#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.storagelevel import StorageLevel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "hospital_discharges_clean.parquet"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "analytics_summary.json"


def rows(frame: DataFrame, limit: int | None = None) -> list[dict]:
    selected = frame.limit(limit) if limit else frame
    return [record.asDict(recursive=True) for record in selected.collect()]


def grouped_analysis(
    frame: DataFrame,
    dimension: str,
    limit: int,
    order_by: str = "record_count",
) -> list[dict]:
    result = (
        frame.where(F.col(dimension).isNotNull() & (F.trim(F.col(dimension).cast("string")) != ""))
        .groupBy(dimension)
        .agg(
            F.count("*").alias("record_count"),
            F.round(F.avg("length_of_stay"), 2).alias("avg_length_of_stay"),
            F.round(F.avg("total_charges"), 2).alias("avg_total_charges"),
            F.round(F.avg("total_costs"), 2).alias("avg_total_costs"),
        )
        .orderBy(F.desc(order_by), F.asc(dimension))
    )
    return rows(result, limit)


def run(input_path: Path, output_path: Path, limit: int) -> dict:
    if not input_path.is_file():
        raise FileNotFoundError(f"Clean Parquet not found: {input_path}")
    spark = (
        SparkSession.builder.master("local[*]")
        .appName("medical-ai-platform-local-analytics")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "Asia/Shanghai")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    started = time.perf_counter()
    frame = spark.read.parquet(str(input_path)).persist(StorageLevel.MEMORY_AND_DISK)
    try:
        total_records = frame.count()
        normalized_facility_name = F.trim(F.col("facility_name").cast("string"))
        overview_row = frame.agg(
            F.countDistinct(
                F.when(
                    F.col("facility_name").isNotNull() & (normalized_facility_name != ""),
                    normalized_facility_name,
                )
            ).alias("facility_count"),
            F.round(F.avg("length_of_stay"), 2).alias("avg_length_of_stay"),
            F.round(F.avg("total_charges"), 2).alias("avg_total_charges"),
            F.round(F.avg("total_costs"), 2).alias("avg_total_costs"),
            F.round(
                F.avg(F.when(F.col("emergency_indicator") == True, 1.0).otherwise(0.0)) * 100,
                2,
            ).alias("emergency_percentage"),
        ).first()

        disease_top = grouped_analysis(frame, "diagnosis_description", limit)
        disease_cost = rows(
            frame.where(F.col("diagnosis_description").isNotNull())
            .groupBy("diagnosis_description")
            .agg(
                F.count("*").alias("record_count"),
                F.round(F.avg("total_charges"), 2).alias("avg_total_charges"),
                F.round(F.avg("total_costs"), 2).alias("avg_total_costs"),
            )
            .orderBy(F.desc("avg_total_charges"), F.desc("record_count")),
            limit,
        )
        age = grouped_analysis(frame, "age_group", limit)
        hospitals = grouped_analysis(frame, "facility_name", limit)

        payment_counts = (
            frame.where(F.col("payment_type_1").isNotNull())
            .groupBy("payment_type_1")
            .agg(F.count("*").alias("record_count"))
            .orderBy(F.desc("record_count"))
        )
        payment_total = payment_counts.agg(F.sum("record_count").alias("total")).first()["total"] or 0
        payments = [
            {
                **record,
                "percentage": round(record["record_count"] / payment_total * 100, 2)
                if payment_total
                else 0,
            }
            for record in rows(payment_counts, limit)
        ]
        severity = grouped_analysis(frame, "severity", limit)
        yearly = rows(
            frame.where(F.col("discharge_year").isNotNull())
            .groupBy("discharge_year")
            .agg(
                F.count("*").alias("record_count"),
                F.round(F.avg("total_charges"), 2).alias("avg_total_charges"),
                F.round(F.avg("total_costs"), 2).alias("avg_total_costs"),
            )
            .orderBy("discharge_year")
        )
        disease_year = rows(
            frame.where(F.col("discharge_year").isNotNull() & F.col("diagnosis_description").isNotNull())
            .groupBy("discharge_year", "diagnosis_description")
            .agg(F.count("*").alias("record_count"))
            .orderBy("discharge_year", F.desc("record_count")),
            max(limit * max(len(yearly), 1), limit),
        )
        trend_available = len(yearly) > 1
        result = {
            "source": str(input_path),
            "generated_by": "PySpark local[*]",
            "overview": {"total_records": total_records, **overview_row.asDict()},
            "diseases_top": disease_top,
            "diseases_cost": disease_cost,
            "age_analysis": age,
            "hospital_analysis": hospitals,
            "payment_distribution": payments,
            "severity_analysis": severity,
            "yearly_trends": {
                "available": trend_available,
                "note": None
                if trend_available
                else "数据仅包含一个或零个年份，无法形成有效时间趋势",
                "years": yearly,
                "disease_by_year": disease_year if trend_available else [],
            },
            "elapsed_seconds": round(time.perf_counter() - started, 2),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(f".{output_path.name}.tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, output_path)
        return result
    finally:
        frame.unpersist()
        spark.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PySpark local-mode medical analytics")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("limit must be between 1 and 100")
    return args


if __name__ == "__main__":
    arguments = parse_args()
    try:
        summary = run(Path(arguments.input).resolve(), Path(arguments.output).resolve(), arguments.limit)
    except Exception as exc:
        print(f"Spark analysis failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Spark records analyzed: {summary['overview']['total_records']:,}")
    print(f"Analytics summary: {Path(arguments.output).resolve()}")
