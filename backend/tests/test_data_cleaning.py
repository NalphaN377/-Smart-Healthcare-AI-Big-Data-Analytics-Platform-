from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from backend.app.utils.cleaning import clean_chunk
from backend.app.utils.columns import OUTPUT_COLUMNS
from backend.scripts.clean_data import run


FIXTURE = Path(__file__).parent / "fixtures" / "medical_sample.csv"


def cleaned_fixture():
    raw = pd.read_csv(FIXTURE, dtype=str, keep_default_na=False)
    return clean_chunk(raw, FIXTURE.name)[0]


def test_required_fields_and_types_are_normalized():
    cleaned = cleaned_fixture()
    assert list(cleaned.columns) == OUTPUT_COLUMNS
    assert str(cleaned["length_of_stay"].dtype) == "Int64"
    assert str(cleaned["emergency_indicator"].dtype) == "boolean"
    assert str(cleaned["total_charges"].dtype) == "Float64"


def test_money_stay_year_and_boolean_rules():
    cleaned = cleaned_fixture()
    assert cleaned.loc[0, "total_charges"] == 1200.50
    assert cleaned.loc[4, "length_of_stay_raw"] == "120+"
    assert cleaned.loc[4, "length_of_stay"] == 120
    assert pd.isna(cleaned.loc[2, "length_of_stay"])
    assert pd.isna(cleaned.loc[2, "discharge_year"])
    assert pd.isna(cleaned.loc[2, "emergency_indicator"])
    assert not (cleaned["total_charges"].dropna() < 0).any()
    assert not (cleaned["total_costs"].dropna() < 0).any()


def test_birth_weight_is_only_kept_for_newborns():
    cleaned = cleaned_fixture()
    assert cleaned.loc[1, "birth_weight"] == 3200
    assert pd.isna(cleaned.loc[0, "birth_weight"])
    assert pd.isna(cleaned.loc[2, "birth_weight"])


def test_duplicate_rows_have_same_record_hash():
    cleaned = cleaned_fixture()
    assert cleaned.loc[0, "record_hash"] == cleaned.loc[3, "record_hash"]
    assert cleaned["record_hash"].nunique() == 4


def test_chunked_pipeline_removes_exact_duplicates(tmp_path):
    output = tmp_path / "clean.parquet"
    report = tmp_path / "quality.md"
    status = run(
        Namespace(
            input=str(FIXTURE),
            output=str(output),
            report=str(report),
            chunksize=2,
            overwrite=False,
        )
    )
    assert status == 0
    parquet = pq.ParquetFile(output)
    assert parquet.metadata.num_rows == 4
    assert len(set(parquet.read(columns=["record_hash"])["record_hash"].to_pylist())) == 4
    assert "Reconciled: **True**" in report.read_text(encoding="utf-8")

