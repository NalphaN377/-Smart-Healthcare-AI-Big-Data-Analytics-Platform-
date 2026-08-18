#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.utils.cleaning import clean_chunk  # noqa: E402
from backend.app.utils.columns import BUSINESS_COLUMNS, IMPORTANT_COLUMNS  # noqa: E402
from backend.app.utils.data_io import discover_data_file, iter_data_chunks  # noqa: E402


NUMERIC_COLUMNS = {
    "facility_id",
    "length_of_stay",
    "discharge_year",
    "apr_drg_code",
    "apr_mdc_code",
    "severity_code",
    "birth_weight",
    "total_charges",
    "total_costs",
}


@dataclass
class ColumnProfile:
    total: int = 0
    missing: int = 0
    dtypes: set[str] = field(default_factory=set)
    unique_values: set[str] = field(default_factory=set)
    unique_capped: bool = False
    top_values: Counter[str] = field(default_factory=Counter)
    numeric_count: int = 0
    numeric_sum: float = 0.0
    numeric_sum_squares: float = 0.0
    numeric_min: float = math.inf
    numeric_max: float = -math.inf

    def update(self, series: pd.Series, track_top: bool, unique_limit: int = 50_000) -> None:
        self.total += len(series)
        self.missing += int(series.isna().sum())
        self.dtypes.add(str(series.dtype))
        present = series.dropna()
        if not self.unique_capped:
            values = present.astype("string").unique().tolist()
            remaining = unique_limit - len(self.unique_values)
            self.unique_values.update(str(value) for value in values[: max(remaining, 0)])
            if len(values) > remaining:
                self.unique_capped = True
        if track_top:
            counts = present.astype("string").value_counts().head(100)
            self.top_values.update({str(key): int(value) for key, value in counts.items()})
            if len(self.top_values) > 500:
                self.top_values = Counter(dict(self.top_values.most_common(200)))

    def update_numeric(self, series: pd.Series) -> None:
        values = pd.to_numeric(series, errors="coerce").dropna().astype(float)
        if values.empty:
            return
        self.numeric_count += len(values)
        self.numeric_sum += float(values.sum())
        self.numeric_sum_squares += float((values * values).sum())
        self.numeric_min = min(self.numeric_min, float(values.min()))
        self.numeric_max = max(self.numeric_max, float(values.max()))

    def unique_display(self) -> str:
        suffix = "+（下限）" if self.unique_capped else ""
        return f"{len(self.unique_values):,}{suffix}"

    def numeric_summary(self) -> str:
        if not self.numeric_count:
            return "-"
        mean = self.numeric_sum / self.numeric_count
        variance = max(self.numeric_sum_squares / self.numeric_count - mean * mean, 0)
        return (
            f"count={self.numeric_count:,}, min={self.numeric_min:,.2f}, "
            f"mean={mean:,.2f}, max={self.numeric_max:,.2f}, std={math.sqrt(variance):,.2f}"
        )


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def write_missing_report(output: Path, message: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "# Data Profile\n\n"
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}\n"
        "- Status: **BLOCKED — required field missing / source dataset not found**\n"
        f"- Detail: `{message}`\n\n"
        "No row counts or medical statistics were fabricated. Confirm that an existing CSV, TSV, "
        "or Parquet file is readable somewhere under the repository root, then rerun "
        "`python backend/scripts/inspect_data.py`.\n",
        encoding="utf-8",
    )


