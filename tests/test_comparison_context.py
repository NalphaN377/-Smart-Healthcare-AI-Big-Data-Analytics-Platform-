from app.service_layer.analysis import comparison


def test_region_comparison_uses_server_aggregate_and_patient_metrics(monkeypatch):
    captured = {}

    def fake_aggregate(dimension, metrics, limit, filters, role):
        captured.update(dimension=dimension, metrics=metrics, filters=filters, role=role)
        return {"rows": [
            {"service_area": "New York City", "count": 20},
            {"service_area": "Long Island", "count": 10},
        ]}

    monkeypatch.setattr(comparison.aggregation, "aggregate", fake_aggregate)
    result = comparison.trusted_comparison(
        "region", "New York City", "Long Island",
        filters={"service_area": "New York City", "year": 2024}, role="patient",
    )

    assert captured == {
        "dimension": "service_area",
        "metrics": ["count", "avg_length_of_stay", "avg_total_charges"],
        "filters": {"year": 2024},
        "role": "patient",
    }
    assert [row["count"] for row in result["rows"]] == [20, 10]


def test_hospital_comparison_requeries_trusted_summary(monkeypatch):
    monkeypatch.setattr(comparison.hospital_compare, "_summary", lambda hospital, _filters, _role: {
        "hospital": hospital, "count": 120, "avg_length_of_stay": 5.0,
    })
    result = comparison.trusted_comparison("hospital", "医院 A", "医院 B", role="patient")

    assert [row["hospital"] for row in result["rows"]] == ["医院 A", "医院 B"]
    assert result["analysis_type"] == "trusted_pair_comparison"
