from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd
import pyarrow.parquet as pq

from .columns import resolve_columns


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".parquet"}


@dataclass(frozen=True)
class SourceInfo:
    path: Path
    file_format: str
    size_bytes: int
    columns: list[str]
    column_mapping: dict[str, str]
    missing_columns: list[str]
    delimiter: str | None = None
    encoding: str | None = None


def _sniff_text(path: Path) -> tuple[str, str, list[str]]:
    sample = path.read_bytes()[:131_072]
    encoding = "utf-8-sig"
    decoded = ""
    for candidate in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            decoded = sample.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    if not decoded:
        decoded = sample.decode("utf-8", errors="replace")

    first_lines = "\n".join(decoded.splitlines()[:20])
    try:
        delimiter = csv.Sniffer().sniff(first_lines, delimiters=",\t;|").delimiter
    except csv.Error:
        counts = {candidate: first_lines.count(candidate) for candidate in (",", "\t", ";", "|")}
        delimiter = max(counts, key=counts.get)
    header = next(csv.reader([decoded.splitlines()[0]], delimiter=delimiter), []) if decoded.splitlines() else []
    return encoding, delimiter, [column.lstrip("\ufeff").strip() for column in header]


def inspect_source(path: str | Path) -> SourceInfo:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Data file not found: {source}")
    suffix = source.suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported data format: {source.suffix}")

    if suffix == ".parquet":
        columns = pq.ParquetFile(source).schema_arrow.names
        encoding = delimiter = None
        file_format = "parquet"
    else:
        encoding, delimiter, columns = _sniff_text(source)
        file_format = "tsv" if delimiter == "\t" else "csv"

    mapping, missing = resolve_columns(list(columns))
    return SourceInfo(
        path=source,
        file_format=file_format,
        size_bytes=source.stat().st_size,
        columns=list(columns),
        column_mapping=mapping,
        missing_columns=missing,
        delimiter=delimiter,
        encoding=encoding,
    )


def _project_candidates(project_root: Path) -> list[Path]:
    candidates: list[Path] = []
    excluded_names = {".git", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache"}
    excluded_subtrees = {("data", "processed"), ("backend", "tests")}

    for directory, child_directories, filenames in os.walk(project_root, followlinks=False):
        current = Path(directory)
        relative_parts = current.relative_to(project_root).parts
        if any(relative_parts[: len(subtree)] == subtree for subtree in excluded_subtrees):
            child_directories[:] = []
            continue
        child_directories[:] = [name for name in child_directories if name not in excluded_names]
        for filename in filenames:
            path = current / filename
            if not path.is_symlink() and path.suffix.casefold() in SUPPORTED_SUFFIXES:
                candidates.append(path)
    return candidates


def discover_data_file(
    explicit: str | Path | None = None, project_root: str | Path | None = None
) -> SourceInfo:
    if explicit:
        return inspect_source(explicit)

    root = Path(project_root).expanduser().resolve() if project_root else PROJECT_ROOT
    candidates = _project_candidates(root)
    if not candidates:
        raise FileNotFoundError(
            f"No CSV, TSV or Parquet medical dataset found recursively under {root}. "
            "The scan excludes generated data/processed, tests, dependencies and Git internals."
        )

    inspected: list[SourceInfo] = []
    errors: list[str] = []
    for candidate in candidates:
        try:
            inspected.append(inspect_source(candidate))
        except (OSError, ValueError) as exc:
            errors.append(f"{candidate}: {exc}")
    if not inspected:
        raise ValueError("Candidate data files could not be inspected: " + "; ".join(errors))

    # Prefer the file whose header maps to the most required medical fields;
    # file size is only a tie breaker.
    return max(inspected, key=lambda info: (len(info.column_mapping), info.size_bytes))


def iter_data_chunks(source: SourceInfo, chunksize: int = 50_000) -> Iterator[pd.DataFrame]:
    if source.file_format == "parquet":
        parquet_file = pq.ParquetFile(source.path)
        for batch in parquet_file.iter_batches(batch_size=chunksize):
            yield batch.to_pandas()
        return

    yield from pd.read_csv(
        source.path,
        sep=source.delimiter,
        encoding=source.encoding,
        encoding_errors="replace",
        chunksize=chunksize,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        on_bad_lines="warn",
        low_memory=False,
    )
