"""智慧医疗 REST/SSE API。"""
from __future__ import annotations

import json
import platform

from flask import Blueprint, Response, request, stream_with_context

from app.common.response import fail, success, timing
from app.data_layer import storage
from app.service_layer.analysis import aggregation
from config import FEATURES, LLM_CONFIG

api = Blueprint("api", __name__, url_prefix="/api")


def _filters() -> dict:
    return {key: request.args.get(key) for key in aggregation.FILTERS if request.args.get(key) not in (None, "")}


def _limit(default=20) -> int:
    value = request.args.get("limit", default, type=int)
    if value is None or not 1 <= value <= 100:
        raise ValueError("limit 必须在 1 到 100 之间")
    return value


@api.get("/health")
@timing()
def health():
    database = {"connected": False}
    try:
        database = {"connected": True, **storage.ping()}
    except Exception as exc:  # 健康接口仍需返回服务状态
        database["error"] = exc.__class__.__name__
    status = "ok" if database["connected"] else "degraded"
    return success({
        "status": status,
        "runtime": {"python": platform.python_version()},
        "database": database,
        "llm": {"configured": bool(LLM_CONFIG["api_key"]), "model": LLM_CONFIG["model"]},
        "features": FEATURES,
    })


@api.get("/metadata")
@timing()
def metadata():
    return success({
        "dimensions": [{"key": key, "label": aggregation.DIMENSION_LABELS[key]} for key in aggregation.DIMENSIONS],
        "metrics": list(aggregation.METRICS),
        "filters": list(aggregation.FILTERS),
        "phase2": ["redis_cache", "ml_cost_prediction", "readmission_risk", "distributed_engine", "local_llm", "backup_restore"],
    })


@api.get("/overview")
@timing()
def overview():
    return success(aggregation.overview(_filters()))


@api.get("/aggregate")
@timing()
def aggregate():
    metrics = request.args.get("metrics")
    metric_list = [value.strip() for value in metrics.split(",") if value.strip()] if metrics else None
    dimension = request.args.get("dimension", "age_group")
    return success(
        aggregation.aggregate(dimension, metrics=metric_list, limit=_limit(), filters=_filters()),
        meta={"dimension": dimension},
    )


@api.get("/avg_length_of_stay")
@timing()
def avg_length_of_stay():
    dimension = request.args.get("dimension", "age_group")
    return success(aggregation.avg_length_of_stay_by(dimension, _limit(), _filters()), meta={"indicator": "平均住院日", "dimension": dimension})


@api.get("/cost_distribution")
@timing()
def cost_distribution():
    dimension = request.args.get("dimension", "disease")
    return success(aggregation.cost_distribution(dimension, _limit(), _filters()), meta={"indicator": "住院费用", "dimension": dimension})


@api.get("/payment_ratio")
@timing()
def payment_ratio():
    return success(aggregation.payment_ratio(_limit(), _filters()), meta={"indicator": "支付方式占比"})


@api.get("/year_trend")
@timing()
def year_trend():
    return success(aggregation.year_trend(_filters()), meta={"indicator": "出院年份趋势"})


@api.get("/dimensions/<dimension>/values")
@timing()
def dimension_values(dimension):
    return success({"dimension": dimension, "values": aggregation.dimension_values(dimension, _limit(100))})


@api.get("/data-quality")
@timing()
def data_quality():
    run = storage.latest_ingestion()
    return success({"latest_ingestion": run, "quality": (run or {}).get("quality") or {}})


@api.post("/chat")
@timing()
def chat():
    body = request.get_json(silent=True) or {}
    query = str(body.get("query", "")).strip()
    if not query:
        raise ValueError("query 不能为空")
    if len(query) > 500:
        raise ValueError("query 长度不能超过 500 个字符")
    from app.ai_layer.agent import get_agent
    return success(get_agent().analyze(query))


@api.post("/chat/stream")
def chat_stream():
    body = request.get_json(silent=True) or {}
    query = str(body.get("query", "")).strip()
    if not query or len(query) > 500:
        return fail("query 不能为空且长度不能超过 500 个字符", code=400), 400
    from app.ai_layer.agent import get_agent
    agent = get_agent()
    try:
        context = agent.prepare(query)
    except ValueError as exc:
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
            yield event("done", {"request_id": context["request_id"], "summary": "".join(summary_parts)})
        except Exception as exc:  # 连接建立后的异常只能通过 SSE 返回
            yield event("error", {"message": "AI 流式生成中断", "type": exc.__class__.__name__})

    return Response(
        generate(), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@api.post("/reports")
@timing()
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
    return success({"title": title, "format": "markdown", "content": generate_report(sections[:8], title)})


@api.route("/v2/<capability>", methods=["GET", "POST"])
def phase2_placeholder(capability):
    known = {"cache", "predictions", "readmission-risk", "backup", "distributed", "local-llm"}
    if capability not in known:
        return fail("二期能力不存在", code=404), 404
    return fail(f"{capability} 已完成接口预留，将在二期启用", code=501, meta={"phase": 2, "enabled": False}), 501
