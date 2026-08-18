#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.utils.columns import OUTPUT_COLUMNS  # noqa: E402


def validate(path: Path, batch_size: int) -> int:
    parquet = pq.ParquetFile(path)
    missing = sorted(set(OUTPUT_COLUMNS) - set(parquet.schema_arrow.names))
    failures: list[str] = []
    if missing:
        failures.append("Missing columns: " + ", ".join(missing))

    temporary = tempfile.NamedTemporaryFile(prefix="medical_validate_", suffix=".sqlite3", delete=False)
    dedup_path = Path(temporary.name)
    temporary.close()
    database = sqlite3.connect(dedup_path)
    database.execute("CREATE TABLE hashes(value TEXT PRIMARY KEY) WITHOUT ROWID")
    total_rows = 0
    duplicate_rows = 0
    invalid_costs = 0
    invalid_stays = 0
    invalid_birth_weights = 0
    try:
        for batch in parquet.iter_batches(batch_size=batch_size):
            frame = batch.to_pandas()
            total_rows += len(frame)
            invalid_costs += int(
                frame["total_charges"].lt(0).fillna(False).sum()
                + frame["total_costs"].lt(0).fillna(False).sum()
            )
            invalid_stays += int(frame["length_of_stay"].lt(0).fillna(False).sum())
            context = (
                frame["admission_type"].fillna("")
                + " "
                + frame["apr_mdc_description"].fillna("")
                + " "
                + frame["apr_drg_description"].fillna("")
            ).str.casefold()
            newborn = context.str.contains(r"newborn|neonate|liveborn|birth", regex=True)
            weight_present = frame["birth_weight"].notna()
            invalid_birth_weights += int((weight_present & ~newborn).sum())
            for record_hash in frame["record_hash"].tolist():
                before = database.total_changes
                database.execute("INSERT OR IGNORE INTO hashes(value) VALUES (?)", (record_hash,))
                duplicate_rows += int(database.total_changes == before)
            database.commit()
    finally:
        database.close()
        dedup_path.unlink(missing_ok=True)

    if invalid_costs:
        failures.append(f"Negative charge/cost values: {invalid_costs}")
    if invalid_stays:
        failures.append(f"Negative length-of-stay values: {invalid_stays}")
    if invalid_birth_weights:
        failures.append(f"Birth weights outside newborn context: {invalid_birth_weights}")
    if duplicate_rows:
        failures.append(f"Duplicate record hashes: {duplicate_rows}")

    print(f"Rows validated: {total_rows:,}")
    print(f"Columns: {len(parquet.schema_arrow.names)}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Validation passed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate cleaned medical Parquet data")
    parser.add_argument(
        "--input",
        default=str(PROJECT_ROOT / "data" / "processed" / "hospital_discharges_clean.parquet"),
    )
    parser.add_argument("--batch-size", type=int, default=50_000)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("batch-size must be positive")
    return args


if __name__ == "__main__":
    arguments = parse_args()
    source_path = Path(arguments.input).resolve()
    if not source_path.is_file():
        print(f"Clean Parquet not found: {source_path}", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(validate(source_path, arguments.batch_size))
