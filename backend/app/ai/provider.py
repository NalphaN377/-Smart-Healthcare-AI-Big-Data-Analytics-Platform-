from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import ProviderFailure, ProviderNotConfigured, ProviderTimeout, UnsupportedQuery
from .prompts import ROUTING_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT
from .schemas import (
    ConversationTurn,
    ProviderSummary,
    TokenUsage,
    ToolDecision,
    ToolResult,
)


class LLMProvider(Protocol):
    @property
    def configured(self) -> bool: ...

    @property
    def public_info(self) -> dict[str, str]: ...

    def choose_tool(self, query: str, history: list[ConversationTurn], registry) -> ToolDecision: ...

    def summarize(self, query: str, result: ToolResult) -> ProviderSummary: ...


class UnconfiguredProvider:
    configured = False

    @property
    def public_info(self) -> dict[str, str]:
        return {"name": "not_configured", "model": "not_configured"}

    def choose_tool(self, query: str, history: list[ConversationTurn], registry) -> ToolDecision:
        raise ProviderNotConfigured("LLM provider not configured")

    def summarize(self, query: str, result: ToolResult) -> ProviderSummary:
        raise ProviderNotConfigured("LLM provider not configured")


class OpenAICompatibleProvider:
    """LangChain chat-model adapter. Credentials remain inside the model client."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout_seconds: float = 30,
        thinking_mode: str = "disabled",
    ):
        self._api_key = api_key
        self._model_name = model
        self._base_url = base_url or None
        self._timeout_seconds = timeout_seconds
        normalized_thinking_mode = thinking_mode.strip().lower()
        if normalized_thinking_mode not in {"enabled", "disabled"}:
            raise ValueError("LLM_THINKING_MODE must be enabled or disabled")
        self._thinking_mode = normalized_thinking_mode

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._model_name)

    @property
    def public_info(self) -> dict[str, str]:
        return {
            "name": "openai_compatible",
            "model": self._model_name or "not_configured",
            "thinking_mode": self._thinking_mode,
        }

    def _model(self):
        if not self.configured:
            raise ProviderNotConfigured("LLM provider not configured")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=self._api_key,
            model=self._model_name,
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            temperature=0,
            max_retries=1,
            extra_body={"thinking": {"type": self._thinking_mode}},
        )

    def choose_tool(self, query: str, history: list[ConversationTurn], registry) -> ToolDecision:
        compact_history = [
            {
                "query": turn.query,
                "tool": turn.tool,
                "arguments": turn.arguments,
                "result_summary": turn.result_summary,
            }
            for turn in history[-10:]
        ]
        messages = [
            ("system", ROUTING_SYSTEM_PROMPT),
            (
                "human",
                "上下文："
                + json.dumps(compact_history, ensure_ascii=False)
                + "\n当前问题："
                + query,
            ),
        ]
        try:
            model = self._model().bind_tools(
                registry.langchain_tools(),
                tool_choice="required",
                parallel_tool_calls=False,
            )
            response = model.invoke(messages)
        except Exception as exc:
            self._raise_safe_provider_error(exc)
        calls = getattr(response, "tool_calls", None) or []
        if len(calls) != 1:
            raise UnsupportedQuery("the provider did not select exactly one supported analytics tool")
        call = calls[0]
        return ToolDecision(
            tool=call["name"],
            arguments=call.get("args") or {},
            token_usage=self._extract_usage(response),
        )

    def summarize(self, query: str, result: ToolResult) -> ProviderSummary:
        payload = result.model_dump(mode="json")
        try:
            response = self._model().invoke(
                [
                    ("system", SUMMARY_SYSTEM_PROMPT),
                    (
                        "human",
                        f"用户问题：{query}\n已验证工具结果："
                        + json.dumps(payload, ensure_ascii=False),
                    ),
                ]
            )
        except Exception as exc:
            self._raise_safe_provider_error(exc)
        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        if not isinstance(content, str) or not content.strip():
            raise ProviderFailure("LLM provider returned an empty response")
        return ProviderSummary(
            text=content.strip(),
            token_usage=self._extract_usage(response),
        )

    @staticmethod
    def _extract_usage(response) -> TokenUsage:
        usage_metadata = getattr(response, "usage_metadata", None) or {}
        response_metadata = getattr(response, "response_metadata", None) or {}
        provider_usage = response_metadata.get("token_usage") or {}
        input_details = usage_metadata.get("input_token_details") or {}
        input_tokens = int(
            usage_metadata.get("input_tokens")
            or provider_usage.get("prompt_tokens")
            or 0
        )
        output_tokens = int(
            usage_metadata.get("output_tokens")
            or provider_usage.get("completion_tokens")
            or 0
        )
        total_tokens = int(
            usage_metadata.get("total_tokens")
            or provider_usage.get("total_tokens")
            or input_tokens + output_tokens
        )
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cache_read_tokens=int(
                input_details.get("cache_read")
                or provider_usage.get("prompt_cache_hit_tokens")
                or 0
            ),
            cache_miss_tokens=int(provider_usage.get("prompt_cache_miss_tokens") or 0),
        )

    @staticmethod
    def _raise_safe_provider_error(error: Exception):
        error_name = error.__class__.__name__.lower()
        if "timeout" in error_name or isinstance(error, TimeoutError):
            raise ProviderTimeout("LLM provider request timed out") from error
        raise ProviderFailure("LLM provider request failed") from error


@dataclass
class DeterministicTestProvider:
    """Explicit test-only provider. It is never selected by environment configuration."""

    configured: bool = True

    @property
    def public_info(self) -> dict[str, str]:
        return {"name": "deterministic_test", "model": "rules-v1"}

    def choose_tool(self, query: str, history: list[ConversationTurn], registry) -> ToolDecision:
        text = re.sub(r"\s+", "", query)
        inherited = history[-1] if history and self._is_follow_up(text) else None
        arguments = dict(inherited.arguments) if inherited else {}
        tool = inherited.tool if inherited else ""

        limit = self._extract_limit(text)
        if limit is not None:
            arguments["limit"] = limit
        if any(token in text for token in ("70岁以上", "70岁及以上", "老年")):
            arguments["age_group"] = "70 or Older"

        if any(token in text for token in ("年度", "年份", "趋势", "2020到2024", "2020至2024")):
            tool = "get_year_trend"
            arguments = {key: value for key, value in arguments.items() if key not in {"metric"}}
        elif any(token in text for token in ("支付", "医保", "付款")):
            tool = "get_payment_distribution"
        elif any(token in text for token in ("严重程度", "病情程度", "重症程度")):
            tool = "get_severity_analysis"
            arguments["metric"] = (
                "average_length_of_stay"
                if any(token in text for token in ("住院时间", "住院天数", "住院日"))
                else "average_cost"
                if self._asks_cost(text)
                else "record_count"
            )
        elif any(token in text for token in ("年龄组", "年龄分布", "不同年龄")) and "疾病" not in text:
            tool = "get_age_analysis"
            arguments["metric"] = "average_cost" if self._asks_cost(text) else "distribution"
        elif any(token in text for token in ("医院", "医疗机构")):
            tool = "get_hospital_analysis"
            arguments["metric"] = "average_cost" if self._asks_cost(text) else "record_count"
        elif any(token in text for token in ("疾病", "诊断", "病种", "COVID")):
            tool = (
                "get_disease_cost_analysis" if self._asks_cost(text) else "get_top_diseases"
            )
        elif any(token in text for token in ("总体", "概览", "总住院", "总记录")):
            tool = "get_overview"
        elif inherited:
            if self._asks_cost(text):
                if tool == "get_top_diseases":
                    tool = "get_disease_cost_analysis"
                elif tool == "get_hospital_analysis":
                    arguments["metric"] = "average_cost"
                elif tool == "get_age_analysis":
                    arguments["metric"] = "average_cost"
        else:
            raise UnsupportedQuery("unsupported medical analytics question")

        if not tool:
            raise UnsupportedQuery("unsupported medical analytics question")
        allowed_fields = set(registry.definition(tool).schema.model_fields)
        arguments = {key: value for key, value in arguments.items() if key in allowed_fields}
        return ToolDecision(tool=tool, arguments=arguments)

    def summarize(self, query: str, result: ToolResult) -> ProviderSummary:
        return ProviderSummary(text=compose_deterministic_answer(query, result))

    @staticmethod
    def _is_follow_up(text: str) -> bool:
        return (
            len(text) <= 18
            or text.startswith(("那", "这些", "改成", "再看", "其中"))
            or text.endswith("呢")
        )

    @staticmethod
    def _asks_cost(text: str) -> bool:
        return any(token in text for token in ("费用", "成本", "花费", "最贵"))

    @staticmethod
    def _extract_limit(text: str) -> int | None:
        arabic = re.search(r"(?:前|最多的?|最高的?)(\d{1,2})", text)
        if not arabic:
            arabic = re.search(r"(\d{1,2})(?:种|个|家)", text)
        if arabic:
            value = int(arabic.group(1))
            return value if 1 <= value <= 50 else None
        chinese_numbers = {
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        match = re.search(r"(?:前|最多的?|最高的?)([一二两三四五六七八九十])", text)
        return chinese_numbers.get(match.group(1)) if match else None


def compose_deterministic_answer(query: str, result: ToolResult) -> str:
    if any(token in query for token in ("为什么", "原因", "导致")):
        neutral_query = query
        for token in ("为什么", "原因", "导致"):
            neutral_query = neutral_query.replace(token, "")
        observation = compose_deterministic_answer(neutral_query, result)
        return (
            f"数据观察：{observation} 数据边界：当前聚合统计数据无法证明该差异的原因，"
            "可能解释只能作为待验证假设，不能视为本数据结论。"
        )
    data = result.data
    if result.tool == "get_year_trend" and not result.meta.get("trend_available"):
        years = result.meta.get("available_years") or result.source.years
        year_text = "、".join(str(year) for year in years) or "当前单一年份"
        return f"当前数据仅包含 {year_text} 年，无法形成跨年度趋势，也不能推断 2020—2024 年的变化。"
    if isinstance(data, dict):
        if result.tool == "get_overview":
            return (
                f"数据观察：共 {int(data.get('total_records') or 0):,} 条住院记录，"
                f"涉及 {int(data.get('facility_count') or 0)} 家医疗机构，"
                f"平均住院 {float(data.get('avg_length_of_stay') or 0):.2f} 天，"
                f"平均总费用为 {float(data.get('avg_total_charges') or 0):,.2f}。"
            )
        return "已根据总体分析工具返回结构化统计结果。"
    if not data:
        return "当前筛选条件下没有可用统计结果。"

    limit = len(data)
    if result.tool == "get_top_diseases":
        details = "；".join(
            f"{index}. {row['diagnosis']}（{int(row['record_count']):,} 条）"
            for index, row in enumerate(data, 1)
        )
        return f"按住院记录数排序，前 {limit} 种疾病为：{details}。"
    if result.tool == "get_disease_cost_analysis":
        details = "；".join(
            f"{index}. {row['diagnosis']}（平均总费用 {float(row.get('avg_total_charges') or 0):,.2f}，平均总成本 {float(row.get('avg_total_costs') or 0):,.2f}）"
            for index, row in enumerate(data, 1)
        )
        return f"疾病费用分析前 {limit} 项：{details}。"
    if result.tool == "get_hospital_analysis":
        cost = result.meta.get("metric") == "average_cost"
        details = "；".join(
            (
                f"{index}. {row['hospital']}（平均总费用 {float(row.get('avg_total_charges') or 0):,.2f}）"
                if cost
                else f"{index}. {row['hospital']}（{int(row.get('record_count') or 0):,} 条）"
            )
            for index, row in enumerate(data, 1)
        )
        return f"医院{'平均费用' if cost else '住院记录数'}分析前 {limit} 项：{details}。"
    if result.tool == "get_age_analysis":
        cost = result.meta.get("metric") == "average_cost"
        details = "；".join(
            (
                f"{row['age_group']}：平均总费用 {float(row.get('avg_total_charges') or 0):,.2f}"
                if cost
                else f"{row['age_group']}：{int(row.get('record_count') or 0):,} 条"
            )
            for row in data
        )
        return f"年龄组{'费用' if cost else '住院记录数'}分析：{details}。"
    if result.tool == "get_payment_distribution":
        details = "；".join(
            f"{row['payment_type']}：{float(row.get('percentage') or 0):.2f}%（{int(row.get('record_count') or 0):,} 条）"
            for row in data
        )
        return f"支付方式分布：{details}。"
    if result.tool == "get_severity_analysis":
        details = "；".join(
            f"{row['severity']}：{int(row.get('record_count') or 0):,} 条，平均住院 {float(row.get('avg_length_of_stay') or 0):.2f} 天"
            for row in data
        )
        return f"病情严重程度分析：{details}。"
    details = "；".join(
        f"{row.get('year')} 年 {int(row.get('record_count') or 0):,} 条" for row in data
    )
    return f"年度统计：{details}。"


def build_provider(config: dict[str, Any]) -> LLMProvider:
    provider_name = str(config.get("AI_PROVIDER", "openai_compatible")).strip().lower()
    if provider_name != "openai_compatible":
        return UnconfiguredProvider()
    api_key = str(config.get("LLM_API_KEY", ""))
    model = str(config.get("LLM_MODEL", ""))
    if not api_key or not model:
        return UnconfiguredProvider()
    return OpenAICompatibleProvider(
        api_key=api_key,
        model=model,
        base_url=str(config.get("LLM_BASE_URL", "")) or None,
        timeout_seconds=float(config.get("LLM_TIMEOUT_SECONDS", 30)),
        thinking_mode=str(config.get("LLM_THINKING_MODE", "disabled")),
    )
