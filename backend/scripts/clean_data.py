#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.utils.cleaning import clean_chunk  # noqa: E402
from backend.app.utils.columns import OUTPUT_COLUMNS  # noqa: E402
from backend.app.utils.data_io import discover_data_file, iter_data_chunks  # noqa: E402


STRING_COLUMNS = {
    "hospital_service_area",
    "hospital_county",
    "operating_certificate_number",
    "facility_name",
    "age_group",
    "zip_code_3_digits",
    "gender",
    "race",
    "ethnicity",
    "length_of_stay_raw",
    "admission_type",
    "patient_disposition",
    "diagnosis_code",
    "diagnosis_description",
    "procedure_code",
    "procedure_description",
    "apr_drg_description",
    "apr_mdc_description",
    "severity",
    "mortality_risk",
    "medical_surgical_description",
    "payment_type_1",
    "payment_type_2",
    "payment_type_3",
    "source_file",
    "record_hash",
}
INTEGER_COLUMNS = {
    "facility_id",
    "length_of_stay",
    "discharge_year",
    "apr_drg_code",
    "apr_mdc_code",
    "severity_code",
    "birth_weight",
    "source_row_number",
}
FLOAT_COLUMNS = {"total_charges", "total_costs"}


PARQUET_SCHEMA = pa.schema(
    [
        pa.field(
            column,
            pa.string()
            if column in STRING_COLUMNS
            else pa.int64()
            if column in INTEGER_COLUMNS
            else pa.float64()
            if column in FLOAT_COLUMNS
            else pa.bool_(),
            nullable=True,
        )
        for column in OUTPUT_COLUMNS
    ]
)


def _new_hashes(connection: sqlite3.Connection, hashes: list[str]) -> tuple[list[bool], int]:
    existing: set[str] = set()
    for start in range(0, len(hashes), 900):
        batch = hashes[start : start + 900]
        placeholders = ",".join("?" for _ in batch)
        existing.update(
            row[0]
            for row in connection.execute(
                f"SELECT record_hash FROM seen_hashes WHERE record_hash IN ({placeholders})", batch
            )
        )
    mask = [value not in existing for value in hashes]
    new_values = [(value,) for value, keep in zip(hashes, mask) if keep]
    connection.executemany("INSERT INTO seen_hashes(record_hash) VALUES (?)", new_values)
    connection.commit()
    return mask, len(hashes) - len(new_values)


def _write_missing_quality_report(output: Path, message: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "# Data Quality Report\n\n"
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}\n"
        "- Status: **BLOCKED — source dataset not found**\n"
        f"- Detail: `{message}`\n\n"
        "No cleaning result or statistics were fabricated.\n",
        encoding="utf-8",
    )


