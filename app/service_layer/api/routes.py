"""智慧医疗 REST/SSE API。"""
from __future__ import annotations

import json
import platform

from flask import Blueprint, Response, request, session, stream_with_context

from app.auth import captcha
from app.auth import service as auth_service
from app.auth.permissions import ROLE_LABELS
from app.auth.web import current_user, login_required, permission_required, start_session
from app.common import cache
from app.common.response import fail, success, timing
from app.data_layer import storage
from app.service_layer.analysis import aggregation
from app.service_layer.analysis import registry as analysis_registry
from config import FEATURES, LLM_CONFIG

api = Blueprint("api", __name__, url_prefix="/api")


def _filters() -> dict:
    return {key: request.args.get(key) for key in aggregation.FILTERS if request.args.get(key) not in (None, "")}


def _limit(default=20) -> int:
    value = request.args.get("limit", default, type=int)
    if value is None or not 1 <= value <= 100:
        raise ValueError("limit 必须在 1 到 100 之间")
    return value


def _request_context() -> dict:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return {
        "ip_address": (forwarded.split(",")[0].strip() if forwarded else request.remote_addr or ""),
        "user_agent": request.headers.get("User-Agent", ""),
    }


def _cached(namespace: str, producer, *, extra: dict | None = None):
    payload = {
        "role": current_user()["role"],
        "query": sorted((key, value) for key, value in request.args.items(multi=True)),
        **(extra or {}),
    }
    data, hit = cache.remember(namespace, payload, producer)
    version = cache.data_version() if FEATURES.get("redis_cache") else None
    return data, {"cache_enabled": bool(FEATURES.get("redis_cache")), "cache_hit": hit, "data_version": version}


