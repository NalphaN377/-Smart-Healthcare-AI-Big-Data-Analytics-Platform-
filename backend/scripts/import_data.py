#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Config  # noqa: E402
from backend.app.database import connect_from_config  # noqa: E402
from backend.app.utils.columns import OUTPUT_COLUMNS  # noqa: E402


INSERT_COLUMNS = OUTPUT_COLUMNS
INSERT_SQL = f"""
    INSERT INTO hospital_discharges ({', '.join(f'`{column}`' for column in INSERT_COLUMNS)})
    VALUES ({', '.join(['%s'] * len(INSERT_COLUMNS))})
    ON DUPLICATE KEY UPDATE record_hash = hospital_discharges.record_hash
"""


def configuration() -> dict:
    return {
        key: getattr(Config, key)
        for key in (
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_CONNECT_TIMEOUT",
        )
    }


def _python_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _rows(frame: pd.DataFrame) -> list[tuple[Any, ...]]:
    return [
        tuple(_python_value(value) for value in record)
        for record in frame[INSERT_COLUMNS].itertuples(index=False, name=None)
    ]


def _insert_with_recovery(
    connection,
    rows: list[tuple[Any, ...]],
    source_rows: list[Any],
    errors: list[str],
    max_errors: int,
) -> tuple[int, int]:
    if not rows:
        return 0, 0
    try:
        with connection.cursor() as cursor:
            cursor.executemany(INSERT_SQL, rows)
            imported = max(cursor.rowcount, 0)
        connection.commit()
        return imported, 0
    except pymysql.MySQLError as exc:
        connection.rollback()
        if len(rows) == 1:
            if len(errors) < max_errors:
                errors.append(f"source_row={source_rows[0]} mysql_error={exc.args[0]} {exc.args[1]}")
            return 0, 1
        midpoint = len(rows) // 2
        left = _insert_with_recovery(
            connection, rows[:midpoint], source_rows[:midpoint], errors, max_errors
        )
        right = _insert_with_recovery(
            connection, rows[midpoint:], source_rows[midpoint:], errors, max_errors
        )
        return left[0] + right[0], left[1] + right[1]


def run(args: argparse.Namespace) -> int:
    path = Path(args.input).resolve()
    if not path.is_file():
        print(f"Clean Parquet not found: {path}", file=sys.stderr)
        return 2
    parquet = pq.ParquetFile(path)
    missing = sorted(set(INSERT_COLUMNS) - set(parquet.schema_arrow.names))
    if missing:
        print("Parquet is missing required columns: " + ", ".join(missing), file=sys.stderr)
        return 2

    config = configuration()
    connection = connect_from_config(config)
    imported = failed = processed = 0
    errors: list[str] = []
    started = time.perf_counter()
    try:
        for batch_number, batch in enumerate(parquet.iter_batches(batch_size=args.batch_size), start=1):
            frame = batch.to_pandas()
            batch_rows = _rows(frame)
            source_rows = frame["source_row_number"].tolist()
            batch_imported, batch_failed = _insert_with_recovery(
                connection, batch_rows, source_rows, errors, args.max_errors
            )
            imported += batch_imported
            failed += batch_failed
            processed += len(frame)
            print(
                f"Batch {batch_number}: processed={processed:,}, imported={imported:,}, failed={failed:,}"
            )
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS row_count FROM hospital_discharges")
            database_rows = int(cursor.fetchone()["row_count"])
    finally:
        connection.close()

    elapsed = time.perf_counter() - started
    rows_per_second = processed / elapsed if elapsed else math.inf
    skipped_existing = processed - imported - failed
    print(f"Imported rows: {imported:,}")
    print(f"Existing rows skipped: {skipped_existing:,}")
    print(f"Failed rows: {failed:,}")
    print(f"Elapsed time: {elapsed:,.2f} seconds")
    print(f"Rows per second: {rows_per_second:,.2f}")
    print(f"SELECT COUNT(*): {database_rows:,}")
    print(f"Clean Parquet rows: {parquet.metadata.num_rows:,}")
    if database_rows < parquet.metadata.num_rows - failed:
        print("Consistency check failed: database contains fewer rows than this clean file", file=sys.stderr)
        return 1
    if errors:
        print("Failed row diagnostics (capped):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch import cleaned medical Parquet into MySQL")
    parser.add_argument(
        "--input",
        default=str(PROJECT_ROOT / "data" / "processed" / "hospital_discharges_clean.parquet"),
    )
    parser.add_argument("--batch-size", type=int, default=2_000)
    parser.add_argument("--max-errors", type=int, default=100)
    args = parser.parse_args()
    if args.batch_size < 1 or args.max_errors < 1:
        parser.error("batch-size and max-errors must be positive")
    return args


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_args()))
    except pymysql.MySQLError as exc:
        print(f"Import failed: MySQL error {exc.args[0]}: {exc.args[1]}", file=sys.stderr)
        raise SystemExit(1)
