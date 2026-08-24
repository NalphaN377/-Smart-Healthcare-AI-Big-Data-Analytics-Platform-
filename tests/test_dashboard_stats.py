from app.service_layer.analysis import aggregation, dashboard_stats


def test_preaggregated_dimension_contract(monkeypatch):
    calls = []

    def query(sql, params=()):
        calls.append((sql, params))
        if "system_state analytics" in sql:
            return [{"is_current": 1}]
        return [{"dimension_value": "2024", "count": 100, "avg_total_charges": 20.0}]

    monkeypatch.setattr(aggregation, "_run_query", query)
    result = aggregation.aggregate("year", ["count", "avg_total_charges"], filters={})
    assert result["engine"] == "sqlserver_preaggregated"
    assert result["rows"][0]["dimension_value"] == 2024
    assert "analytics_dimension_stat" in calls[-1][0]


def test_stats_only_accept_empty_or_service_area_filter():
    assert dashboard_stats.scope_for({}) == dashboard_stats.ALL_SCOPE
    assert dashboard_stats.scope_for({"service_area": "NYC"}) == "NYC"
    assert dashboard_stats.scope_for({"year": 2024}) is None


def test_stale_stats_fall_back_to_business_table(monkeypatch):
    queries = []

    def query(sql, params=()):
        queries.append(sql)
        if "system_state analytics" in sql:
            return [{"is_current": 0}]
        return [{"dimension_value": "F", "count": 10}]

    monkeypatch.setattr(aggregation, "_run_query", query)
    result = aggregation.aggregate("gender", ["count"])
    assert "engine" not in result
    assert any("FROM dbo.inpatient_discharge" in sql for sql in queries)


def test_batch_merge_is_scoped_to_new_ingestion():
    sql = dashboard_stats.batch_merge_sql(42)
    assert "source_batch_id=42" in sql
    assert "analytics_data_version" in sql
    assert "MERGE dbo.analytics_summary_stat" in sql
    assert "MERGE dbo.analytics_dimension_stat" in sql