def _chat_history(body: dict) -> list[dict]:
    """仅保留少量文本对话用于指代消解，避免客户端注入任意结构或超长上下文。"""
    history = body.get("history") or []
    if not isinstance(history, list):
        raise ValueError("history 必须是数组")
    clean = []
    for item in history[-6:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()[:300]
        if content:
            clean.append({"role": item["role"], "content": content})
    return clean


@api.post("/auth/register")
@timing()
def register():
    body = request.get_json(silent=True) or {}
    if str(body.get("password") or "") != str(body.get("password_confirm") or ""):
        return fail("两次输入的密码不一致", code=400), 400
    user = auth_service.register_user(body)
    auth_service.audit(user, "auth.register", user.get("role", ""), **_request_context())
    return success({"username": user["username"], "role": user["role"]}, message="注册成功，请登录"), 201


@api.post("/auth/login")
@timing()
def login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not username or not password:
        return fail("请输入用户名和密码", code=400), 400
    captcha_valid, captcha_message = captcha.verify(str(body.get("captcha") or ""))
    if not captcha_valid:
        return fail(captcha_message, code=400), 400
    user, message = auth_service.authenticate(username, password, **_request_context())
    if not user:
        return fail(message, code=401), 401
    csrf_token = start_session(user)
    return success({"user": user, "csrf_token": csrf_token}, message="登录成功")


@api.get("/auth/captcha")
@timing()
def login_captcha():
    return success(captcha.issue())


@api.post("/auth/logout")
@timing()
@login_required
def logout():
    auth_service.audit(current_user(), "auth.logout", **_request_context())
    session.clear()
    return success(message="已安全退出")


@api.get("/auth/me")
@timing()
@login_required
def me():
    return success({"user": current_user(), "csrf_token": session.get("csrf_token")})


@api.post("/auth/change-password")
@timing()
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    auth_service.change_password(
        current_user()["id"], str(body.get("current_password") or ""),
        str(body.get("new_password") or ""), current_user(),
    )
    return success(message="密码修改成功")


@api.delete("/auth/account")
@timing()
@login_required
def cancel_account():
    body = request.get_json(silent=True) or {}
    if str(body.get("confirmation") or "") != "注销账号":
        return fail("请输入“注销账号”确认操作", code=400), 400
    auth_service.cancel_own_account(
        current_user(), str(body.get("password") or ""), **_request_context(),
    )
    session.clear()
    return success(message="账号已注销")


@api.get("/health")
@timing()
def health():
    connected = False
    try:
        storage.ping()
        connected = True
    except Exception:  # 公共健康检查不暴露内部异常
        pass
    return success({"status": "ok" if connected else "degraded", "database": {"connected": connected}})


@api.get("/metadata")
@timing()
@permission_required("data_asset:read")
def metadata():
    role = current_user()["role"]
    return success({
        "dimensions": [{"key": key, "label": spec.label, "sensitive": spec.sensitive} for key, spec in analysis_registry.dimensions_for(role).items()],
        "metrics": [{"key": key, "label": spec.label, "unit": spec.unit, "disclaimer": spec.disclaimer} for key, spec in analysis_registry.metrics_for(role).items()],
        "filters": list(aggregation.FILTERS),
        "phase2": [
            "redis_cache", "ml_cost_prediction", "disease_procedure_association",
            "persistent_conversation", "readmission_risk_contract", "distributed_engine",
            "local_llm", "backup_restore",
        ],
    })


@api.get("/overview")
@timing()
@permission_required("overview:read")
def overview():
    filters = _filters()
    data, cache_meta = _cached("overview", lambda: aggregation.overview(filters))
    if current_user()["role"] == "patient":
        data = {
            "summary": data.get("summary", {}),
            "trend": data.get("trend", []),
            "diseases": [row for row in data.get("diseases", []) if int(row.get("count") or 0) >= 11][:5],
            "ages": [], "payments": [], "genders": [], "severity": [],
            "filters": data.get("filters", {}),
        }
    return success(data, meta=cache_meta)


@api.get("/aggregate")
@timing()
@permission_required("patient_profile:read")
def aggregate():
    metrics = request.args.get("metrics")
    metric_list = [value.strip() for value in metrics.split(",") if value.strip()] if metrics else None
    dimension = request.args.get("dimension", "age_group")
    limit = _limit()
    filters = _filters()
    data, cache_meta = _cached(
        "aggregate",
        lambda: aggregation.aggregate(dimension, metrics=metric_list, limit=limit, filters=filters, role=current_user()["role"]),
        extra={"dimension": dimension, "metrics": metric_list},
    )
    return success(data, meta={"dimension": dimension, **cache_meta})


@api.get("/avg_length_of_stay")
@timing()
@permission_required("patient_profile:read")
def avg_length_of_stay():
    dimension = request.args.get("dimension", "age_group")
    limit, filters = _limit(), _filters()
    data, cache_meta = _cached("avg_length_of_stay", lambda: aggregation.avg_length_of_stay_by(dimension, limit, filters, current_user()["role"]))
    return success(data, meta={"indicator": "平均住院日", "dimension": dimension, **cache_meta})


@api.get("/cost_distribution")
@timing()
@permission_required("patient_profile:read")
def cost_distribution():
    dimension = request.args.get("dimension", "disease")
    limit, filters = _limit(), _filters()
    data, cache_meta = _cached("cost_distribution", lambda: aggregation.cost_distribution(dimension, limit, filters, current_user()["role"]))
    return success(data, meta={"indicator": "住院费用", "dimension": dimension, **cache_meta})


@api.get("/payment_ratio")
@timing()
@permission_required("patient_profile:read")
def payment_ratio():
    limit, filters = _limit(), _filters()
    data, cache_meta = _cached("payment_ratio", lambda: aggregation.payment_ratio(limit, filters, current_user()["role"]))
    return success(data, meta={"indicator": "支付方式占比", **cache_meta})


@api.get("/year_trend")
@timing()
@permission_required("patient_profile:read")
def year_trend():
    filters = _filters()
    data, cache_meta = _cached("year_trend", lambda: aggregation.year_trend(filters, current_user()["role"]))
    return success(data, meta={"indicator": "出院年份趋势", **cache_meta})


@api.get("/dimensions/<dimension>/values")
@timing()
@permission_required("patient_profile:read")
def dimension_values(dimension):
    limit = _limit(100)
    values, cache_meta = _cached("dimension_values", lambda: aggregation.dimension_values(dimension, limit, current_user()["role"]), extra={"dimension": dimension})
    return success({"dimension": dimension, "values": values}, meta=cache_meta)


@api.get("/data-quality")
@timing()
@permission_required("data_asset:read")
def data_quality():
    run = storage.latest_ingestion()
    return success({"latest_ingestion": run, "quality": (run or {}).get("quality") or {}})


@api.get("/data-quality/fields")
@timing()
@permission_required("data_asset:read")
def data_quality_fields():
    from app.service_layer.analysis.field_quality import field_quality_matrix

    # 两个获授权角色看到相同的非患者级字段统计，共享缓存可避免850万行重复扫描。
    data, hit = cache.remember("field_quality_matrix", {"scope": "data_asset"}, field_quality_matrix, ttl=86400)
    return success(data, meta={
        "cache_enabled": bool(FEATURES.get("redis_cache")), "cache_hit": hit,
        "data_version": cache.data_version() if FEATURES.get("redis_cache") else None,
    })


@api.post("/chat")
@timing()
@login_required
def chat():
    body = request.get_json(silent=True) or {}
    query = str(body.get("query", "")).strip()
    if not query:
        raise ValueError("query 不能为空")
    if len(query) > 500:
        raise ValueError("query 长度不能超过 500 个字符")
    from app.ai_layer.agent import get_agent
    from app.ai_layer import conversation as conversations
    user = current_user()
    conversation = conversations.resolve(user["id"], body.get("conversation_id"), query)
    history = conversations.history(user["id"], conversation["public_id"])
    result = get_agent().analyze(query, user["role"], history or _chat_history(body))
    conversations.append_message(user["id"], conversation["public_id"], "user", query, request_id=result["request_id"])
    conversations.append_message(
        user["id"], conversation["public_id"], "assistant", result["summary"],
        request_id=result["request_id"], payload={"intent": result["intent"], "request_id": result["request_id"]},
    )
    result["conversation_id"] = conversation["public_id"]
    return success(result)


@api.post("/chat/stream")
@login_required
def chat_stream():
    body = request.get_json(silent=True) or {}
    query = str(body.get("query", "")).strip()
    if not query or len(query) > 500:
        return fail("query 不能为空且长度不能超过 500 个字符", code=400), 400
    from app.ai_layer.agent import get_agent
    from app.ai_layer import conversation as conversations
    agent = get_agent()
    user = current_user()
    try:
        conversation = conversations.resolve(user["id"], body.get("conversation_id"), query)
        history = conversations.history(user["id"], conversation["public_id"])
        analysis_context = body.get("analysis_context")
        if analysis_context is not None:
            if not isinstance(analysis_context, dict) or analysis_context.get("kind") != "comparison":
                raise ValueError("analysis_context 格式无效")
            filters = analysis_context.get("filters") or {}
            if not isinstance(filters, dict):
                raise ValueError("analysis_context.filters 必须是对象")
            spec = {
                "comparison_type": str(analysis_context.get("comparison_type") or "")[:20],
                "a": analysis_context.get("a"),
                "b": analysis_context.get("b"),
                "filters": filters,
            }
            if any(len(str(spec[key] or "")) > 200 for key in ("a", "b")):
                raise ValueError("比较对象名称过长")
            context = agent.prepare_comparison(query, user["role"], spec)
        else:
            context = agent.prepare(query, user["role"], history or _chat_history(body))
        context["conversation_id"] = conversation["public_id"]
        conversations.append_message(
            user["id"], conversation["public_id"], "user", query, request_id=context["request_id"],
        )
    except PermissionError as exc:
        return fail(str(exc), code=403), 403
    except (ValueError, LookupError) as exc:
        return fail(str(exc), code=400), 400

    def event(name: str, payload) -> str:
        return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    @stream_with_context
    def generate():
        yield event("context", context)
        summary_parts = []
        try:
            for token in agent.stream(context):
                summary_parts.append(token)
                yield event("delta", {"text": token})
            summary = "".join(summary_parts)
            conversations.append_message(
                user["id"], conversation["public_id"], "assistant", summary,
                request_id=context["request_id"], payload={"intent": context["intent"], "request_id": context["request_id"]},
            )
            yield event("done", {"request_id": context["request_id"], "conversation_id": conversation["public_id"], "summary": summary})
        except Exception as exc:  # 连接建立后的异常只能通过 SSE 返回
            yield event("error", {"message": "AI 流式生成中断", "type": exc.__class__.__name__})

    return Response(
        generate(), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@api.get("/conversations")
@timing()
@login_required
def list_conversations():
    from app.ai_layer import conversation as conversations
    return success(conversations.list_for_user(current_user()["id"], _limit(30)))


@api.get("/conversations/<conversation_id>")
@timing()
@login_required
def conversation_detail(conversation_id):
    from app.ai_layer import conversation as conversations
    try:
        return success(conversations.detail(current_user()["id"], conversation_id))
    except LookupError as exc:
        return fail(str(exc), code=404), 404


@api.delete("/conversations/<conversation_id>")
@timing()
@login_required
def archive_conversation(conversation_id):
    from app.ai_layer import conversation as conversations
    try:
        conversations.archive(current_user()["id"], conversation_id)
    except LookupError as exc:
        return fail(str(exc), code=404), 404
    return success(message="对话已归档")


@api.post("/reports")
@timing()
@permission_required("report:generate")
def reports():
    body = request.get_json(silent=True) or {}
    title = str(body.get("title") or "医疗大数据洞察报告")[:100]
    sections = body.get("sections") or [
        {"title": "疾病住院量与费用", "data": aggregation.cost_distribution("disease", 10)},
        {"title": "患者年龄结构", "data": aggregation.avg_length_of_stay_by("age_group", 10)},
        {"title": "支付方式构成", "data": aggregation.payment_ratio(20)},
    ]
    if not isinstance(sections, list) or not sections:
        raise ValueError("sections 必须是非空数组")
    from app.ai_layer.report import generate_report
    content = generate_report(sections[:8], title)
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.analysis_report(title,content,status,created_by) OUTPUT INSERTED.id "
            f"VALUES ({','.join([storage.PARAM] * 4)})",
            (title, content, "draft", current_user()["id"]),
        )
        report_id = int(cursor.fetchone()[0])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    auth_service.audit(current_user(), "report.generate", str(report_id), **_request_context())
    return success({"id": report_id, "title": title, "status": "draft", "format": "markdown", "content": content})


def _report_row(cursor, row, *, include_content=False):
    item = dict(zip([column[0] for column in cursor.description], row))
    for key in ("published_at", "created_at", "updated_at"):
        if item.get(key):
            item[key] = item[key].isoformat()
    if not include_content:
        item.pop("content", None)
    return item


@api.get("/reports")
@timing()
@permission_required("report:generate")
def report_library():
    user = current_user()
    limit = _limit(50)
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        where, params = ("", ()) if user["role"] == "admin" else (f"WHERE r.created_by={storage.PARAM}", (user["id"],))
        cursor.execute(
            f"SELECT TOP {limit} r.id,r.title,r.status,r.created_by,"
            "COALESCE(NULLIF(u.display_name,N''),u.username) AS author,r.published_at,r.created_at,r.updated_at "
            "FROM dbo.analysis_report r JOIN dbo.users u ON u.id=r.created_by "
            f"{where} ORDER BY r.updated_at DESC,r.id DESC",
            params,
        )
        return success([_report_row(cursor, row) for row in cursor.fetchall()])
    finally:
        conn.close()


@api.get("/reports/<int:report_id>")
@timing()
@permission_required("report:generate")
def report_detail(report_id):
    user = current_user()
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        owner_clause, params = ("", (report_id,)) if user["role"] == "admin" else (f" AND r.created_by={storage.PARAM}", (report_id, user["id"]))
        cursor.execute(
            "SELECT r.id,r.title,r.content,r.status,r.created_by,"
            "COALESCE(NULLIF(u.display_name,N''),u.username) AS author,r.published_at,r.created_at,r.updated_at "
            "FROM dbo.analysis_report r JOIN dbo.users u ON u.id=r.created_by "
            f"WHERE r.id={storage.PARAM}{owner_clause}",
            params,
        )
        row = cursor.fetchone()
        if not row:
            return fail("报告不存在或无权查看", code=404), 404
        return success(_report_row(cursor, row, include_content=True))
    finally:
        conn.close()


@api.get("/reports/public")
@timing()
@permission_required("report:public:read")
def public_reports():
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id,title,content,published_at,created_at FROM dbo.analysis_report WHERE status='published' ORDER BY published_at DESC")
        columns = [column[0] for column in cursor.description]
        rows = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            for key in ("published_at", "created_at"):
                if item.get(key):
                    item[key] = item[key].isoformat()
            rows.append(item)
        return success(rows)
    finally:
        conn.close()


@api.get("/notifications")
@timing()
@login_required
def notifications():
    from app.service_layer import notifications as notification_service

    return success(notification_service.list_for_user(current_user()["id"], _limit(50)))


@api.put("/notifications/<int:notification_id>/read")
@timing()
@login_required
def read_notification(notification_id):
    from app.service_layer import notifications as notification_service

    if not notification_service.mark_read(current_user()["id"], notification_id):
        return fail("通知不存在", code=404), 404
    return success(message="通知已读")


@api.put("/notifications/read-all")
@timing()
@login_required
def read_all_notifications():
    from app.service_layer import notifications as notification_service

    changed = notification_service.mark_all_read(current_user()["id"])
    return success({"updated": changed}, message="全部通知已读")


@api.put("/admin/reports/<int:report_id>/publish")
@timing()
@permission_required("system:manage")
def publish_report(report_id):
    from app.service_layer import notifications as notification_service

    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT title,status FROM dbo.analysis_report WITH (UPDLOCK,HOLDLOCK) WHERE id={storage.PARAM}",
            (report_id,),
        )
        report = cursor.fetchone()
        if not report:
            conn.rollback()
            return fail("报告不存在", code=404), 404
        title, previous_status = report
        notified = 0
        if previous_status != "published":
            cursor.execute(
                "UPDATE dbo.analysis_report SET status='published',published_at=SYSUTCDATETIME(),"
                f"updated_at=SYSUTCDATETIME() WHERE id={storage.PARAM}",
                (report_id,),
            )
            notified = notification_service.enqueue_report_published(cursor, report_id, title)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    auth_service.audit(current_user(), "report.publish", str(report_id), **_request_context())
    return success({"notifications_created": notified}, message="报告已发布")


