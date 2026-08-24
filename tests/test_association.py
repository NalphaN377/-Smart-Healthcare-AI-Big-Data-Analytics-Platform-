import pytest

from app.service_layer.analysis import association


def test_association_contract_and_parameter_order(monkeypatch):
    captured = {}

    def fake_query(sql, params):
        captured.update(sql=sql, params=params)
        return [{"diagnosis_code": "DIG012", "procedure_code": "GIS006", "pair_count": 120}]

    monkeypatch.setattr(association, "_run_query", fake_query)
    result = association.disease_procedure_associations(
        limit=10, min_count=50, filters={"year": "2024"},
    )
    assert result["analysis_level"] == "discharge_primary_diagnosis_primary_procedure"
    assert result["rows"][0]["pair_count"] == 120
    assert captured["params"] == [2024, 50]
    assert "TOP 10" in captured["sql"]
    assert "SUM(pair_count) OVER" in captured["sql"]
    assert "dbo.disease_procedure_stat" in captured["sql"]
    assert result["engine"] == "sqlserver_preaggregated"


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"min_count": 10}])
def test_association_rejects_unsafe_limits(kwargs):
    with pytest.raises(ValueError):
        association.disease_procedure_associations(**kwargs)


def test_association_rejects_non_preaggregated_filter():
    with pytest.raises(ValueError, match="仅支持 year"):
        association.disease_procedure_associations(filters={"gender": "F"})


def test_refresh_uses_long_task_and_returns_status(monkeypatch):
    called = {}
    monkeypatch.setattr(association.storage, "init_schema", lambda: None)
    monkeypatch.setattr(association.storage, "get_data_version", lambda: 4)
    monkeypatch.setattr(association, "run_long_sql", lambda sql: called.update(sql=sql))
    monkeypatch.setattr(association, "association_status", lambda: {"pair_groups": 12})
    result = association.refresh_association_stats()
    assert result == {"refreshed": True, "pair_groups": 12}
    assert "TRUNCATE TABLE dbo.disease_procedure_stat" in called["sql"]
    assert "association_data_version" in called["sql"]
