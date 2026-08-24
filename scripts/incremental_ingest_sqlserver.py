"""SPARCS 多年度 CSV -> SQL Server 幂等增量导入。

处理流程：字段契约校验 -> 文件指纹 -> BULK INSERT 暂存表 -> SQL标准化
-> 行哈希去重 -> 追加业务表 -> 数据版本发布。脚本不清空已有业务数据。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.common import cache  # noqa: E402
from app.data_layer import loader, storage  # noqa: E402
from app.service_layer.analysis import dashboard_stats  # noqa: E402
from config import BASE_DIR  # noqa: E402
from scripts.bulk_ingest_sqlserver import TEXT_EXPRESSIONS, _run_dotnet_sql  # noqa: E402


def file_sha256(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def read_and_validate_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        raw_columns = next(csv.reader(stream))
    canonical = loader.canonicalize_column_names(raw_columns)
    expected = list(storage.COLUMN_MAPPING)
    if canonical != expected:
        missing = [column for column in expected if column not in canonical]
        unknown = [column for column in canonical if column not in expected]
        order_matches = not missing and not unknown
        raise ValueError(
            f"{path.name} 字段契约不匹配: 缺少={missing}, 多出={unknown}, "
            f"字段集合相同但顺序不同={order_matches and canonical != expected}"
        )
    return raw_columns


def _row_hash_expression() -> str:
    pieces = [f"N'|',COALESCE(CONVERT(NVARCHAR(MAX),[{column}]),N'<NULL>')" for column in storage.SQL_COLUMNS]
    return "HASHBYTES('SHA2_256',CONCAT(CAST(N'' AS NVARCHAR(MAX))," + ",".join(pieces) + "))"


def build_incremental_sql(path: Path, run_id: int) -> str:
    escaped_path = str(path).replace("'", "''")
    columns_sql = ", ".join(f"[{name}]" for name in storage.SQL_COLUMNS)
    expressions_sql = ", ".join(f"{TEXT_EXPRESSIONS[name]} AS [{name}]" for name in storage.SQL_COLUMNS)
    hash_expression = _row_hash_expression()
    dashboard_merge_sql = dashboard_stats.batch_merge_sql(run_id)
    return f"""
SET NOCOUNT ON;
SET XACT_ABORT ON;
BEGIN TRANSACTION;
DECLARE @lock_result INT;
EXEC @lock_result = sys.sp_getapplock
    @Resource=N'yiliaoBigData:incremental_ingestion', @LockMode='Exclusive',
    @LockOwner='Transaction', @LockTimeout=0;
IF @lock_result < 0 THROW 51000, N'已有增量导入任务正在运行', 1;

TRUNCATE TABLE dbo.inpatient_discharge_stage;
BULK INSERT dbo.inpatient_discharge_stage
FROM '{escaped_path}'
WITH (FORMAT='CSV', FIRSTROW=2, FIELDQUOTE='"', ROWTERMINATOR='0x0a',
      CODEPAGE='65001', TABLOCK, BATCHSIZE=50000, MAXERRORS=1);

DECLARE @rows_read BIGINT = (SELECT COUNT_BIG(*) FROM dbo.inpatient_discharge_stage);
;WITH normalized AS (
    SELECT {expressions_sql}
    FROM dbo.inpatient_discharge_stage
), hashed AS (
    SELECT *, {hash_expression} AS source_row_hash
    FROM normalized
), deduplicated AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY source_row_hash ORDER BY (SELECT NULL)) AS duplicate_rank
    FROM hashed
)
INSERT INTO dbo.inpatient_discharge ({columns_sql}, source_row_hash, source_batch_id)
SELECT {columns_sql}, incoming.source_row_hash, {int(run_id)}
FROM deduplicated AS incoming
WHERE incoming.duplicate_rank=1
  AND NOT EXISTS (
      SELECT 1 FROM dbo.inpatient_discharge AS existing WITH (UPDLOCK,HOLDLOCK)
      WHERE existing.source_row_hash=incoming.source_row_hash
  );

DECLARE @rows_inserted BIGINT = @@ROWCOUNT;
UPDATE dbo.ingestion_run
SET chunks_processed=1, rows_read=@rows_read, rows_inserted=@rows_inserted,
    rows_dropped=0, rows_skipped=@rows_read-@rows_inserted
WHERE id={int(run_id)};

MERGE dbo.disease_procedure_stat AS target
USING (
    SELECT discharge_year,
           ccsr_diagnosis_code AS diagnosis_code,
           MAX(ccsr_diagnosis_description) AS diagnosis_description,
           ccsr_procedure_code AS procedure_code,
           MAX(ccsr_procedure_description) AS procedure_description,
           COUNT_BIG(*) AS pair_count
    FROM dbo.inpatient_discharge
    WHERE source_batch_id={int(run_id)} AND discharge_year IS NOT NULL
      AND ccsr_diagnosis_code IS NOT NULL AND LTRIM(RTRIM(ccsr_diagnosis_code))<>''
      AND ccsr_procedure_code IS NOT NULL AND LTRIM(RTRIM(ccsr_procedure_code))<>''
    GROUP BY discharge_year,ccsr_diagnosis_code,ccsr_procedure_code
) AS source
ON target.discharge_year=source.discharge_year
AND target.diagnosis_code=source.diagnosis_code
AND target.procedure_code=source.procedure_code
WHEN MATCHED THEN UPDATE SET
    pair_count=target.pair_count+source.pair_count,
    diagnosis_description=source.diagnosis_description,
    procedure_description=source.procedure_description,
    updated_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT
    (discharge_year,diagnosis_code,diagnosis_description,procedure_code,procedure_description,pair_count)
