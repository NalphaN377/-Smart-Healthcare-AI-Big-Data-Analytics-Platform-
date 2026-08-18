import pytest
from pydantic import ValidationError

from backend.app.ai.schemas import ChartSpec, DiseaseTopQuery, TokenUsage


@pytest.mark.parametrize("limit", [0, 51, 1.5, "five"])
def test_tool_limit_is_strictly_bounded(limit):
    with pytest.raises(ValidationError):
        DiseaseTopQuery.model_validate({"limit": limit})


def test_tool_schema_rejects_extra_and_invalid_filters():
    with pytest.raises(ValidationError):
        DiseaseTopQuery.model_validate({"limit": 5, "sql": "DROP TABLE x"})
    with pytest.raises(ValidationError):
        DiseaseTopQuery.model_validate({"age_group": "senior"})
    with pytest.raises(ValidationError):
        DiseaseTopQuery.model_validate({"hospital": "bad\x00name"})


def test_chart_spec_rejects_arbitrary_types_and_unknown_fields():
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({"type": "javascript", "title": "bad", "data": []})
    with pytest.raises(ValidationError):
        ChartSpec.model_validate(
            {
                "type": "bar",
                "title": "bad field",
                "x_field": "label",
                "series": [{"name": "数量", "field": "missing"}],
                "data": [{"label": "A", "count": 1}],
            }
        )


def test_unavailable_chart_cannot_smuggle_data():
    with pytest.raises(ValidationError):
        ChartSpec.model_validate(
            {
                "type": "line",
                "status": "unavailable",
                "title": "趋势",
                "data": [{"year": 2021}],
                "message": "unavailable",
            }
        )


def test_token_usage_combines_routing_and_summary_without_negative_values():
    routing = TokenUsage(input_tokens=100, output_tokens=10, total_tokens=110)
    summary = TokenUsage(
        input_tokens=200,
        output_tokens=40,
        total_tokens=240,
        cache_read_tokens=80,
    )
    combined = routing + summary
    assert combined.model_dump() == {
        "input_tokens": 300,
        "output_tokens": 50,
        "total_tokens": 350,
        "cache_read_tokens": 80,
        "cache_miss_tokens": 0,
    }

    with pytest.raises(ValidationError):
        TokenUsage(total_tokens=-1)
