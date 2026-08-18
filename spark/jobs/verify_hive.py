#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time

from pyspark.sql import SparkSession, functions as F


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Spark SQL through a remote Hive Metastore")
    parser.add_argument(
        "--metastore-uri",
        default="thrift://hive-metastore:9083",
    )
    parser.add_argument(
        "--table",
        default="medical_analytics.hospital_discharges",
    )
    parser.add_argument("--expected-rows", type=int, default=2_094_483)
    parser.add_argument("--expected-facilities", type=int, default=205)
    return parser.parse_args()


def run(args: argparse.Namespace) -> tuple[int, int, float]:
    spark = (
        SparkSession.builder.master("local[*]")
        .appName("medical-ai-platform-hive-verification")
        .config("spark.sql.catalogImplementation", "hive")
        .config("hive.metastore.uris", args.metastore_uri)
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "8")
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    started = time.perf_counter()
    try:
        frame = spark.table(args.table)
        normalized_name = F.trim(F.col("facility_name").cast("string"))
        result = frame.agg(
            F.count("*").alias("record_count"),
            F.countDistinct(
                F.when(
                    F.col("facility_name").isNotNull() & (normalized_name != ""),
                    normalized_name,
                )
            ).alias("facility_count"),
        ).first()
        return int(result["record_count"]), int(result["facility_count"]), time.perf_counter() - started
    finally:
        spark.stop()


if __name__ == "__main__":
    arguments = parse_args()
    try:
        records, facilities, elapsed = run(arguments)
    except Exception as exc:
        print(f"Spark Hive verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Spark Hive records: {records:,}")
    print(f"Spark Hive facility count: {facilities:,}")
    print(f"Spark Hive elapsed: {elapsed:,.2f} seconds")
    if records != arguments.expected_rows or facilities != arguments.expected_facilities:
        print("Spark Hive consistency check failed", file=sys.stderr)
        raise SystemExit(1)
