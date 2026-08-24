"""DeepSeek Anthropic 兼容 API 摘要生成与流式输出。"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from config import LLM_CONFIG

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是智慧医疗大数据分析平台的数据分析助手。只能依据提供的聚合结果回答，"
    "不得编造数字。用简洁、专业的中文指出主要结论、可能的管理含义和数据口径限制。"
    "不得输出个人医疗建议或诊断结论。控制在180字以内。"
)

PATIENT_SYSTEM_PROMPT = (
    "你是智慧医疗平台面向患者和家属的健康信息助手。只能依据提供的公开聚合结果回答，"
    "使用通俗、克制的中文，不得编造数字，不得提供个人诊断、处方、用药或治疗建议。"
    "应明确说明内容仅供健康科普参考，如涉及个人症状应建议咨询专业医务人员。控制在180字以内。"
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


def _prompt(data: dict, query: str) -> str:
    compact = dict(data)
    if isinstance(compact.get("rows"), list):
        compact["rows"] = compact["rows"][:20]
    payload = json.dumps(compact, ensure_ascii=False, default=str)
    return f"用户问题：{query or '请解读本次分析'}\n聚合结果：{payload}\n请输出一段可直接展示的分析摘要。"


def stream_summary(data: dict, query: str = "", role: str = "doctor") -> Iterator[str]:
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
            messages=[{"role": "user", "content": _prompt(data, query)}],
        ) as stream:
            for text in stream.text_stream:
                if text:
                    emitted = True
                    yield text
    except Exception as exc:  # noqa: BLE001 - 外部服务必须兜底
        logger.warning("DeepSeek 流式生成失败: %s", exc.__class__.__name__)
        if not emitted:
            yield template_summary(data)


def generate_summary(data: dict, query: str = "", role: str = "doctor") -> str:
    return "".join(stream_summary(data, query, role)).strip()


def template_summary(data: dict) -> str:
    rows = data.get("rows", [])
    dimension = data.get("dimension_label") or data.get("dimension", "当前维度")
    if not rows:
        return f"未查询到「{dimension}」下的有效数据，请调整筛选条件后重试。"
    top = rows[0]
    label = top.get("dimension_value") or top.get("payment") or top.get("year") or "未标注"
    metrics = data.get("metrics") or []
    primary = data.get("sort_by") or (metrics[0] if metrics else "count")
    metric_labels = {
        "count": "住院量", "avg_length_of_stay": "平均住院日", "avg_total_charges": "次均费用",
        "sum_total_charges": "总费用", "avg_total_costs": "次均成本", "sum_total_costs": "总成本",
    }
    text = f"本次按{dimension}统计，共得到 {len(rows)} 个分组；"
    if data.get("dimension") == "year" and not data.get("sort_by"):
        text += f"结果从「{label}」年份开始。"
    elif primary == "count":
        text += f"住院量排序首位的是「{label}」，共 {int(top.get('count') or 0):,} 条记录。"
    elif top.get(primary) is not None:
        value = float(top[primary])
        if primary == "avg_length_of_stay":
            formatted = f"{value:.1f} 天"
        else:
            formatted = f"{value:,.0f} 元"
        text += f"按{metric_labels.get(primary, primary)}排序首位的是「{label}」，指标值为 {formatted}。"
    else:
        text += f"排序首位的是「{label}」。"
    if top.get("ratio") is not None:
        text += f"其占总体的 {float(top['ratio']) * 100:.1f}%。"
    if top.get("avg_length_of_stay") is not None and primary != "avg_length_of_stay":
        text += f"该组平均住院日为 {float(top['avg_length_of_stay']):.1f} 天。"
    if top.get("avg_total_charges") is not None and primary != "avg_total_charges":
        text += f"次均费用约 {float(top['avg_total_charges']):,.0f} 元。"
    return text
