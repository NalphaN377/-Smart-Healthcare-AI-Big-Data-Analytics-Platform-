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


def test_field_quality_contract_uses_single_annual_aggregation(monkeypatch):
    from app.service_layer.analysis import field_quality
    from app.service_layer.api import routes

    captured = {}
    row = {"year": 2024, "records": 100}
    for index, _spec in enumerate(field_quality.FIELDS):
        row[f"f{index}_applicable"] = 100
        row[f"f{index}_present"] = 98
        row[f"f{index}_valid"] = 97
    monkeypatch.setattr(
        aggregation, "_run_query",
        lambda sql, *_args, **_kwargs: captured.update(sql=sql) or [row],
    )
    monkeypatch.setattr(routes.cache, "remember", lambda _namespace, _payload, producer, **_kwargs: (producer(), False))
    client = authenticated_client(monkeypatch, "doctor")
    payload = client.get("/api/data-quality/fields").get_json()["data"]

    assert payload["field_count"] == 33
    assert payload["years"] == [2024]
    assert payload["fields"][0]["score_pct"] == 98.49
    procedure = next(item for item in payload["fields"] if item["field"] == "ccsr_procedure_code")
    assert procedure["conditional"] is True
    assert procedure["score_pct"] is None
    assert "GROUP BY discharge_year" in captured["sql"]


def test_report_library_is_scoped_to_current_user(monkeypatch):
    class Cursor:
        description = [(name,) for name in ("id", "title", "status", "created_by", "author", "published_at", "created_at", "updated_at")]

        def execute(self, sql, params=()):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [(7, "我的报告", "draft", 1, "测试用户", None, None, None)]

    class Connection:
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value
        def close(self): pass

    connection = Connection()
    monkeypatch.setattr(storage, "get_connection", lambda: connection)
    client = authenticated_client(monkeypatch, "doctor")
    response = client.get("/api/reports?limit=20")

    assert response.status_code == 200
    assert response.get_json()["data"][0]["title"] == "我的报告"
    assert "r.created_by" in connection.cursor_value.sql
    assert connection.cursor_value.params == (1,)


def test_report_detail_cannot_cross_accounts(monkeypatch):
    class Cursor:
        description = []
        def execute(self, _sql, _params=()): pass
        def fetchone(self): return None

    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass

    monkeypatch.setattr(storage, "get_connection", Connection)
    client = authenticated_client(monkeypatch, "doctor")
    response = client.get("/api/reports/99")
    assert response.status_code == 404


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


def test_sse_concept_question_uses_knowledge_rag(monkeypatch):
    from app.ai_layer import agent as agent_module
    from app.ai_layer import conversation as conversations

    client = authenticated_client(monkeypatch, "doctor")
    monkeypatch.setattr(conversations, "resolve", lambda *_args, **_kwargs: {"public_id": "00000000-0000-0000-0000-000000000001"})
    monkeypatch.setattr(conversations, "history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(conversations, "append_message", lambda *_args, **_kwargs: 1)
    monkeypatch.setitem(LLM_CONFIG, "api_key", "")
    monkeypatch.setattr(agent_module, "_agent", agent_module.MedicalAgent(use_llm_intent=False))

    response = client.post(
        "/api/chat/stream", json={"query": "费用和成本有什么区别？"},
        headers={"X-CSRF-Token": "test-csrf"},
    )
    body = response.get_data(as_text=True)
    context_block = next(block for block in body.split("\n\n") if "event: context" in block)
    context_line = next(line for line in context_block.splitlines() if line.startswith("data: "))
    context = json.loads(context_line[6:])

    assert response.status_code == 200
    assert context["answer_mode"] == "knowledge"
    assert context["direct_answer"] is None
    assert context["knowledge_sources"] == ["费用与成本口径"]
    assert "Total Charges" in body


def test_sse_comparison_context_bypasses_knowledge_search(monkeypatch):
    from app.ai_layer import agent as agent_module
    from app.ai_layer import conversation as conversations
    from app.service_layer.analysis import comparison

    client = authenticated_client(monkeypatch, "patient")
    monkeypatch.setattr(conversations, "resolve", lambda *_args, **_kwargs: {"public_id": "00000000-0000-0000-0000-000000000001"})
    monkeypatch.setattr(conversations, "history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(conversations, "append_message", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(comparison, "trusted_comparison", lambda *_args, **_kwargs: {
        "analysis_type": "trusted_pair_comparison", "dimension": "service_area",
        "metrics": ["count"], "filters": {}, "rows": [
            {"service_area": "New York City", "count": 20},
            {"service_area": "Long Island", "count": 10},
        ],
    })
    monkeypatch.setitem(LLM_CONFIG, "api_key", "")
    monkeypatch.setattr(agent_module, "_agent", agent_module.MedicalAgent(use_llm_intent=False))

    response = client.post(
        "/api/chat/stream",
        json={
            "query": "解读区域差异",
            "analysis_context": {"kind": "comparison", "comparison_type": "region", "a": "New York City", "b": "Long Island", "filters": {}},
        },
        headers={"X-CSRF-Token": "test-csrf"},
    )
    body = response.get_data(as_text=True)
    context_block = next(block for block in body.split("\n\n") if "event: context" in block)
    context_line = next(line for line in context_block.splitlines() if line.startswith("data: "))
    context = json.loads(context_line[6:])

    assert response.status_code == 200
    assert context["answer_mode"] == "structured"
    assert context["intent"]["source"] == "trusted_comparison_context"
    assert context["data"]["rows"][0]["count"] == 20


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