@api.put("/admin/reports/<int:report_id>/withdraw")
@timing()
@permission_required("system:manage")
def withdraw_report(report_id):
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT status FROM dbo.analysis_report WITH (UPDLOCK,HOLDLOCK) WHERE id={storage.PARAM}",
            (report_id,),
        )
        report = cursor.fetchone()
        if not report:
            conn.rollback()
            return fail("报告不存在", code=404), 404
        if report[0] != "published":
            conn.rollback()
            return fail("该报告当前未发布", code=409), 409
        cursor.execute(
            f"DELETE FROM dbo.user_notification WHERE report_id={storage.PARAM}",
            (report_id,),
        )
        removed_notifications = max(int(cursor.rowcount or 0), 0)
        cursor.execute(
            "UPDATE dbo.analysis_report SET status='draft',published_at=NULL,updated_at=SYSUTCDATETIME() "
            f"WHERE id={storage.PARAM}",
            (report_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    auth_service.audit(current_user(), "report.withdraw", str(report_id), **_request_context())
    return success({"notifications_removed": removed_notifications}, message="报告已撤回")


@api.get("/admin/users")
@timing()
@permission_required("user:manage")
def admin_users():
    return success(auth_service.list_users())


@api.post("/admin/users")
@timing()
@permission_required("user:manage")
def admin_create_user():
    return success(auth_service.create_user(request.get_json(silent=True) or {}, current_user()), message="用户创建成功")


@api.put("/admin/users/<int:user_id>")
@timing()
@permission_required("user:manage")
def admin_update_user(user_id):
    try:
        user = auth_service.update_user(user_id, request.get_json(silent=True) or {}, current_user())
    except LookupError as exc:
        return fail(str(exc), code=404), 404
    return success(user, message="用户更新成功")


@api.delete("/admin/users/<int:user_id>")
@timing()
@permission_required("user:manage")
def admin_delete_user(user_id):
    try:
        auth_service.delete_user(user_id, current_user(), **_request_context())
    except LookupError as exc:
        return fail(str(exc), code=404), 404
    return success(message="账号已删除")


@api.post("/admin/users/<int:user_id>/reset-password")
@timing()
@permission_required("user:manage")
def admin_reset_password(user_id):
    try:
        auth_service.reset_password(user_id, str((request.get_json(silent=True) or {}).get("new_password") or ""), current_user())
    except LookupError as exc:
        return fail(str(exc), code=404), 404
    return success(message="密码已重置，用户下次登录后必须修改密码")


@api.get("/admin/system/health")
@timing()
@permission_required("system:manage")
def admin_system_health():
    database = {"connected": False}
    try:
        database = {"connected": True, **storage.ping()}
    except Exception as exc:
        database["error"] = exc.__class__.__name__
    return success({
        "status": "ok" if database["connected"] else "degraded",
        "runtime": {"python": platform.python_version()}, "database": database,
        "llm": {"configured": bool(LLM_CONFIG["api_key"]), "model": LLM_CONFIG["model"]},
        "redis": cache.health(), "features": FEATURES,
    })


@api.get("/admin/audit-logs")
@timing()
@permission_required("audit:read")
def admin_audit_logs():
    return success(auth_service.list_audit_logs(_limit(100)))


@api.get("/v2/cache")
@timing()
@permission_required("system:manage")
def phase2_cache_status():
    return success(cache.health())


@api.get("/v2/analytics/catalog")
@timing()
@login_required
def analytics_catalog():
    role = current_user()["role"]
    return success({
        "years": [2021, 2022, 2023, 2024],
        "dimensions": [
            {"key": key, "label": spec.label, "min_count": max(spec.min_count, 11 if role == "patient" else 1),
             "sensitive": spec.sensitive}
            for key, spec in analysis_registry.dimensions_for(role).items()
        ],
        "metrics": [
            {"key": key, "label": spec.label, "unit": spec.unit, "description": spec.description,
             "disclaimer": spec.disclaimer}
            for key, spec in analysis_registry.metrics_for(role).items()
        ],
    })


@api.post("/v2/analytics/query")
@timing()
@login_required
def analytics_query():
    body = request.get_json(silent=True) or {}
    dimensions = body.get("dimensions") or ([body.get("dimension")] if body.get("dimension") else [])
    metrics = body.get("metrics") or ["count"]
    if not isinstance(dimensions, list) or not isinstance(metrics, list):
        raise ValueError("dimensions 和 metrics 必须是数组")
    filters = body.get("filters") or {}
    if not isinstance(filters, dict):
        raise ValueError("filters 必须是对象")
    role = current_user()["role"]
    extra = {"dimensions": dimensions, "metrics": metrics, "filters": filters,
             "sort_by": body.get("sort_by"), "sort_order": body.get("sort_order", "desc"),
             "limit": body.get("limit", 20)}
    data, cache_meta = _cached(
        "analytics_query",
        lambda: aggregation.aggregate(
            dimensions, metrics, limit=int(body.get("limit", 20)), filters=filters,
            sort_by=body.get("sort_by"), sort_order=body.get("sort_order", "desc"), role=role,
        ),
        extra=extra,
    )
    return success(data, meta=cache_meta)


@api.post("/v2/analytics/topics/<topic>")
@timing()
@login_required
def analytics_topic(topic):
    from app.service_layer.analysis import mining

    body = request.get_json(silent=True) or {}
    filters = body.get("filters") or {}
    if not isinstance(filters, dict):
        raise ValueError("filters 必须是对象")
    role = current_user()["role"]
    extra = {"topic": topic, "filters": filters, "limit": body.get("limit", 100), "contract_version": 2}
    data, cache_meta = _cached(
        f"analytics_topic:{topic}",
        lambda: mining.topic_analysis(
            topic, role=role, filters=filters, limit=max(1, min(int(body.get("limit", 100)), 100)),
            dimension=body.get("dimension"), metrics=body.get("metrics"),
        ),
        extra=extra,
    )
    return success(data, meta=cache_meta)


@api.get("/v2/analytics/hospitals")
@timing()
@login_required
def analytics_hospitals():
    from app.service_layer.analysis import hospital_compare

    search = (request.args.get("search") or "").strip()[:100]
    service_area = (request.args.get("service_area") or "").strip()[:100]
    limit = request.args.get("limit", 100, type=int)
    if limit is None or not 1 <= limit <= 300:
        raise ValueError("limit 必须在 1 到 300 之间")
    data, cache_meta = _cached(
        "analytics_hospitals",
        lambda: hospital_compare.list_hospitals(search=search, service_area=service_area, limit=limit),
        extra={"search": search, "service_area": service_area},
    )
    return success(data, meta=cache_meta)


@api.post("/v2/analytics/hospital-compare")
@timing()
@login_required
def analytics_hospital_compare():
    from app.service_layer.analysis import hospital_compare

    body = request.get_json(silent=True) or {}
    filters = body.get("filters") or {}
    if not isinstance(filters, dict):
        raise ValueError("filters 必须是对象")
    hospital_a, hospital_b = body.get("hospital_a"), body.get("hospital_b")
    extra = {"hospital_a": hospital_a, "hospital_b": hospital_b, "filters": filters, "contract_version": 1}
    data, cache_meta = _cached(
        "analytics_hospital_compare",
        lambda: hospital_compare.compare_hospitals(
            hospital_a, hospital_b, filters=filters, role=current_user()["role"],
        ),
        extra=extra,
    )
    return success(data, meta=cache_meta)


@api.get("/v2/associations/disease-procedure")
@timing()
@permission_required("patient_profile:read")
def disease_procedure_associations():
    from app.service_layer.analysis.association import disease_procedure_associations as analyze

    limit = _limit()
    min_count = request.args.get("min_count", 100, type=int)
    if min_count is None:
        raise ValueError("min_count 必须是整数")
    data, cache_meta = _cached(
        "disease_procedure_associations",
        lambda: analyze(limit=limit, min_count=min_count, filters=_filters()),
        extra={"min_count": min_count},
    )
    return success(data, meta=cache_meta)


@api.post("/v2/readmission-risk")
@timing()
@permission_required("patient_profile:read")
def readmission_risk_unavailable():
    """明确暴露数据契约缺口，禁止用单次脱敏出院记录伪造风险概率。"""
    return fail(
        "当前数据无法可靠计算30天再入院风险",
        code=422,
        meta={
            "phase": 2,
            "enabled": False,
            "reason": "missing_longitudinal_patient_linkage",
            "required_fields": [
                "稳定且脱敏的患者纵向标识",
                "入院与出院日期",
                "后续30天内再次入院标签",
            ],
        },
    ), 422


@api.post("/v2/predictions/cost")
@timing()
@permission_required("cost_prediction:use")
def predict_inpatient_cost():
    from app.ml.cost_model import predict_cost

    if not FEATURES.get("ml_analysis"):
        return fail("费用预测功能未启用", code=503, meta={"phase": 2, "enabled": False}), 503
    body = request.get_json(silent=True) or {}
    try:
        result = predict_cost(body.get("features"))
    except FileNotFoundError as exc:
        return fail(str(exc), code=503, meta={"phase": 2, "enabled": False}), 503
    return success(result, meta={"phase": 2, "enabled": True})


@api.get("/v2/predictions/cost-options")
@timing()
@permission_required("cost_prediction:use")
def prediction_cost_options():
    from app.ml.cost_model import cost_prediction_options

    return success(cost_prediction_options())


@api.post("/v2/predictions/future-cost")
@timing()
@permission_required("future_cost_prediction:use")
def predict_future_inpatient_cost():
    """待入院病例的未来年度成本情景；只接受入院前可知字段。"""
    from app.ml.cost_model import predict_future_cost

    if not FEATURES.get("ml_analysis"):
        return fail("费用预测功能未启用", code=503, meta={"phase": 2, "enabled": False}), 503
    body = request.get_json(silent=True) or {}
    try:
        result = predict_future_cost(
            body.get("features"), body.get("forecast_year"), body.get("annual_cost_growth_rate"),
        )
    except FileNotFoundError as exc:
        return fail(str(exc), code=503, meta={"phase": 2, "enabled": False}), 503
    return success(result, meta={"phase": 2, "enabled": True})


@api.post("/v2/forecasts/annual-budget")
@timing()
@permission_required("budget_forecast:use")
def forecast_annual_budget():
    """医院/服务区域年度预算预测，仅对医生和管理员开放。"""
    from app.ml.cost_model import forecast_annual_budget as build_forecast

    if not FEATURES.get("ml_analysis"):
        return fail("费用预测功能未启用", code=503, meta={"phase": 2, "enabled": False}), 503
    return success(build_forecast(request.get_json(silent=True) or {}), meta={"phase": 2, "enabled": True})


@api.route("/v2/<capability>", methods=["GET", "POST"])
@login_required
def phase2_placeholder(capability):
    known = {"cache", "predictions", "backup", "distributed", "local-llm"}
    if capability not in known:
        return fail("二期能力不存在", code=404), 404
    return fail(f"{capability} 已完成接口预留，将在二期启用", code=501, meta={"phase": 2, "enabled": False}), 501
