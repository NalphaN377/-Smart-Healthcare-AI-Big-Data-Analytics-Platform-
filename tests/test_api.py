import json

import pytest

from app.service_layer.app import create_app
from app.service_layer.analysis import aggregation
from app.data_layer import storage
from app.auth import service as auth_service
from app.auth.permissions import permissions_for
from config import LLM_CONFIG


@pytest.fixture()
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def authenticated_client(monkeypatch, role="admin"):
    user = {
        "id": 1, "username": f"{role}_test", "display_name": "测试用户", "role": role,
        "email": None, "is_active": True, "must_change_password": False,
        "permissions": permissions_for(role),
    }
    monkeypatch.setattr(auth_service, "get_user", lambda _user_id: user)
    app = create_app()
    app.config.update(TESTING=True)
    test_client = app.test_client()
    with test_client.session_transaction() as auth_session:
        auth_session["user_id"] = user["id"]
        auth_session["csrf_token"] = "test-csrf"
        auth_session["last_activity"] = 4_000_000_000
    return test_client


def test_health_contract(client, monkeypatch):
    monkeypatch.setattr(storage, "ping", lambda: {"database": "test", "version": "SQL Server test"})
    response = client.get("/api/health")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["code"] == 0
    assert payload["data"]["database"]["connected"] is True
    assert "elapsed_ms" in payload["meta"]


def test_protected_endpoint_requires_login(client):
    assert client.get("/api/aggregate").status_code == 401


def test_invalid_aggregate_inputs_return_400(monkeypatch):
    client = authenticated_client(monkeypatch)
    assert client.get("/api/aggregate?dimension=unsafe_column").status_code == 400
    assert client.get("/api/aggregate?limit=101").status_code == 400
    assert client.get("/api/aggregate?metrics=drop_table").status_code == 400


def test_data_quality_contract(monkeypatch):
    client = authenticated_client(monkeypatch, "doctor")
    monkeypatch.setattr(storage, "latest_ingestion", lambda: {"status": "completed", "quality": {"overall": 0.99}})
    payload = client.get("/api/data-quality").get_json()
    assert payload["data"]["quality"]["overall"] == 0.99


