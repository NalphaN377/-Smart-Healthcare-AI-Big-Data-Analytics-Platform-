"""LangChain AI Agent：系统大脑，串联「意图识别 → 数据分析 → 文本/图表生成」。

对应文档功能：
- 「智能工具调用」：解析意图 → 匹配并调用分析 API。
- 「分析结果文本生成」「大屏可视化」：整合分析结果生成摘要与图表配置。

说明：本项目 Agent 的核心是「意图 → 工具调用」的编排。默认实现为
同进程直接调用服务层聚合函数（零网络开销、易调试）；如需严格按文档
走 HTTP API，可将 _fetch_data 改为 requests 调用 RESTful 接口。
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.ai_layer.chart_gen import generate_chart_option
from app.ai_layer.intent import detect_intent, detect_intent_with_llm
from app.ai_layer.knowledge import retrieve
from app.ai_layer.text_gen import (
    generate_knowledge_answer, generate_summary, stream_knowledge_answer, stream_summary,
)
from config import FEATURES, LLM_CONFIG

logger = logging.getLogger(__name__)


class MedicalAgent:
    """医疗大数据分析 Agent。"""

    def __init__(self, use_llm_intent: bool = False):
        self.use_llm_intent = use_llm_intent

    def analyze(self, query: str, role: str = "doctor", history: list[dict] | None = None) -> dict:
        """执行一次完整的智能分析闭环。

        Returns:
            {
                "intent": {...},
                "data": {...},        # 服务层返回的分析结果
                "summary": "...",     # 文字摘要
                "chart": {...},       # ECharts 配置
            }
        """
        # 1. 意图识别
        context = self.prepare(query, role, history)
        if context.get("direct_answer"):
            summary = context["direct_answer"]
        elif context.get("answer_mode") == "knowledge":
            summary = generate_knowledge_answer(context.get("knowledge") or [], query, role)
        else:
            summary = generate_summary(context["data"], query, role, context.get("knowledge"))
        return {**context, "summary": summary}

    def prepare(self, query: str, role: str = "doctor", history: list[dict] | None = None) -> dict:
        """准备流式/非流式请求共享的结构化分析上下文。"""
        intent = detect_intent_with_llm(query, history) if self.use_llm_intent else detect_intent(query)
        knowledge = retrieve(query, role)

        if intent.get("status") == "ready" and intent.get("topic"):
            from app.service_layer.analysis import mining

            data = mining.topic_analysis(
                intent["topic"], role=role, filters=intent.get("filters"), limit=intent.get("limit", 100),
                dimension=intent.get("dimension"), metrics=intent.get("metrics"),
            )
            chart = generate_chart_option(data, intent.get("chart_type", "bar"))
            return self._context(intent, role, data=data, chart=chart, knowledge=knowledge, answer_mode="structured")

        if role == "patient" and intent.get("status") == "ready":
            allowed_dimensions = {"disease", "year", "service_area"}
            allowed_metrics = {"count", "avg_length_of_stay", "avg_total_charges"}
            if intent.get("dimension") not in allowed_dimensions or not set(intent.get("metrics") or []) <= allowed_metrics:
                intent = {
                    **intent,
                    "status": "unsupported",
                    "chart_requested": False,
                    "message": "患者用户仅可查询公开的疾病、年度和服务区域趋势，当前问题暂不生成图表。",
                }

        if intent.get("status") != "ready":
            message = str(intent.get("message") or "")
            medical_block = "专业医务人员" in message or "个人症状" in message
            if knowledge and not medical_block:
                return self._context(
                    intent, role, data={"rows": []}, chart=None,
                    knowledge=knowledge, answer_mode="knowledge",
                )
            return self._context(
                intent, role, data={"rows": []}, chart=None,
                direct_answer=message, knowledge=[], answer_mode="direct",
            )

        # 2. 调用服务层获取数据
        data = self._fetch_data(intent, role)

        # 3. 只有已确认的分析意图且确有数据时才生成图表。
        chart = (
            generate_chart_option(data, intent["chart_type"], value_field=intent.get("sort_by"))
            if intent.get("chart_requested") else None
        )
        return self._context(intent, role, data=data, chart=chart, knowledge=knowledge, answer_mode="structured")

    @staticmethod
    def _context(
        intent: dict, role: str, data: dict, chart, direct_answer: str | None = None,
        knowledge: list[dict] | None = None, answer_mode: str = "structured",
    ) -> dict:
        return {
            "request_id": uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "intent": intent,
            "data": data,
            "chart": chart,
            "direct_answer": direct_answer,
            "answer_mode": answer_mode,
            "knowledge": knowledge or [],
            "knowledge_sources": [item.get("title") for item in (knowledge or [])],
            "model": LLM_CONFIG["model"],
            "audience": role,
        }

    @staticmethod
    def stream(context: dict):
        if context.get("direct_answer"):
            yield context["direct_answer"]
            return
        if context.get("answer_mode") == "knowledge":
            yield from stream_knowledge_answer(
                context.get("knowledge") or [], context["intent"]["query"], context.get("audience", "doctor"),
            )
            return
        yield from stream_summary(
            context["data"], context["intent"]["query"], context.get("audience", "doctor"),
            context.get("knowledge"),
        )

    def _fetch_data(self, intent: dict, role: str = "doctor") -> dict:
        """根据意图调用服务层聚合分析（对应「智能工具调用」）。"""
        from app.service_layer.analysis import aggregation

        dimension = intent["dimension"]
        metrics = intent["metrics"]

        if role == "patient":
            allowed_dimensions = {"disease", "year", "service_area"}
            allowed_metrics = {"count", "avg_length_of_stay", "avg_total_charges"}
            if dimension not in allowed_dimensions or not set(metrics) <= allowed_metrics:
                raise ValueError("患者用户仅可查询公开疾病趋势、年度趋势和服务区域概览")
            intent["limit"] = min(int(intent.get("limit", 10)), 10)
            intent["filters"] = {
                key: value for key, value in (intent.get("filters") or {}).items()
                if key in {"year", "year_from", "year_to", "disease", "service_area"}
            }

        # 支付方式占比走专门接口（带 ratio）
        if dimension == "payment" and set(metrics) <= {"count"}:
            return aggregation.payment_ratio(
                limit=intent.get("limit", 20), filters=intent.get("filters"), role=role,
            )

        data = aggregation.aggregate(
            dimension,
            metrics=metrics,
            limit=intent.get("limit", 20),
            filters=intent.get("filters"),
            sort_by=intent.get("sort_by"),
            sort_order=intent.get("sort_order", "desc"),
            role=role,
        )
        if role == "patient" and isinstance(data.get("rows"), list):
            data["rows"] = [row for row in data["rows"] if int(row.get("count") or 0) >= 11]
        return data


# 模块级单例（供 Flask 路由复用）
_agent: Optional[MedicalAgent] = None


def get_agent() -> MedicalAgent:
    """获取全局 Agent 单例。"""
    global _agent
    if _agent is None:
        _agent = MedicalAgent(use_llm_intent=FEATURES["llm_intent"])
    return _agent
