import pytest
from pydantic import ValidationError

from backend.app.ai.schemas import ChartSpec, DiseaseTopQuery


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