def test_role_specific_analytics_catalog(monkeypatch):
    admin = authenticated_client(monkeypatch, "admin")
    admin_metrics = {item["key"] for item in admin.get("/api/v2/analytics/catalog").get_json()["data"]["metrics"]}
    doctor = authenticated_client(monkeypatch, "doctor")
    doctor_metrics = {item["key"] for item in doctor.get("/api/v2/analytics/catalog").get_json()["data"]["metrics"]}
    patient = authenticated_client(monkeypatch, "patient")
    patient_dimensions = {item["key"] for item in patient.get("/api/v2/analytics/catalog").get_json()["data"]["dimensions"]}
    assert "charge_cost_spread_ratio" in admin_metrics
    assert "charge_cost_spread_ratio" not in doctor_metrics
    assert patient_dimensions == {"disease", "service_area", "year"}


def test_analytics_query_passes_server_role_and_blocks_finance(monkeypatch):
    patient = authenticated_client(monkeypatch, "patient")
    response = patient.post(
        "/api/v2/analytics/query",
        json={"dimensions": ["year"], "metrics": ["charge_cost_spread_ratio"]},
        headers={"X-CSRF-Token": "test-csrf"},
    )
    assert response.status_code == 403


def test_topic_endpoint_enforces_admin_only_analysis(monkeypatch):
    doctor = authenticated_client(monkeypatch, "doctor")
    response = doctor.post(
        "/api/v2/analytics/topics/data_quality", json={},
        headers={"X-CSRF-Token": "test-csrf"},
    )
    assert response.status_code == 403


def test_notifications_are_scoped_to_current_user(monkeypatch):
    from app.service_layer import notifications as notification_service

    client = authenticated_client(monkeypatch, "doctor")
    captured = {}
    monkeypatch.setattr(notification_service, "list_for_user", lambda user_id, limit: captured.update(user_id=user_id, limit=limit) or {
        "items": [{"id": 7, "report_id": 3, "is_read": False}], "unread_count": 1,
    })
    response = client.get("/api/notifications?limit=20")

    assert response.status_code == 200
    assert response.get_json()["data"]["unread_count"] == 1
    assert captured == {"user_id": 1, "limit": 20}


def test_notification_read_cannot_cross_accounts(monkeypatch):
    from app.service_layer import notifications as notification_service

    client = authenticated_client(monkeypatch, "patient")
    monkeypatch.setattr(notification_service, "mark_read", lambda _user_id, _notification_id: False)
    response = client.put("/api/notifications/99/read", headers={"X-CSRF-Token": "test-csrf"})

    assert response.status_code == 404
    assert response.get_json()["message"] == "通知不存在"


def test_publish_report_creates_patient_and_doctor_notifications(monkeypatch):
    from app.service_layer import notifications as notification_service

    class Cursor:
        rowcount = 1

        def __init__(self):
            self.commands = []

        def execute(self, sql, params=()):
            self.commands.append((sql, params))

        def fetchone(self):
            return ("新报告", "draft")

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.committed = False

        def cursor(self):
            return self.cursor_value

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

        def close(self):
            pass

    connection = Connection()
    created = {}
    monkeypatch.setattr(storage, "get_connection", lambda: connection)
    monkeypatch.setattr(notification_service, "enqueue_report_published", lambda cursor, report_id, title: created.update(cursor=cursor, report_id=report_id, title=title) or 2)
    monkeypatch.setattr(auth_service, "audit", lambda *_args, **_kwargs: None)
    client = authenticated_client(monkeypatch, "admin")

    response = client.put("/api/admin/reports/12/publish", headers={"X-CSRF-Token": "test-csrf"})

    assert response.status_code == 200
    assert response.get_json()["data"]["notifications_created"] == 2
    assert created["report_id"] == 12 and created["title"] == "新报告"
    assert connection.committed is True