def test_sse_chat_has_context_delta_and_done(monkeypatch):
    from app.ai_layer import conversation as conversations

    client = authenticated_client(monkeypatch, "doctor")
    monkeypatch.setattr(conversations, "resolve", lambda *_args, **_kwargs: {"public_id": "00000000-0000-0000-0000-000000000001"})
    monkeypatch.setattr(conversations, "history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(conversations, "append_message", lambda *_args, **_kwargs: 1)
    monkeypatch.setitem(LLM_CONFIG, "api_key", "")
    monkeypatch.setattr(aggregation, "aggregate", lambda *args, **kwargs: {
        "dimension": "age_group", "dimension_label": "年龄段", "metrics": ["count"],
        "rows": [{"dimension_value": "50 to 69", "count": 20}],
    })
    response = client.post("/api/chat/stream", json={"query": "不同年龄段住院量"}, headers={"X-CSRF-Token": "test-csrf"})
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert "event: context" in body
    assert "event: delta" in body
    assert "event: done" in body
    done_line = next(line for block in body.split("\n\n") if "event: done" in block for line in block.splitlines() if line.startswith("data: "))
    assert json.loads(done_line[6:])["summary"]


def test_sse_unsupported_question_has_no_chart_or_data_query(monkeypatch):
    from app.ai_layer import agent as agent_module
    from app.ai_layer import conversation as conversations

    client = authenticated_client(monkeypatch, "doctor")
    monkeypatch.setattr(conversations, "resolve", lambda *_args, **_kwargs: {"public_id": "00000000-0000-0000-0000-000000000001"})
    monkeypatch.setattr(conversations, "history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(conversations, "append_message", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(agent_module, "_agent", agent_module.MedicalAgent(use_llm_intent=False))
    monkeypatch.setattr(aggregation, "aggregate", lambda *_args, **_kwargs: pytest.fail("越界问题不应查询数据库"))
    response = client.post(
        "/api/chat/stream", json={"query": "北京明天天气怎么样？"}, headers={"X-CSRF-Token": "test-csrf"},
    )
    body = response.get_data(as_text=True)
    context_block = next(block for block in body.split("\n\n") if "event: context" in block)
    context_line = next(line for line in context_block.splitlines() if line.startswith("data: "))
    context = json.loads(context_line[6:])
    assert response.status_code == 200
    assert context["intent"]["status"] == "unsupported"
    assert context["chart"] is None
    assert context["data"]["rows"] == []


def test_phase2_contract(monkeypatch):
    client = authenticated_client(monkeypatch)
    response = client.get("/api/v2/predictions")
    assert response.status_code == 501
    assert response.get_json()["meta"]["phase"] == 2
    assert response.get_json()["meta"]["enabled"] is False
    assert response.get_json()["meta"]["request_id"]
    assert client.get("/api/v2/unknown").status_code == 404


def test_disease_procedure_association_endpoint(monkeypatch):
    from app.service_layer.analysis import association

    client = authenticated_client(monkeypatch, "doctor")
    monkeypatch.setattr(association, "disease_procedure_associations", lambda **kwargs: {
        "analysis_level": "discharge_primary_diagnosis_primary_procedure",
        "min_count": kwargs["min_count"], "rows": [],
    })
    response = client.get("/api/v2/associations/disease-procedure?year=2024&min_count=50")
    assert response.status_code == 200
    assert response.get_json()["data"]["min_count"] == 50


def test_readmission_risk_reports_missing_data_contract(monkeypatch):
    client = authenticated_client(monkeypatch, "doctor")
    response = client.post(
        "/api/v2/readmission-risk", json={}, headers={"X-CSRF-Token": "test-csrf"},
    )
    assert response.status_code == 422
    payload = response.get_json()
    assert payload["meta"]["reason"] == "missing_longitudinal_patient_linkage"
    assert len(payload["meta"]["required_fields"]) == 3


def test_cost_prediction_endpoint(monkeypatch):
    from app.ml import cost_model

    client = authenticated_client(monkeypatch, "doctor")
    monkeypatch.setitem(__import__("app.service_layer.api.routes", fromlist=["FEATURES"]).FEATURES, "ml_analysis", True)
    monkeypatch.setattr(cost_model, "predict_cost", lambda features: {
        "predicted_total_cost": 123.45, "received": features,
    })
    response = client.post(
        "/api/v2/predictions/cost",
        json={"features": {"length_of_stay": 2}},
        headers={"X-CSRF-Token": "test-csrf"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["predicted_total_cost"] == 123.45
    assert response.get_json()["meta"]["enabled"] is True


@pytest.mark.parametrize("role", ["patient", "doctor", "admin"])
def test_all_roles_can_use_cost_prediction(monkeypatch, role):
    from app.ml import cost_model

    client = authenticated_client(monkeypatch, role)
    monkeypatch.setitem(__import__("app.service_layer.api.routes", fromlist=["FEATURES"]).FEATURES, "ml_analysis", True)
    monkeypatch.setattr(cost_model, "predict_cost", lambda _features: {"predicted_total_cost": 100.0})
    response = client.post(
        "/api/v2/predictions/cost", json={"features": {"length_of_stay": 2}},
        headers={"X-CSRF-Token": "test-csrf"},
    )
    assert response.status_code == 200
    assert "cost_prediction:use" in permissions_for(role)


def test_cost_prediction_without_model_returns_503(monkeypatch):
    from app.ml import cost_model

    client = authenticated_client(monkeypatch, "doctor")
    monkeypatch.setitem(__import__("app.service_layer.api.routes", fromlist=["FEATURES"]).FEATURES, "ml_analysis", True)
    monkeypatch.setattr(cost_model, "predict_cost", lambda _features: (_ for _ in ()).throw(FileNotFoundError("无模型")))
    response = client.post(
        "/api/v2/predictions/cost", json={"features": {}},
        headers={"X-CSRF-Token": "test-csrf"},
    )
    assert response.status_code == 503


def test_chat_persists_conversation(monkeypatch):
    from app.ai_layer import agent as agent_module
    from app.ai_layer import conversation as conversations

    client = authenticated_client(monkeypatch, "doctor")
    public_id = "00000000-0000-0000-0000-000000000001"
    saved = []
    monkeypatch.setattr(conversations, "resolve", lambda *_args, **_kwargs: {"public_id": public_id})
    monkeypatch.setattr(conversations, "history", lambda *_args, **_kwargs: [{"role": "user", "content": "上一轮"}])
    monkeypatch.setattr(conversations, "append_message", lambda *args, **kwargs: saved.append((args, kwargs)) or len(saved))
    monkeypatch.setattr(agent_module, "get_agent", lambda: type("Agent", (), {"analyze": lambda self, *_args: {
        "request_id": "r1", "intent": {"dimension": "year"}, "summary": "结果", "data": {}, "chart": None,
    }})())
    response = client.post(
        "/api/chat", json={"query": "继续分析", "conversation_id": public_id},
        headers={"X-CSRF-Token": "test-csrf"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["conversation_id"] == public_id
    assert [call[0][2] for call in saved] == ["user", "assistant"]


def test_error_response_exposes_request_id(client):
    response = client.get("/api/not-found", headers={"X-Request-ID": "client-trace-1"})
    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "client-trace-1"
    assert response.get_json()["meta"]["request_id"] == "client-trace-1"


def test_patient_cannot_access_patient_profile(monkeypatch):
    client = authenticated_client(monkeypatch, "patient")
    assert client.get("/api/aggregate?dimension=age_group").status_code == 403
    assert client.get("/api/data-quality").status_code == 403


def test_patient_overview_is_projected(monkeypatch):
    client = authenticated_client(monkeypatch, "patient")
    monkeypatch.setattr(aggregation, "overview", lambda *_args, **_kwargs: {
        "summary": {"discharges": 20}, "trend": [], "diseases": [{"dimension_value": "公开疾病", "count": 20}],
        "ages": [{"dimension_value": "70+"}], "payments": [{"payment": "Medicare"}],
        "genders": [{"dimension_value": "F"}], "severity": [{"dimension_value": "Major"}], "filters": {},
    })
    payload = client.get("/api/overview").get_json()["data"]
    assert payload["diseases"]
    assert payload["ages"] == []
    assert payload["payments"] == []


def test_login_starts_session_and_returns_permissions(client, monkeypatch):
    user = {"id": 7, "username": "doctor", "display_name": "医生", "role": "doctor", "is_active": True,
            "must_change_password": False, "permissions": permissions_for("doctor")}
    monkeypatch.setattr(auth_service, "authenticate", lambda *_args, **_kwargs: (user, "success"))
    response = client.post("/api/auth/login", json={"username": "doctor", "password": "Password123"})
    assert response.status_code == 200
    assert "patient_profile:read" in response.get_json()["data"]["user"]["permissions"]


def test_patient_or_doctor_can_register(client, monkeypatch):
    created = {"id": 8, "username": "new_doctor", "role": "doctor", "is_active": True}
    monkeypatch.setattr(auth_service, "register_user", lambda payload: {**created, "role": payload["role"]})
    monkeypatch.setattr(auth_service, "audit", lambda *_args, **_kwargs: None)
    response = client.post("/api/auth/register", json={
        "username": "new_doctor", "display_name": "新医生", "role": "doctor",
        "password": "Password123", "password_confirm": "Password123",
    })
    assert response.status_code == 201
    assert response.get_json()["data"]["role"] == "doctor"


def test_register_rejects_mismatched_password(client, monkeypatch):
    monkeypatch.setattr(auth_service, "register_user", lambda _payload: pytest.fail("不应调用注册服务"))
    response = client.post("/api/auth/register", json={
        "username": "patient", "role": "patient", "password": "Password123", "password_confirm": "Password456",
    })
    assert response.status_code == 400


def test_public_registration_cannot_create_admin():
    with pytest.raises(ValueError, match="患者用户或医生用户"):
        auth_service.register_user({"username": "bad", "role": "admin", "password": "Password123"})


def test_csrf_is_required_for_authenticated_writes(monkeypatch):
    client = authenticated_client(monkeypatch, "doctor")
    response = client.post("/api/reports", json={})
    assert response.status_code == 403


def test_patient_can_cancel_own_account(monkeypatch):
    client = authenticated_client(monkeypatch, "patient")
    called = {}
    monkeypatch.setattr(auth_service, "cancel_own_account", lambda user, password, **_kwargs: called.update(user=user, password=password))
    response = client.delete("/api/auth/account", json={"password": "Password123", "confirmation": "注销账号"}, headers={"X-CSRF-Token": "test-csrf"})
    assert response.status_code == 200
    assert called["user"]["role"] == "patient"
    assert client.get("/api/auth/me").status_code == 401


def test_cancel_account_requires_exact_confirmation(monkeypatch):
    client = authenticated_client(monkeypatch, "doctor")
    response = client.delete("/api/auth/account", json={"password": "Password123", "confirmation": "确认"}, headers={"X-CSRF-Token": "test-csrf"})
    assert response.status_code == 400


def test_admin_can_delete_another_user(monkeypatch):
    client = authenticated_client(monkeypatch, "admin")
    deleted = {}
    monkeypatch.setattr(auth_service, "delete_user", lambda user_id, actor, **_kwargs: deleted.update(user_id=user_id, actor=actor))
    response = client.delete("/api/admin/users/9", headers={"X-CSRF-Token": "test-csrf"})
    assert response.status_code == 200
    assert deleted["user_id"] == 9
    assert deleted["actor"]["role"] == "admin"


def test_admin_cannot_delete_or_cancel_self():
    admin = {"id": 1, "username": "admin", "role": "admin"}
    with pytest.raises(ValueError, match="不能删除自己的账号"):
        auth_service.delete_user(1, admin)
    with pytest.raises(ValueError, match="不能自助注销"):
        auth_service.cancel_own_account(admin, "Password123")
