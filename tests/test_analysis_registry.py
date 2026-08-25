import pytest

from app.service_layer.analysis import aggregation, mining, registry


def test_admin_financial_metric_is_not_available_to_doctor_or_patient():
    assert "charge_cost_spread_ratio" in registry.metrics_for("admin")
    assert "charge_cost_spread_ratio" not in registry.metrics_for("doctor")
    assert "charge_cost_spread_ratio" not in registry.metrics_for("patient")
    with pytest.raises(PermissionError, match="收费成本差额率"):
        registry.require_metric("charge_cost_spread_ratio", "doctor")


def test_patient_catalog_is_restricted_and_sensitive_groups_are_suppressed(monkeypatch):
    assert set(registry.dimensions_for("patient")) == {"disease", "service_area", "year"}
    calls = []
    monkeypatch.setattr(aggregation, "_aggregate_from_stats", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(aggregation, "_run_query", lambda sql, params=(): calls.append((sql, params)) or [])
    result = aggregation.aggregate("disease", ["count"], role="patient")
    assert "HAVING COUNT_BIG(*)>=11" in calls[-1][0]
    assert result["suppression_threshold"] == 11


def test_two_dimensions_use_only_registry_expressions_and_parameterized_filters(monkeypatch):
    calls = []
    monkeypatch.setattr(aggregation, "_run_query", lambda sql, params=(): calls.append((sql, params)) or [
        {"year": 2024, "age_group": "50-69", "count": 2},
    ])
    result = aggregation.aggregate(
        ["year", "age_group"], ["count"], filters={"service_area": "Capital/Adirond"}, role="admin",
    )
    sql, params = calls[-1]
    assert "CASE" in sql and "GROUP BY" in sql
    assert sql.count("%s") == 1
    assert params == ["Capital/Adirondacks"]
    assert result["rows"][0]["dimension_value"] == "2024 | 50-69"


def test_specialized_topics_enforce_role_boundaries():
    with pytest.raises(PermissionError):
        mining.topic_analysis("hospital_benchmark", role="doctor")
    with pytest.raises(PermissionError):
        mining.topic_analysis("data_quality", role="patient")
    with pytest.raises(PermissionError):
        mining.topic_analysis("demographic", role="patient")


def test_case_mix_benchmark_is_parameterized_and_has_chart_dimension(monkeypatch):
    captured = {}
    monkeypatch.setattr(aggregation, "_run_query", lambda sql, params=(): captured.update(sql=sql, params=list(params)) or [
        {"hospital": "HOSPITAL A", "case_count": 100, "case_mix_cost_index": 1.1,
         "case_mix_los_index": 0.9, "avg_actual_cost": 10, "avg_expected_cost": 9},
    ])
    result = mining.case_mix_adjusted_hospitals(
        filters={"year": 2024, "hospital": "Hospital A"}, role="admin", limit=5,
    )
    assert "Hospital A" not in captured["sql"]
    assert captured["params"] == [2024, 2024, "HOSPITAL A"]
    assert result["rows"][0]["dimension_value"] == "HOSPITAL A"


def test_growth_ranking_compares_first_and_last_available_year(monkeypatch):
    monkeypatch.setattr(aggregation, "_run_query", lambda *_args, **_kwargs: [
        {"year": 2021, "dimension_value": "A", "count": 100, "metric_value": 1000},
        {"year": 2024, "dimension_value": "A", "count": 120, "metric_value": 1500},
        {"year": 2021, "dimension_value": "B", "count": 100, "metric_value": 2000},
        {"year": 2024, "dimension_value": "B", "count": 120, "metric_value": 2400},
    ])
    result = mining.growth_ranking("disease", "sum_total_costs", role="admin")
    assert [row["dimension_value"] for row in result["rows"]] == ["A", "B"]
    assert result["rows"][0]["growth_pct"] == 50.0
    assert result["rows"][0]["absolute_growth"] == 500.0
    assert result["source_metric"] == "sum_total_costs"
