"""DeepSeek Anthropic 兼容 API 摘要生成与流式输出。"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from config import LLM_CONFIG
from app.ai_layer.knowledge import compact_context
from app.service_layer.analysis import registry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是智慧医疗大数据分析平台的数据分析助手。只能依据提供的聚合结果和口径知识回答，"
    "不得编造数字。用简洁、专业的中文指出主要结论、可能的管理含义和数据口径限制。"
    "不得输出个人医疗建议或诊断结论。控制在180字以内。"
)

PATIENT_SYSTEM_PROMPT = (
    "你是智慧医疗平台面向患者和家属的健康信息助手。只能依据提供的公开聚合结果和口径知识回答，"
    "使用通俗、克制的中文，不得编造数字，不得提供个人诊断、处方、用药或治疗建议。"
    "应明确说明内容仅供健康科普参考，如涉及个人症状应建议咨询专业医务人员。控制在180字以内。"
)

KNOWLEDGE_SYSTEM_PROMPT = (
    "你是智慧医疗大数据分析平台的知识助手。只能依据提供的检索片段回答；"
    "如果片段不足以回答，要明确说明缺少什么，不能补造事实或数字。"
    "区分统计人次与独立患者人数，动态数字以SQL元数据片段为准。"
    "不得提供个人诊断、处方、治疗或用药建议。控制在220字以内。"
)


def llm_available() -> bool:
    return bool(LLM_CONFIG.get("api_key"))


def _client():
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 anthropic SDK，请安装 requirements.txt") from exc
    return Anthropic(
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
        timeout=LLM_CONFIG["timeout"],
    )


def _prompt(data: dict, query: str, knowledge: list[dict] | None = None) -> str:
    compact = dict(data)
    if isinstance(compact.get("rows"), list):
        compact["rows"] = compact["rows"][:20]
    payload = json.dumps(compact, ensure_ascii=False, default=str)
    knowledge_text = compact_context(knowledge or [])
    support = f"\n相关口径知识：\n{knowledge_text}" if knowledge_text else ""
    return f"用户问题：{query or '请解读本次分析'}\n聚合结果：{payload}{support}\n聚合结果中的数字优先，请输出一段可直接展示的分析摘要。"


def stream_summary(
    data: dict, query: str = "", role: str = "doctor", knowledge: list[dict] | None = None,
) -> Iterator[str]:
    """逐段产出模型文本；缺少密钥或调用失败时产出模板摘要。"""
    if not llm_available():
        text = template_summary(data)
        if role == "patient":
            text += " 内容仅供健康科普参考，不构成个人诊断或治疗建议。"
        yield text
        return
    emitted = False
    try:
        client = _client()
        with client.messages.stream(
            model=LLM_CONFIG["model"],
            max_tokens=LLM_CONFIG["max_tokens"],
            temperature=LLM_CONFIG["temperature"],
            system=PATIENT_SYSTEM_PROMPT if role == "patient" else SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _prompt(data, query, knowledge)}],
        ) as stream:
            for text in stream.text_stream:
                if text:
                    emitted = True
                    yield text
    except Exception as exc:  # noqa: BLE001 - 外部服务必须兜底
        logger.warning("DeepSeek 流式生成失败: %s", exc.__class__.__name__)
        if not emitted:
            yield template_summary(data)


def generate_summary(
    data: dict, query: str = "", role: str = "doctor", knowledge: list[dict] | None = None,
) -> str:
    return "".join(stream_summary(data, query, role, knowledge)).strip()


def stream_knowledge_answer(documents: list[dict], query: str = "", role: str = "doctor") -> Iterator[str]:
    """基于最多3条检索片段回答定义、口径和平台元数据问题。"""
    if not documents:
        yield "知识库中没有找到足够依据，请补充问题中的指标、年份或分析对象。"
        return
    if not llm_available():
        yield knowledge_template(documents)
        return
    try:
        client = _client()
        prompt = f"用户问题：{query}\n检索片段：\n{compact_context(documents)}\n请直接回答，并简要说明数据口径。"
        with client.messages.stream(
            model=LLM_CONFIG["model"], max_tokens=LLM_CONFIG["max_tokens"],
            temperature=0, system=KNOWLEDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            emitted = False
            for text in stream.text_stream:
                if text:
                    emitted = True
                    yield text
            if not emitted:
                yield knowledge_template(documents)
    except Exception as exc:  # noqa: BLE001
        logger.warning("知识检索回答生成失败: %s", exc.__class__.__name__)
        yield knowledge_template(documents)


def generate_knowledge_answer(documents: list[dict], query: str = "", role: str = "doctor") -> str:
    return "".join(stream_knowledge_answer(documents, query, role)).strip()


def knowledge_template(documents: list[dict]) -> str:
    primary = documents[0]
    sources = "、".join(item["title"] for item in documents[:3])
    return f"{primary['content']} 依据：{sources}。"


def template_summary(data: dict) -> str:
    rows = data.get("rows", [])
    dimension = data.get("dimension_label") or data.get("dimension", "当前维度")
    if not rows:
        return f"未查询到「{dimension}」下的有效数据，请调整筛选条件后重试。"
    top = rows[0]
    label = top.get("dimension_value") or top.get("payment") or top.get("year") or "未标注"
    metrics = data.get("metrics") or []
    primary = data.get("sort_by") or (metrics[0] if metrics else "count")
    metric_labels = {key: spec.label for key, spec in registry.METRICS.items()}
    metric_labels.update({
        "case_mix_cost_index": "病例组合校正成本指数",
        "case_mix_los_index": "病例组合校正住院日指数",
        "hhi": "医院集中度 HHI",
        "growth_pct": "增长率",
        "absolute_growth": "绝对增长量",
        "records": "记录数",
    })
    if (data.get("filters") or {}).get("disease") and len(rows) == 1:
        if primary == "avg_length_of_stay" and top.get(primary) is not None:
            return (
                f"在当前数据中，「{label}」相关出院记录的平均住院日为 "
                f"{float(top[primary]):.1f} 天。这是群体历史平均值，不代表个人实际需要住院的时间；"
                "个人住院安排应由医务人员结合病情判断。"
            )
    text = f"本次按{dimension}统计，共得到 {len(rows)} 个分组；"
    if data.get("dimension") == "year" and not data.get("sort_by"):
        text += f"结果从「{label}」年份开始。"
    elif primary == "count":
        text += f"住院量排序首位的是「{label}」，共 {int(top.get('count') or 0):,} 条记录。"
    elif top.get(primary) is not None:
        value = float(top[primary])
        if primary == "avg_length_of_stay":
            formatted = f"{value:.1f} 天"
        elif primary == "quality_score" or registry.METRICS.get(primary, None) and registry.METRICS[primary].unit == "%":
            formatted = f"{value:.2f}%"
        elif registry.METRICS.get(primary, None) and registry.METRICS[primary].unit in {"USD", "USD/天"}:
            formatted = f"US${value:,.0f}" + ("/天" if registry.METRICS[primary].unit == "USD/天" else "")
        elif registry.METRICS.get(primary, None) and registry.METRICS[primary].unit == "倍":
            formatted = f"{value:.2f} 倍"
        else:
            formatted = f"{value:,.2f}"
        text += f"按{metric_labels.get(primary, primary)}排序首位的是「{label}」，指标值为 {formatted}。"
    else:
        text += f"排序首位的是「{label}」。"
    if top.get("ratio") is not None:
        text += f"其占总体的 {float(top['ratio']) * 100:.1f}%。"
    if top.get("avg_length_of_stay") is not None and primary != "avg_length_of_stay":
        text += f"该组平均住院日为 {float(top['avg_length_of_stay']):.1f} 天。"
    if top.get("avg_total_charges") is not None and primary != "avg_total_charges":
        text += f"次均费用约 US${float(top['avg_total_charges']):,.0f}。"
    caveats = data.get("caveats") or []
    if caveats:
        text += f" 口径提示：{str(caveats[0])}。"
    return text
