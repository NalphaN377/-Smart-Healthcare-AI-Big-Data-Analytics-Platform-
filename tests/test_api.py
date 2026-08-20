import json

import pytest

from app.service_layer.app import create_app
from app.service_layer.analysis import aggregation
from app.data_layer import storage
from config import LLM_CONFIG


@pytest.fixture()
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_contract(client, monkeypatch):
    monkeypatch.setattr(storage, "ping", lambda: {"database": "test", "version": "SQL Server test"})
    response = client.get("/api/health")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["database"]["connected"] is True
    assert "elapsed_ms" in payload["meta"]


def test_invalid_aggregate_inputs_return_400(client):
    assert client.get("/api/aggregate?dimension=unsafe_column").status_code == 400
    assert client.get("/api/aggregate?limit=101").status_code == 400
    assert client.get("/api/aggregate?metrics=drop_table").status_code == 400


def test_data_quality_contract(client, monkeypatch):
    monkeypatch.setattr(storage, "latest_ingestion", lambda: {"status": "completed", "quality": {"overall": 0.99}})
    payload = client.get("/api/data-quality").get_json()
    assert payload["data"]["quality"]["overall"] == 0.99


def test_sse_chat_has_context_delta_and_done(client, monkeypatch):
    monkeypatch.setitem(LLM_CONFIG, "api_key", "")
    monkeypatch.setattr(aggregation, "aggregate", lambda *args, **kwargs: {
        "dimension": "age_group", "dimension_label": "年龄段", "metrics": ["count"],
        "rows": [{"dimension_value": "50 to 69", "count": 20}],
    })
    response = client.post("/api/chat/stream", json={"query": "不同年龄段住院量"})
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert "event: context" in body
    assert "event: delta" in body
    assert "event: done" in body
    done_line = next(line for block in body.split("\n\n") if "event: done" in block for line in block.splitlines() if line.startswith("data: "))
    assert json.loads(done_line[6:])["summary"]


def test_phase2_contract(client):
    response = client.get("/api/v2/predictions")
    assert response.status_code == 501
    assert response.get_json()["meta"] == {"phase": 2, "enabled": False}
    assert client.get("/api/v2/unknown").status_code == 404

