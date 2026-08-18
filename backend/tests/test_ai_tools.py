import pytest

from backend.app.ai.errors import ToolValidationFailure, UnsupportedQuery
from backend.app.ai.tools import ToolRegistry
from backend.tests.conftest import FakeAnalyticsRepository


EXPECTED_TOOLS = {
    "get_overview",
    "get_top_diseases",
    "get_disease_cost_analysis",
    "get_hospital_analysis",
    "get_age_analysis",
    "get_payment_distribution",
    "get_severity_analysis",
    "get_year_trend",
}


def test_registry_exposes_only_allowlisted_tools():
    registry = ToolRegistry(FakeAnalyticsRepository())
    assert {definition.name for definition in registry.definitions} == EXPECTED_TOOLS
    with pytest.raises(UnsupportedQuery):
        registry.execute("run_sql", {"sql": "SELECT 1"})


def test_top_diseases_uses_service_result_and_validated_limit():
    registry = ToolRegistry(FakeAnalyticsRepository())
    result = registry.execute("get_top_diseases", {"limit": 5, "age_group": "70 or Older"})
    assert len(result.data) == 5
    assert result.data[0] == {"diagnosis": "Disease 1", "record_count": 10}
    assert result.meta["filters"] == {"age_group": "70 or Older"}
    assert result.source.record_count == 4
    assert result.source.years == [2021]


def test_tool_argument_validation_occurs_before_repository_call():
    registry = ToolRegistry(FakeAnalyticsRepository())
    with pytest.raises(ToolValidationFailure):
        registry.execute("get_top_diseases", {"limit": 1_000_000})


def test_single_year_trend_is_explicitly_unavailable():
    registry = ToolRegistry(FakeAnalyticsRepository())
    result = registry.execute("get_year_trend", {})
    assert result.meta["trend_available"] is False
    assert result.meta["available_years"] == [2021]
    assert "无法形成跨年度趋势" in result.meta["message"]
