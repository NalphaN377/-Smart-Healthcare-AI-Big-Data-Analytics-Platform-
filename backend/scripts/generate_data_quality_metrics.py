#!/usr/bin/env python3
"""Generate a small machine-readable quality snapshot from the official Parquet."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


KEY_FIELDS = (
    "age_group",
    "facility_name",
    "diagnosis_description",
    "severity",
    "payment_type_1",
    "length_of_stay",
    "total_charges",
    "total_costs",
)
RULE_COLUMNS = (
    "facility_name",
    "admission_type",
    "apr_mdc_description",
    "apr_drg_description",
    "birth_weight",
    "length_of_stay",
    "discharge_year",
    "emergency_indicator",
    "total_charges",
    "total_costs",
    "source_file",
    "record_hash",
)


def duplicate_rows_removed(report_path: Path) -> int:
    if not report_path.is_file():
        return 0
    text = report_path.read_text(encoding="utf-8")
    match = re.search(r"Exact duplicate rows removed:\s*([\d,]+)", text)
    return int(match.group(1).replace(",", "")) if match else 0


def parquet_null_counts(parquet: pq.ParquetFile) -> dict[str, int]:
    names = parquet.schema_arrow.names
    counts = {name: 0 for name in names}
    for row_group_index in range(parquet.metadata.num_row_groups):
        row_group = parquet.metadata.row_group(row_group_index)
        for column_index, name in enumerate(names):
            statistics = row_group.column(column_index).statistics
            if statistics is None or statistics.null_count is None:
                raise RuntimeError(f"Parquet statistics missing null_count for {name}")
            counts[name] += int(statistics.null_count)
    return counts


def scan_rules(parquet: pq.ParquetFile, batch_size: int) -> dict:
    temporary = tempfile.NamedTemporaryFile(
        prefix="medical_quality_hashes_",
        suffix=".sqlite3",
        delete=False,
    )
    dedup_path = Path(temporary.name)
    temporary.close()
    database = sqlite3.connect(dedup_path)
    database.execute("CREATE TABLE hashes(value TEXT PRIMARY KEY) WITHOUT ROWID")

    facilities: set[str] = set()
    source_files: set[str] = set()
    duplicate_rows = 0
    anomalies = {
        "negative_charges": 0,
        "negative_costs": 0,
        "invalid_length_of_stay": 0,
        "invalid_birth_weight": 0,
        "invalid_year": 0,
        "invalid_emergency_indicator": 0,
    }
    current_year = datetime.now(UTC).year
    try:
        for batch in parquet.iter_batches(batch_size=batch_size, columns=RULE_COLUMNS):
            frame = batch.to_pandas()
            facilities.update(
                value.strip()
                for value in frame["facility_name"].dropna().astype(str)
                if value.strip()
            )
            source_files.update(
                value.strip()
                for value in frame["source_file"].dropna().astype(str)
                if value.strip()
            )
            anomalies["negative_charges"] += int(
                frame["total_charges"].lt(0).fillna(False).sum()
            )
            anomalies["negative_costs"] += int(
                frame["total_costs"].lt(0).fillna(False).sum()
            )
            anomalies["invalid_length_of_stay"] += int(
                frame["length_of_stay"].lt(0).fillna(False).sum()
            )
            invalid_year = frame["discharge_year"].notna() & ~frame["discharge_year"].between(
                1900,
                current_year + 1,
            )
            anomalies["invalid_year"] += int(invalid_year.sum())
            if not pd.api.types.is_bool_dtype(frame["emergency_indicator"].dtype):
                invalid_emergency = frame["emergency_indicator"].notna() & ~frame[
                    "emergency_indicator"
                ].isin([True, False])
                anomalies["invalid_emergency_indicator"] += int(invalid_emergency.sum())

            context = (
                frame["admission_type"].fillna("")
                + " "
                + frame["apr_mdc_description"].fillna("")
                + " "
                + frame["apr_drg_description"].fillna("")
            ).str.casefold()
            newborn = context.str.contains(r"newborn|neonate|liveborn|birth", regex=True)
            weight = frame["birth_weight"]
            invalid_weight = weight.notna() & ((weight <= 0) | (weight > 15_000) | ~newborn)
            anomalies["invalid_birth_weight"] += int(invalid_weight.sum())

            hashes = [(str(value),) for value in frame["record_hash"].dropna()]
            before = database.total_changes
            database.executemany("INSERT OR IGNORE INTO hashes(value) VALUES (?)", hashes)
            duplicate_rows += len(hashes) - (database.total_changes - before)
            database.commit()
    finally:
        database.close()
        dedup_path.unlink(missing_ok=True)
    return {
        "facility_count": len(facilities),
        "source_files": sorted(source_files),
        "duplicate_rows_remaining": duplicate_rows,
        "anomalies": anomalies,
    }


def generate(input_path: Path, report_path: Path, batch_size: int) -> dict:
    parquet = pq.ParquetFile(input_path)
    total_rows = int(parquet.metadata.num_rows)
    total_columns = int(parquet.metadata.num_columns)
    null_counts = parquet_null_counts(parquet)
    rules = scan_rules(parquet, batch_size)
    total_nulls = sum(null_counts.values())
    total_cells = total_rows * total_columns
    anomalies = rules["anomalies"]
    invalid_total = sum(anomalies.values())
    consistency_invalid = (
        anomalies["invalid_length_of_stay"]
        + anomalies["invalid_year"]
        + anomalies["invalid_emergency_indicator"]
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "total_rows": total_rows,
        "total_columns": total_columns,
        "duplicate_rows_removed": duplicate_rows_removed(report_path),
        "duplicate_rows_remaining": rules["duplicate_rows_remaining"],
        "facility_count": rules["facility_count"],
        "completeness_score": round((1 - total_nulls / total_cells) * 100, 2),
        "validity_score": round(max(0, 1 - invalid_total / max(total_rows * 6, 1)) * 100, 2),
        "consistency_score": round(
            max(0, 1 - consistency_invalid / max(total_rows * 3, 1)) * 100,
            2,
        ),
        "fields": [
            {
                "field": field,
                "missing_count": null_counts[field],
                "missing_rate": round(null_counts[field] * 100 / total_rows, 4),
            }
            for field in KEY_FIELDS
        ],
        "anomalies": anomalies,
        "source": {
            "source_filename": rules["source_files"][0] if len(rules["source_files"]) == 1 else None,
            "source_files": rules["source_files"],
            "processed_filename": input_path.name,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(PROJECT_ROOT / "data/processed/hospital_discharges_clean.parquet"),
    )
    parser.add_argument(
        "--cleaning-report",
        default=str(PROJECT_ROOT / "docs/data_quality_report.md"),
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "docs/data_quality_metrics.json"),
    )
    parser.add_argument("--batch-size", type=int, default=100_000)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("batch-size must be positive")
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"cleaned Parquet not found: {input_path}")
    metrics = generate(input_path, Path(args.cleaning_report).resolve(), args.batch_size)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