VALUES
    (source.discharge_year,source.diagnosis_code,source.diagnosis_description,
     source.procedure_code,source.procedure_description,source.pair_count);
{dashboard_merge_sql}
COMMIT TRANSACTION;
"""


def _batch_quality(run_id: int) -> dict:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT_BIG(*), "
            "AVG(CASE WHEN facility_name IS NOT NULL AND age_group IS NOT NULL AND discharge_year IS NOT NULL "
            "AND ccsr_diagnosis_description IS NOT NULL AND payment_typology_1 IS NOT NULL THEN 1.0 ELSE 0.0 END), "
            "AVG(CASE WHEN length_of_stay >= 0 AND total_charges >= 0 AND total_costs >= 0 THEN 1.0 ELSE 0.0 END), "
            "AVG(CASE WHEN gender IN ('M','F','U') AND emergency_department_indicator IN ('Y','N') THEN 1.0 ELSE 0.0 END), "
            "AVG(CASE WHEN discharge_year BETWEEN 2000 AND YEAR(GETDATE()) THEN 1.0 ELSE 0.0 END) "
            "FROM dbo.inpatient_discharge WHERE source_batch_id=%s" % storage.PARAM,
            (run_id,),
        )
        row = cursor.fetchone()
        report = {
            "sample_size": int(row[0] or 0),
            "completeness": round(float(row[1] or 0), 4),
            "accuracy": round(float(row[2] or 0), 4),
            "consistency": round(float(row[3] or 0), 4),
            "timeliness": round(float(row[4] or 0), 4),
        }
        report["overall"] = round(
            sum(report[key] for key in ("completeness", "accuracy", "consistency", "timeliness")) / 4, 4
        )
        return report
    finally:
        conn.close()


def incremental_ingest(filepath: str | Path, *, force: bool = False) -> dict:
    path = Path(filepath).resolve()
    if not path.is_file() or path.suffix.lower() != ".csv":
        raise ValueError(f"必须提供存在的 CSV 文件: {path}")
    raw_columns = read_and_validate_header(path)
    storage.init_schema()
    storage.mark_stale_ingestions()

    started = time.perf_counter()
    source_hash = file_sha256(path)
    previous = storage.completed_ingestion_by_hash(source_hash)
    if previous and not force:
        return {
            "status": "skipped", "reason": "same_file_already_completed", "source_file": str(path),
            "source_sha256": source_hash, "previous_run": previous,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        }

    run_id = storage.start_ingestion(
        str(path), path.stat().st_size, source_sha256=source_hash,
        mode="incremental", source_columns=raw_columns,
    )
    previous_version = storage.get_data_version()
    try:
        _run_dotnet_sql(build_incremental_sql(path, run_id))
        quality = _batch_quality(run_id)
        storage.finish_ingestion(run_id, status="completed", quality=quality)
        run = storage.get_ingestion(run_id) or {}
        if int(run.get("rows_inserted") or 0) > 0:
            version = storage.bump_data_version()
            dashboard_stats.advance_version(previous_version, version)
            cache.publish_data_version(version)
        else:
            version = storage.get_data_version()
        return {
            "status": "completed", "run_id": run_id, "source_file": str(path),
            "source_sha256": source_hash, "rows_read": int(run.get("rows_read") or 0),
            "rows_inserted": int(run.get("rows_inserted") or 0),
            "rows_skipped": int(run.get("rows_skipped") or 0), "quality": quality,
            "data_version": version, "elapsed_seconds": round(time.perf_counter() - started, 2),
        }
    except Exception as exc:
        storage.finish_ingestion(run_id, status="failed", error=str(exc))
        raise


def _input_files(files: list[str] | None, directory: str | None, pattern: str) -> list[Path]:
    selected = [Path(value).resolve() for value in (files or [])]
    if directory:
        selected.extend(sorted(Path(directory).resolve().glob(pattern)))
    unique = []
    seen = set()
    for path in selected:
        key = str(path).casefold()
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(description="SPARCS 多年度 SQL Server 幂等增量导入")
    parser.add_argument("--file", action="append", help="CSV路径，可重复传入")
    parser.add_argument("--directory", help="批量扫描目录")
    # 新增年度文件使用带括号的新命名；该默认值刻意排除2021文件名末尾的下载日期“20231012”。
    parser.add_argument("--pattern", default="Hospital_Inpatient_Discharges_(SPARCS_De-Identified)__202[2-9]_*.csv")
    parser.add_argument("--force", action="store_true", help="即使文件指纹已成功处理也重新核对（行哈希仍会去重）")
    parser.add_argument("--validate-only", action="store_true", help="只检查字段契约，不连接数据库")
    args = parser.parse_args()

    files = _input_files(args.file, args.directory, args.pattern)
    if not files:
        parser.error("请通过 --file 或 --directory 指定至少一个CSV")
    results = []
    for path in files:
        if args.validate_only:
            results.append({"source_file": str(path), "columns": read_and_validate_header(path), "status": "valid"})
        else:
            results.append(incremental_ingest(path, force=args.force))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
