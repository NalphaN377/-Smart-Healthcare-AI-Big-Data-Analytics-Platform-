from backend.app.repositories.analytics_repository import AnalyticsRepository


def test_overview_counts_distinct_nonempty_facility_names(monkeypatch):
    repository = AnalyticsRepository({})
    captured = {}

    def fake_fetch_one(sql, values):
        captured["sql"] = " ".join(sql.split())
        captured["values"] = values
        return {"facility_count": 2}

    monkeypatch.setattr(repository, "_fetch_one", fake_fetch_one)

    assert repository.overview({})["facility_count"] == 2
    assert "COUNT(DISTINCT BINARY NULLIF(TRIM(facility_name), ''))" in captured["sql"]
    assert "COALESCE(CAST(facility_id" not in captured["sql"]
    assert captured["values"] == []
