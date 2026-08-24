import csv

from app.common import cache
from scripts.incremental_ingest_sqlserver import build_incremental_sql, read_and_validate_header


CANONICAL_COLUMNS = [
    "Hospital Service Area", "Hospital County", "Operating Certificate Number", "Permanent Facility Id",
    "Facility Name", "Age Group", "Zip Code - 3 digits", "Gender", "Race", "Ethnicity",
    "Length of Stay", "Type of Admission", "Patient Disposition", "Discharge Year",
    "CCSR Diagnosis Code", "CCSR Diagnosis Description", "CCSR Procedure Code",
    "CCSR Procedure Description", "APR DRG Code", "APR DRG Description", "APR MDC Code",
    "APR MDC Description", "APR Severity of Illness Code", "APR Severity of Illness Description",
    "APR Risk of Mortality", "APR Medical Surgical Description", "Payment Typology 1",
    "Payment Typology 2", "Payment Typology 3", "Birth Weight", "Emergency Department Indicator",
    "Total Charges", "Total Costs",
]


def test_2024_header_aliases_are_accepted(tmp_path):
    columns = list(CANONICAL_COLUMNS)
    columns[0] = "Health Service Area"
    columns[6] = "Zip Code"
    path = tmp_path / "2024.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerow(columns)
    assert read_and_validate_header(path) == columns


def test_incremental_sql_is_idempotent_and_never_truncates_business_table(tmp_path):
    path = tmp_path / "year.csv"
    sql = build_incremental_sql(path, 9)
    assert "source_row_hash" in sql
    assert "NOT EXISTS" in sql
    assert "sp_getapplock" in sql
    assert "TRUNCATE TABLE dbo.inpatient_discharge;" not in sql
    assert "source_batch_id, 9" not in sql  # 列名与值分别位于 INSERT / SELECT，避免拼接错位。


class FakeRedis:
    def __init__(self):
        self.values = {"yiliaoBigData:system:data_version": "7"}

    def ping(self):
        return True

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = str(value)

    def setex(self, key, _ttl, value):
        self.values[key] = value


def test_cache_aside_hits_on_second_call(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setitem(cache.FEATURES, "redis_cache", True)
    monkeypatch.setattr(cache, "_client", fake)
    monkeypatch.setattr(cache, "_connection_attempted", True)
    calls = []

    first, first_hit = cache.remember("aggregate", {"role": "doctor", "year": 2024}, lambda: calls.append(1) or {"rows": [1]})
    second, second_hit = cache.remember("aggregate", {"role": "doctor", "year": 2024}, lambda: calls.append(2) or {})

    assert first == second == {"rows": [1]}
    assert first_hit is False
    assert second_hit is True
    assert calls == [1]