def _write_quality_report(
    report_path: Path,
    source_path: Path,
    output_path: Path,
    stats: dict[str, int],
    null_cells: int,
    total_cells: int,
    missing_columns: list[str],
    elapsed: float,
) -> None:
    raw_rows = stats.get("raw_rows", 0)
    clean_rows = stats.get("clean_rows", 0)
    duplicates = stats.get("duplicate_rows", 0)
    anomaly_total = sum(
        value
        for key, value in stats.items()
        if key.startswith(("invalid_", "negative_", "birth_weight_cleared"))
    )
    completeness = 1 - null_cells / total_cells if total_cells else 0
    duplicate_rate = duplicates / raw_rows if raw_rows else 0
    validity_denominator = max(clean_rows * 6, 1)
    validity = max(0.0, 1 - anomaly_total / validity_denominator)
    consistency = max(
        0.0,
        1
        - (
            stats.get("invalid_discharge_year", 0)
            + stats.get("invalid_emergency_indicator", 0)
            + stats.get("invalid_length_of_stay", 0)
        )
        / max(clean_rows * 3, 1),
    )
    anomaly_lines = "\n".join(
        f"- `{key}`: {value:,}"
        for key, value in sorted(stats.items())
        if key not in {"raw_rows", "clean_rows", "duplicate_rows"}
    ) or "- None"
    missing_lines = "\n".join(f"- `{column}` — Required field missing" for column in missing_columns) or "- None"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        f"""# Data Quality Report

- Generated: {datetime.now().isoformat(timespec='seconds')}
- Source: `{source_path}`
- Clean output: `{output_path}`
- Elapsed time: {elapsed:,.2f} seconds

## Row reconciliation

- Original rows: {raw_rows:,}
- Exact duplicate rows removed: {duplicates:,}
- Clean rows: {clean_rows:,}
- Reconciled: **{raw_rows == clean_rows + duplicates}**

## Quality dimensions

| Dimension | Score | Method |
|---|---:|---|
| Completeness | {completeness:.2%} | Non-null cells / all canonical output cells |
| Consistency | {consistency:.2%} | Valid year, emergency flag and length-of-stay rules |
| Validity | {validity:.2%} | Six core medical/numeric rule checks |
| Duplicate rate | {duplicate_rate:.4%} | Exact normalized business-row hash |

## Source fields missing

{missing_lines}

## Rule actions and anomalies

{anomaly_lines}

Birth weight is retained only for records whose admission/DRG/MDC context identifies a newborn or neonate; zero and values above 15,000 g are null. `120+` length of stay becomes numeric `120` while the original text is retained.
""",
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> int:
    report_path = Path(args.report).resolve()
    try:
        source = discover_data_file(args.input)
    except (FileNotFoundError, ValueError) as exc:
        _write_missing_quality_report(report_path, str(exc))
        print(f"Cleaning blocked: {exc}", file=sys.stderr)
        print(f"Report written: {report_path}")
        return 2

    output = Path(args.output).resolve()
    if output == source.path:
        print("Refusing to overwrite the source dataset.", file=sys.stderr)
        return 2
    if output.exists() and not args.overwrite:
        print(f"Output already exists: {output}. Use --overwrite to replace only this processed file.", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(f".{output.name}.tmp")
    if temporary_output.exists():
        temporary_output.unlink()

    dedup_handle = tempfile.NamedTemporaryFile(prefix="medical_dedup_", suffix=".sqlite3", delete=False)
    dedup_path = Path(dedup_handle.name)
    dedup_handle.close()
    dedup = sqlite3.connect(dedup_path)
    dedup.execute("PRAGMA journal_mode=WAL")
    dedup.execute("PRAGMA synchronous=NORMAL")
    dedup.execute("CREATE TABLE seen_hashes (record_hash TEXT PRIMARY KEY) WITHOUT ROWID")

    writer = pq.ParquetWriter(temporary_output, PARQUET_SCHEMA, compression="zstd")
    stats: dict[str, int] = {}
    row_offset = 0
    null_cells = 0
    total_cells = 0
    started = time.perf_counter()
    try:
        for chunk_number, raw_chunk in enumerate(iter_data_chunks(source, args.chunksize), start=1):
            cleaned, stats = clean_chunk(
                raw_chunk,
                source_file=source.path.name,
                row_offset=row_offset,
                stats=stats,
            )
            row_offset += len(raw_chunk)
            within_chunk = ~cleaned["record_hash"].duplicated(keep="first")
            stats["duplicate_rows"] = stats.get("duplicate_rows", 0) + int((~within_chunk).sum())
            cleaned = cleaned.loc[within_chunk].reset_index(drop=True)
            keep_mask, cross_chunk_duplicates = _new_hashes(dedup, cleaned["record_hash"].tolist())
            stats["duplicate_rows"] += cross_chunk_duplicates
            cleaned = cleaned.loc[keep_mask].reset_index(drop=True)
            stats["clean_rows"] = stats.get("clean_rows", 0) + len(cleaned)
            null_cells += int(cleaned.isna().sum().sum())
            total_cells += int(cleaned.shape[0] * cleaned.shape[1])
            if not cleaned.empty:
                table = pa.Table.from_pandas(
                    cleaned,
                    schema=PARQUET_SCHEMA,
                    preserve_index=False,
                    safe=False,
                )
                writer.write_table(table, row_group_size=args.chunksize)
            print(
                f"Cleaned chunk {chunk_number}: raw={stats['raw_rows']:,}, "
                f"clean={stats['clean_rows']:,}, duplicates={stats.get('duplicate_rows', 0):,}"
            )
        writer.close()
        writer = None
        os.replace(temporary_output, output)
    except Exception:
        if writer is not None:
            writer.close()
        if temporary_output.exists():
            temporary_output.unlink()
        raise
    finally:
        dedup.close()
        for candidate in (dedup_path, Path(f"{dedup_path}-wal"), Path(f"{dedup_path}-shm")):
            if candidate.exists():
                candidate.unlink()

    elapsed = time.perf_counter() - started
    _write_quality_report(
        report_path,
        source.path,
        output,
        stats,
        null_cells,
        total_cells,
        source.missing_columns,
        elapsed,
    )
    print(f"Original rows: {stats.get('raw_rows', 0):,}")
    print(f"Exact duplicates removed: {stats.get('duplicate_rows', 0):,}")
    print(f"Clean rows: {stats.get('clean_rows', 0):,}")
    print(f"Parquet: {output}")
    print(f"Quality report: {report_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunked medical data cleaner")
    parser.add_argument("--input", help="CSV, TSV or Parquet source; auto-detected when omitted")
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "data" / "processed" / "hospital_discharges_clean.parquet"),
    )
    parser.add_argument("--report", default=str(PROJECT_ROOT / "docs" / "data_quality_report.md"))
    parser.add_argument("--chunksize", type=int, default=50_000)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.chunksize < 1:
        parser.error("chunksize must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