def build_report(args: argparse.Namespace) -> int:
    output = Path(args.output).resolve()
    try:
        source = discover_data_file(args.input)
    except (FileNotFoundError, ValueError) as exc:
        write_missing_report(output, str(exc))
        print(f"Data audit blocked: {exc}", file=sys.stderr)
        print(f"Report written: {output}")
        return 2

    profiles = {column: ColumnProfile() for column in BUSINESS_COLUMNS}
    total_rows = 0
    tracked_hashes: set[str] = set()
    duplicate_observations = 0
    duplicate_rows_tracked = 0
    duplicate_tracking_limit = args.duplicate_sample
    anomaly_counts: dict[str, int] = {}

    for chunk_number, raw_chunk in enumerate(iter_data_chunks(source, args.chunksize), start=1):
        cleaned, anomaly_counts = clean_chunk(
            raw_chunk,
            source_file=source.path.name,
            row_offset=total_rows,
            stats=anomaly_counts,
        )
        for column, profile in profiles.items():
            profile.update(cleaned[column], track_top=column in IMPORTANT_COLUMNS)
            if column in NUMERIC_COLUMNS:
                profile.update_numeric(cleaned[column])

        if len(tracked_hashes) < duplicate_tracking_limit:
            hashes = cleaned["record_hash"].tolist()
            for value in hashes:
                if duplicate_rows_tracked >= duplicate_tracking_limit:
                    break
                duplicate_rows_tracked += 1
                if value in tracked_hashes:
                    duplicate_observations += 1
                else:
                    tracked_hashes.add(value)

        total_rows += len(raw_chunk)
        print(f"Profiled chunk {chunk_number}: {total_rows:,} rows")

    duplicate_rate = duplicate_observations / duplicate_rows_tracked if duplicate_rows_tracked else 0
    mapped_pairs = "\n".join(
        f"- `{_escape(raw)}` → `{canonical}`" for raw, canonical in source.column_mapping.items()
    ) or "- No required columns mapped"
    missing_lines = "\n".join(f"- `{column}` — Required field missing" for column in source.missing_columns)
    if not missing_lines:
        missing_lines = "- None"

    table_rows = []
    for column, profile in profiles.items():
        missing_rate = profile.missing / profile.total if profile.total else 0
        table_rows.append(
            "| {name} | {dtype} | {missing:,} | {rate:.2%} | {unique} | {numeric} |".format(
                name=column,
                dtype=", ".join(sorted(profile.dtypes)) or "unknown",
                missing=profile.missing,
                rate=missing_rate,
                unique=profile.unique_display(),
                numeric=_escape(profile.numeric_summary()),
            )
        )

    top_sections = []
    for column in sorted(IMPORTANT_COLUMNS):
        values = profiles[column].top_values.most_common(10)
        rendered = ", ".join(f"`{_escape(key)}` ({count:,})" for key, count in values) or "No non-null values"
        top_sections.append(f"### {column}\n\n{rendered}")

    anomalies = "\n".join(
        f"- `{key}`: {value:,}" for key, value in sorted(anomaly_counts.items()) if key != "raw_rows"
    ) or "- No rule violations detected"
    facility_profile = profiles["facility_name"]
    facility_count = facility_profile.unique_display()

    report = f"""# Data Profile

- Generated: {datetime.now().isoformat(timespec='seconds')}
- File path: `{source.path}`
- File size: {source.size_bytes / 1024 / 1024:,.2f} MiB
- Format: {source.file_format}
- Encoding: {source.encoding or 'n/a'}
- Delimiter: `{source.delimiter or 'n/a'}`
- Total rows: {total_rows:,}
- Source field count: {len(source.columns)}
- Mapped medical field count: {len(source.column_mapping)} / {len(BUSINESS_COLUMNS) - 1}

## Source fields

{', '.join(f'`{_escape(column)}`' for column in source.columns)}

## Column mapping

{mapped_pairs}

## Required fields missing

{missing_lines}

## Metric definitions

- Medical institution count: **{facility_count}**
- Definition: case-sensitive distinct cleaned, non-null and non-empty `facility_name`; `facility_id` is not used for this metric.

## Column statistics

| Internal field | Observed type | Missing | Missing rate | Unique values | Numeric statistics |
|---|---:|---:|---:|---:|---|
{chr(10).join(table_rows)}

Unique counts marked “下限” reached the {50_000:,}-value memory cap. Numeric statistics are calculated from normalized values.

## Categorical Top values

{chr(10).join(top_sections)}

## Duplicate estimate

- Rows examined for duplicate estimation: {duplicate_rows_tracked:,}
- Duplicate rows observed: {duplicate_observations:,}
- Estimated duplicate rate in the tracked prefix: {duplicate_rate:.4%}
- Method: stable full-business-row hash, capped at {duplicate_tracking_limit:,} rows to bound memory.

## Anomalies

{anomalies}
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Report written: {output}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunked medical source data profiler")
    parser.add_argument("--input", help="CSV, TSV or Parquet file; auto-detected when omitted")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "docs" / "data_profile.md"))
    parser.add_argument("--chunksize", type=int, default=50_000)
    parser.add_argument("--duplicate-sample", type=int, default=1_000_000)
    args = parser.parse_args()
    if args.chunksize < 1 or args.duplicate_sample < 1:
        parser.error("chunksize and duplicate-sample must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(build_report(parse_args()))
