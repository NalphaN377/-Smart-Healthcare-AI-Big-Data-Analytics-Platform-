"""Spark Local 分布式 ETL：CSV -> 清洗 -> Parquet -> （可选）SQL Server。

与 ``scripts/bulk_ingest_sqlserver.py``（Pandas / BULK INSERT）口径完全一致：
复用 ``cleaner.py`` 的清洗规则（整行去重、金额标准化、Length of Stay 转数值、
非新生儿 Birth Weight 置空、缺失处理）与 ``quality.py`` 的四维质量评估，
用 Spark DataFrame 算子实现，结果落 **Parquet 列式存储**，并可选写回业务表。

环境要求：
- conda 环境已装 ``pyspark>=3.4``、``py4j``；
- **JDK 17**（Spark 3.4 不支持 JDK 22 之类更高版本）。若 JDK17 不在默认
  ``JAVA_HOME``，可设置 ``SPARK_JAVA_HOME`` 指向它，脚本会自动切换。

用法：
    python scripts/spark_etl.py --file "<CSV路径>"                          # 清洗 + Parquet
    python scripts/spark_etl.py --file "<CSV路径>" --write-sqlserver --truncate   # 另写回业务表
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from functools import reduce

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Spark 3.4 不支持 JDK 22+；允许用 SPARK_JAVA_HOME 指定 JDK 17
if os.environ.get("SPARK_JAVA_HOME") and Path(os.environ["SPARK_JAVA_HOME"]).exists():
    os.environ["JAVA_HOME"] = os.environ["SPARK_JAVA_HOME"]

from app.data_layer import storage  # noqa: E402
from config import DATA_DIR, SOURCE_DATA_PATH  # noqa: E402

# 与 cleaner.py / quality.py 保持一致的关键字段（snake_case 版）
REQUIRED_FIELDS_SNAKE = [
    "facility_name", "age_group", "length_of_stay", "discharge_year",
    "ccsr_diagnosis_description", "payment_typology_1", "total_charges", "total_costs",
]
MONEY_SNAKE = ["total_charges", "total_costs"]
NUMERIC_SNAKE = ["length_of_stay", "discharge_year", "apr_severity_of_illness_code", *MONEY_SNAKE]


def build_spark():
    """创建 Local 模式 SparkSession（演示级配置，避免 OOM）。"""
    import pyspark
    from pyspark.sql import SparkSession

    # conda 环境下 PySpark 解析 SPARK_HOME 会漏掉 \pyspark 一级，导致找不到 bin/spark-submit.cmd；
    # 这里显式钉到 pyspark 包目录（含 bin 与依赖 jar）。
    spark_home = os.path.dirname(pyspark.__file__)
    if not Path(spark_home, "bin", "spark-submit.cmd").exists():
        raise RuntimeError(f"未找到 bin/spark-submit.cmd，SPARK_HOME 应指向 pyspark 包目录: {spark_home}")
    os.environ["SPARK_HOME"] = spark_home

    # Windows 原生 FS 写入依赖 winutils.exe（HADOOP_HOME 目录含 bin/winutils.exe）
    hadoop_home = os.environ.get("SPARK_HADOOP_HOME") or "E:/support/hadoop"
    if Path(hadoop_home, "bin", "winutils.exe").exists():
        os.environ["HADOOP_HOME"] = hadoop_home

    builder = (
        SparkSession.builder
        .appName("sparcs-etl-local")
        .master("local[*]")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.memory", "3g")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.adaptive.enabled", "true")
    )
    if os.environ.get("HADOOP_HOME"):
        hadoop_home = os.environ["HADOOP_HOME"]
        builder = builder.config("spark.hadoop.hadoop.home.dir", hadoop_home)
        # Windows 上强制 Java 实现，避免 NativeIO$Windows.access0 的原生库 UnsatisfiedLinkError
        builder = builder.config("spark.hadoop.hadoop.native.lib", "false")
        builder = builder.config("spark.driver.extraJavaOptions", f"-Djava.library.path={hadoop_home}\\bin")
    return builder.getOrCreate()


def load_and_rename(spark, filepath: str):
    """整列按字符串读入（金额/年份原始形态不一），再按 COLUMN_MAPPING 转 snake_case。"""
    from pyspark.sql import functions as F

    raw = spark.read.option("header", True).csv(filepath)
    mapping = storage.COLUMN_MAPPING
    missing = [name for name in mapping if name not in raw.columns]
    if missing:
        raise ValueError(f"源文件缺少字段: {missing}")
    return raw.select(
        *[F.col(original).alias(snake) for original, snake in mapping.items()]
    )


def clean_spark(df):
    """Spark 版清洗流水线，与 cleaner.clean() 规则一一对应。"""
    from pyspark.sql import functions as F

    # 1. 整行去重（keep first）
    before = df.count()
    df = df.dropDuplicates()
    duplicates_removed = before - df.count()

    # 2. 金额标准化：去 逗号/$、空串置空、转 double、负值归 0
    for col in MONEY_SNAKE:
        df = df.withColumn(
            col,
            F.when(F.regexp_replace(F.col(col), r"[,$\s]", "").isin("", "-", "."), F.lit(None))
            .otherwise(F.regexp_replace(F.col(col), r"[,$\s]", "").cast("double")),
        )
        df = df.withColumn(col, F.when(F.col(col) < 0, F.lit(0.0)).otherwise(F.col(col)))

    # 3. 数值类型标准化：LOS 提取数字（"120 +" -> 120）、年份/严重度编码转 int
    df = df.withColumn(
        "length_of_stay",
        F.when(F.regexp_extract(F.col("length_of_stay"), r"(\d+)", 0) == "", F.lit(None))
        .otherwise(F.regexp_extract(F.col("length_of_stay"), r"(\d+)", 0).cast("int")),
    )
    df = df.withColumn("length_of_stay", F.when(F.col("length_of_stay") < 0, F.lit(0)).otherwise(F.col("length_of_stay")))
    for col in ("discharge_year", "apr_severity_of_illness_code"):
        df = df.withColumn(col, F.col(col).cast("int"))

    # 4. 缺失处理：字符字段空串填充（与 handle_missing 一致）
    for col, dtype in df.dtypes:
        if dtype == "string":
            df = df.withColumn(col, F.when(F.col(col).isNull(), F.lit("")).otherwise(F.col(col)))

    # 5. 非新生儿 Birth Weight 置空（最后执行，与 cleaner 顺序一致）
    df = df.withColumn(
        "birth_weight",
        F.when(F.col("type_of_admission") != "Newborn", F.lit(None)).otherwise(F.col("birth_weight")),
    )

    # 6. 核心字段全部缺失的坏行剔除（对应 clean_with_stats）
    blank_all = reduce(lambda a, b: a & b, (F.col(c).isNull() | (F.col(c) == "") for c in REQUIRED_FIELDS_SNAKE))
    df = df.where(~blank_all)

    stats = {
        "rows_read": before,
        "rows_after_clean": df.count(),
        "duplicates_removed": duplicates_removed,
    }
    return df, stats


def assess_spark(df) -> dict:
    """Spark 版四维质量评估，与 quality.assess() 同口径。"""
    from pyspark.sql import functions as F

    total = df.count()
    if not total:
        return {"completeness": 0, "accuracy": 0, "consistency": 0, "timeliness": 0, "uniqueness": 0, "overall": 0, "sample_size": 0}

    # completeness：核心字段"非空且非空串"单元格占比（对应 quality.completeness）
    blank_cells = sum(
        df.filter(F.col(c).isNull() | (F.col(c) == "")).count() for c in REQUIRED_FIELDS_SNAKE
    )
    completeness = 1.0 - blank_cells / (len(REQUIRED_FIELDS_SNAKE) * total)

    # accuracy：金额/时长三列"可解析且 >= 0"占比的平均（对应 quality.accuracy）
    accuracy = float(
        sum(
            df.filter(F.col(c).isNotNull() & (F.col(c) >= 0)).count()
            for c in (MONEY_SNAKE + ["length_of_stay"])
        ) / (3.0 * total)
    )

    # consistency：Gender / ED / Risk 取值域校验
    consistency = sum([
        df.filter(F.col("gender").isNull() | (F.col("gender").isin("M", "F", "U"))).count() / total,
        df.filter(F.col("emergency_department_indicator").isNull() | (F.col("emergency_department_indicator").isin("Y", "N"))).count() / total,
        df.filter(F.col("apr_risk_of_mortality").isNull() | (F.col("apr_risk_of_mortality").isin("Minor", "Moderate", "Major", "Extreme", ""))).count() / total,
    ]) / 3.0

    # timeliness：出院年份在合理区间
    timeliness = df.filter(F.col("discharge_year").between(2000, date.today().year)).count() / total

    report = {
        "completeness": round(completeness, 4),
        "accuracy": round(accuracy, 4),
        "consistency": round(consistency, 4),
        "timeliness": round(timeliness, 4),
        "sample_size": int(total),
    }
    # uniqueness 由清洗阶段的真实去重数计算（在 main 中补入），整体分不含唯一性（与 quality.assess 一致）
    report["overall"] = round(sum(report[k] for k in ("completeness", "accuracy", "consistency", "timeliness")) / 4.0, 4)
    return report


def write_parquet_fallback(df, out: str) -> str:
    """Spark 写盘在 Windows 缺失 Hadoop 原生库时降级：collect 后由 pyarrow 落列式 Parquet。"""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(out)
    path.mkdir(parents=True, exist_ok=True)
    part = path / "part-00000.parquet"
    table = pa.Table.from_pandas(df.toPandas())
    pq.write_table(table, str(part), compression="snappy")
    return f"pyarrow@{part}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Spark Local ETL：清洗 TOP 数据并落 Parquet")
    parser.add_argument("--file", default=str(SOURCE_DATA_PATH), help="源 CSV 路径")
    parser.add_argument("--out", default=str(DATA_DIR / "processed" / "spark_inpatient_discharge.parquet"), help="Parquet 输出目录")
    parser.add_argument("--no-parquet", action="store_true", help="不写 Parquet，仅演示清洗/质量")
    parser.add_argument("--write-sqlserver", action="store_true", help="另将清洗结果写回 SQL Server 业务表")
    parser.add_argument("--truncate", action="store_true", help="写回前清空业务表（与 write-sqlserver 配合）")
    args = parser.parse_args()

    started = time.perf_counter()
    spark = build_spark()
    try:
        df = load_and_rename(spark, args.file)
        cleaned, stats = clean_spark(df)
        quality = assess_spark(cleaned)
        quality["uniqueness"] = round(1.0 - stats["duplicates_removed"] / stats["rows_read"], 4)

        out = None
        write_engine = None
        if not args.no_parquet:
            out = str(Path(args.out))
            try:
                cleaned.write.mode("overwrite").parquet(out)
                write_engine = "spark"
            except Exception as exc:
                print(f"[WARN] Spark 写 Parquet 失败，降级 pyarrow 落盘: {exc}", file=sys.stderr)
                write_engine = write_parquet_fallback(cleaned, out)

        db_info = None
        if args.write_sqlserver:
            if args.truncate:
                storage.truncate_table()
            pandas_df = cleaned.select(*storage.SQL_COLUMNS).toPandas()
            run_id = storage.start_ingestion(args.file, Path(args.file).stat().st_size)
            try:
                inserted = storage.bulk_insert(pandas_df)
                storage.finish_ingestion(run_id, status="completed", quality=quality)
                db_info = {"run_id": run_id, "rows_inserted": inserted}
            except Exception:
                storage.finish_ingestion(run_id, status="failed", error="spark_etl 写回失败")
                raise

        summary = {
            "engine": "spark_local",
            "write_engine": write_engine,
            "rows_read": stats["rows_read"],
            "rows_after_clean": stats["rows_after_clean"],
            "duplicates_removed": stats["duplicates_removed"],
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "quality": {k: quality[k] for k in ("completeness", "accuracy", "consistency", "timeliness", "uniqueness", "overall")},
            "parquet": out,
            "sqlserver": db_info,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()