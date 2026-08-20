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


def stream_summary(data: dict, query: str = "") -> Iterator[str]:
    """逐段产出模型文本；缺少密钥或调用失败时产出模板摘要。"""
    if not llm_available():
        yield template_summary(data)
        return
    emitted = False
    try:
        client = _client()
        with client.messages.stream(
            model=LLM_CONFIG["model"],
            max_tokens=LLM_CONFIG["max_tokens"],
            temperature=LLM_CONFIG["temperature"],
            system=SYSTEM_PROMPT,
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


def generate_summary(data: dict, query: str = "") -> str:
    return "".join(stream_summary(data, query)).strip()


def template_summary(data: dict) -> str:
    rows = data.get("rows", [])
    dimension = data.get("dimension_label") or data.get("dimension", "当前维度")
    if not rows:
        return f"未查询到「{dimension}」下的有效数据，请调整筛选条件后重试。"
    top = rows[0]
    label = top.get("dimension_value") or top.get("payment") or top.get("year") or "未标注"
    count = int(top.get("count") or 0)
    text = f"本次按{dimension}统计，共得到 {len(rows)} 个分组；数量最高的是「{label}」，共 {count:,} 条记录。"
    if top.get("ratio") is not None:
        text += f"其占总体的 {float(top['ratio']) * 100:.1f}%。"
    if top.get("avg_length_of_stay") is not None:
        text += f"该组平均住院日为 {float(top['avg_length_of_stay']):.1f} 天。"
    if top.get("avg_total_charges") is not None:
        text += f"次均费用约 {float(top['avg_total_charges']):,.0f} 元。"
    return text
