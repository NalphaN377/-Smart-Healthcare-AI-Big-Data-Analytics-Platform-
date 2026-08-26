import json
from pathlib import Path

import pytest

from app.ai_layer.intent import detect_intent
from app.service_layer.analysis import mining, registry


CATALOG = json.loads((Path(__file__).parents[1] / "config" / "ai_suggestions.json").read_text(encoding="utf-8"))
PATIENT_DIMENSIONS = {"disease", "year", "service_area"}
PATIENT_METRICS = {"count", "avg_length_of_stay", "avg_total_charges"}


@pytest.mark.parametrize(
    ("role", "question"),
    [(role, question) for role, questions in CATALOG.items() for question in questions],
)
def test_visible_ai_suggestion_is_executable_for_role(role, question):
    intent = detect_intent(question)
    assert intent["status"] == "ready", (question, intent)
    if intent.get("topic"):
        assert role in mining.TOPIC_ROLES[intent["topic"]]
        return
    registry.require_dimension(intent["dimension"], role)
    for metric in intent["metrics"]:
        registry.require_metric(metric, role)
    if role == "patient":
        assert intent["dimension"] in PATIENT_DIMENSIONS
        assert set(intent["metrics"]) <= PATIENT_METRICS