def test_withdraw_report_removes_notifications_in_same_transaction(monkeypatch):
    class Cursor:
        rowcount = 1

        def __init__(self):
            self.commands = []

        def execute(self, sql, params=()):
            self.commands.append((sql, params))
            self.rowcount = 3 if sql.startswith("DELETE FROM dbo.user_notification") else 1

        def fetchone(self):
            return ("published",)

    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.committed = False

        def cursor(self):
            return self.cursor_value

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

        def close(self):
            pass

    connection = Connection()
    monkeypatch.setattr(storage, "get_connection", lambda: connection)
    monkeypatch.setattr(auth_service, "audit", lambda *_args, **_kwargs: None)
    client = authenticated_client(monkeypatch, "admin")

    response = client.put("/api/admin/reports/12/withdraw", headers={"X-CSRF-Token": "test-csrf"})

    assert response.status_code == 200
    assert response.get_json()["data"]["notifications_removed"] == 3
    assert any(sql.startswith("DELETE FROM dbo.user_notification") for sql, _params in connection.cursor_value.commands)
    assert any("status='draft'" in sql for sql, _params in connection.cursor_value.commands)
    assert connection.committed is True


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


def test_patient_can_use_hospital_compare(monkeypatch):
    from app.service_layer.analysis import hospital_compare

    client = authenticated_client(monkeypatch, "patient")
    monkeypatch.setattr(hospital_compare, "compare_hospitals", lambda a, b, **kwargs: {
        "hospitals": [{"hospital": a}, {"hospital": b}], "role_scope": kwargs["role"],
    })
    response = client.post(
        "/api/v2/analytics/hospital-compare",
        json={"hospital_a": "医院 A", "hospital_b": "医院 B", "filters": {}},
        headers={"X-CSRF-Token": "test-csrf"},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["role_scope"] == "patient"


def test_login_starts_session_and_returns_permissions(client, monkeypatch):
    from app.auth import captcha

    user = {"id": 7, "username": "doctor", "display_name": "医生", "role": "doctor", "is_active": True,
            "must_change_password": False, "permissions": permissions_for("doctor")}
    monkeypatch.setattr(captcha, "verify", lambda _value: (True, ""))
    monkeypatch.setattr(auth_service, "authenticate", lambda *_args, **_kwargs: (user, "success"))
    response = client.post("/api/auth/login", json={"username": "doctor", "password": "Password123", "captcha": "ABCDE"})
    assert response.status_code == 200
    assert "patient_profile:read" in response.get_json()["data"]["user"]["permissions"]


def test_login_captcha_is_required_and_one_time(client, monkeypatch):
    from app.auth import captcha

    monkeypatch.setattr(captcha.secrets, "choice", lambda _alphabet: "A")
    response = client.get("/api/auth/captcha")
    assert response.status_code == 200
    assert response.get_json()["data"]["image"].startswith("data:image/svg+xml;base64,")

    wrong = client.post("/api/auth/login", json={
        "username": "doctor", "password": "Password123", "captcha": "BBBBB",
    })
    assert wrong.status_code == 400
    assert "验证码错误" in wrong.get_json()["message"]

    reused = client.post("/api/auth/login", json={
        "username": "doctor", "password": "Password123", "captcha": "AAAAA",
    })
    assert reused.status_code == 400
    assert "过期" in reused.get_json()["message"]

    user = {"id": 7, "username": "doctor", "display_name": "医生", "role": "doctor", "is_active": True,
            "must_change_password": False, "permissions": permissions_for("doctor")}
    monkeypatch.setattr(auth_service, "authenticate", lambda *_args, **_kwargs: (user, "success"))
    client.get("/api/auth/captcha")
    valid = client.post("/api/auth/login", json={
        "username": "doctor", "password": "Password123", "captcha": "AAAAA",
    })
    assert valid.status_code == 200


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
