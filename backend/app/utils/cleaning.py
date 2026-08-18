from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .columns import BUSINESS_COLUMNS, OUTPUT_COLUMNS, SOURCE_COLUMNS, resolve_columns


NULL_TOKENS = {"", "na", "n/a", "nan", "null", "none", "unknown", "not available", "-"}
INTEGER_COLUMNS = [
    "facility_id",
    "apr_drg_code",
    "apr_mdc_code",
    "severity_code",
]
CATEGORY_COLUMNS = [
    column
    for column in SOURCE_COLUMNS
    if column
    not in {
        "length_of_stay",
        "discharge_year",
        "birth_weight",
        "emergency_indicator",
        "total_charges",
        "total_costs",
        *INTEGER_COLUMNS,
    }
]


def _add(stats: dict[str, int], key: str, value: int) -> None:
    stats[key] = stats.get(key, 0) + int(value)


def clean_text(series: pd.Series) -> pd.Series:
    result = series.astype("string").str.normalize("NFKC")
    result = result.str.replace(r"[\x00-\x1f\x7f]", " ", regex=True)
    result = result.str.replace(r"\s+", " ", regex=True).str.strip()
    folded = result.str.casefold()
    return result.mask(folded.isin(NULL_TOKENS), pd.NA)


def _canonical_frame(raw: pd.DataFrame) -> pd.DataFrame:
    mapping, _ = resolve_columns([str(column) for column in raw.columns])
    canonical = pd.DataFrame(index=raw.index)
    for raw_name, canonical_name in mapping.items():
        values = raw[raw_name]
        if canonical_name in canonical:
            canonical[canonical_name] = canonical[canonical_name].where(
                canonical[canonical_name].astype("string").str.strip().ne(""), values
            )
        else:
            canonical[canonical_name] = values
    for column in SOURCE_COLUMNS:
        if column not in canonical:
            canonical[column] = pd.NA
    return canonical[SOURCE_COLUMNS]


def _clean_money(series: pd.Series, field: str, stats: dict[str, int]) -> pd.Series:
    text = clean_text(series)
    text = text.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    text = text.str.replace(r"[^0-9.\-]+", "", regex=True).replace("", pd.NA)
    numeric = pd.to_numeric(text, errors="coerce")
    invalid = series.astype("string").str.strip().ne("") & numeric.isna()
    negative = numeric.lt(0)
    _add(stats, f"invalid_{field}", invalid.sum())
    _add(stats, f"negative_{field}", negative.sum())
    return numeric.mask(negative).astype("Float64")


def _clean_integer(series: pd.Series, field: str, stats: dict[str, int]) -> pd.Series:
    text = clean_text(series).str.replace(r"\.0$", "", regex=True)
    numeric = pd.to_numeric(text, errors="coerce")
    invalid = text.notna() & (numeric.isna() | numeric.lt(0) | numeric.mod(1).ne(0))
    _add(stats, f"invalid_{field}", invalid.sum())
    return numeric.mask(invalid).astype("Int64")


def _record_hash(frame: pd.DataFrame) -> pd.Series:
    values = frame[BUSINESS_COLUMNS].astype("string").fillna("<NULL>")
    first = pd.util.hash_pandas_object(
        values, index=False, hash_key="medplatformkey01", categorize=True
    ).astype("uint64")
    second = pd.util.hash_pandas_object(
        values, index=False, hash_key="medplatformkey02", categorize=True
    ).astype("uint64")
    return pd.Series(
        [f"{left:016x}{right:016x}" for left, right in zip(first, second)],
        index=frame.index,
        dtype="string",
    )


def clean_chunk(
    raw: pd.DataFrame,
    source_file: str,
    row_offset: int = 0,
    stats: dict[str, int] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    counters = stats if stats is not None else {}
    frame = _canonical_frame(raw)
    _add(counters, "raw_rows", len(frame))

    frame["length_of_stay_raw"] = clean_text(frame["length_of_stay"])
    for column in CATEGORY_COLUMNS:
        frame[column] = clean_text(frame[column])

    for column in INTEGER_COLUMNS:
        frame[column] = _clean_integer(frame[column], column, counters)

    stay_text = frame["length_of_stay_raw"]
    stay_number = pd.to_numeric(stay_text.str.extract(r"(-?\d+)", expand=False), errors="coerce")
    invalid_stay = stay_text.notna() & (stay_number.isna() | stay_number.lt(0) | stay_number.gt(3650))
    _add(counters, "invalid_length_of_stay", invalid_stay.sum())
    frame["length_of_stay"] = stay_number.mask(invalid_stay).astype("Int64")

    year = pd.to_numeric(clean_text(frame["discharge_year"]), errors="coerce")
    max_year = datetime.now().year + 1
    invalid_year = year.notna() & (~year.between(1900, max_year) | year.mod(1).ne(0))
    _add(counters, "invalid_discharge_year", invalid_year.sum())
    frame["discharge_year"] = year.mask(invalid_year).astype("Int64")

    frame["total_charges"] = _clean_money(frame["total_charges"], "total_charges", counters)
    frame["total_costs"] = _clean_money(frame["total_costs"], "total_costs", counters)

    birth_weight = pd.to_numeric(
        clean_text(frame["birth_weight"]).str.replace(",", "", regex=False), errors="coerce"
    )
    newborn_context = (
        frame["admission_type"].fillna("")
        + " "
        + frame["apr_mdc_description"].fillna("")
        + " "
        + frame["apr_drg_description"].fillna("")
    ).str.casefold()
    is_newborn = newborn_context.str.contains(r"newborn|neonate|liveborn|birth", regex=True)
    invalid_birth_weight = birth_weight.notna() & (
        ~is_newborn | birth_weight.le(0) | birth_weight.gt(15_000)
    )
    _add(counters, "birth_weight_cleared", invalid_birth_weight.sum())
    frame["birth_weight"] = birth_weight.mask(invalid_birth_weight).astype("Int64")

    emergency_text = clean_text(frame["emergency_indicator"]).str.casefold()
    boolean_map: dict[str, Any] = {
        "y": True,
        "yes": True,
        "true": True,
        "1": True,
        "是": True,
        "n": False,
        "no": False,
        "false": False,
        "0": False,
        "否": False,
    }
    emergency = emergency_text.map(boolean_map)
    invalid_emergency = emergency_text.notna() & emergency.isna()
    _add(counters, "invalid_emergency_indicator", invalid_emergency.sum())
    frame["emergency_indicator"] = emergency.astype("boolean")

    frame["source_file"] = source_file
    frame["source_row_number"] = pd.Series(
        range(row_offset + 1, row_offset + len(frame) + 1), index=frame.index, dtype="Int64"
    )
    frame["record_hash"] = _record_hash(frame)
    return frame[OUTPUT_COLUMNS], counters
