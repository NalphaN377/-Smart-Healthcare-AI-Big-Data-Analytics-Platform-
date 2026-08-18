from __future__ import annotations

import re
from time import perf_counter
from typing import Any

from .chart import ChartPlanner
from .provider import compose_deterministic_answer
from .schemas import AIQueryData, ConversationTurn, ProviderSummary, ToolCallAudit, ToolResult


class GroundingGuard:
    """Rejects invented years/numbers and falls back to a deterministic rendering."""

    NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?%?")

    def validate_or_fallback(
        self,
        query: str,
        answer: str,
        result: ToolResult,
    ) -> tuple[str, bool, str | None]:
        if any(currency in answer for currency in ("美元", "人民币", "元")):
            return compose_deterministic_answer(query, result), True, "currency_not_in_tool_result"
        if self._metric_label_mismatch(answer, result):
            return compose_deterministic_answer(query, result), True, "metric_label_mismatch"
        if not self._category_labels_grounded(answer, result):
            return compose_deterministic_answer(query, result), True, "category_label_not_grounded"

        allowed_numbers: set[float] = set()
        allowed_tokens: set[str] = set()
        self._collect(result.model_dump(mode="json"), allowed_numbers, allowed_tokens)
        for value in list(allowed_numbers):
            allowed_numbers.update({round(value), round(value, 1), round(value, 2), value * 100})
        if isinstance(result.data, list):
            allowed_numbers.update(float(rank) for rank in range(1, len(result.data) + 1))

        for token in self.NUMBER_PATTERN.findall(answer):
            normalized = token.rstrip("%").replace(",", "")
            try:
                numeric = float(normalized)
            except ValueError:
                continue
            if token.rstrip("%") in allowed_tokens:
                continue
            if not any(abs(numeric - allowed) <= max(0.01, abs(allowed) * 1e-6) for allowed in allowed_numbers):
                return compose_deterministic_answer(query, result), True, "number_not_in_tool_result"

        answer_years = {int(value) for value in re.findall(r"\b(?:19|20)\d{2}\b", answer)}
        if not answer_years.issubset(set(result.source.years)):
            return compose_deterministic_answer(query, result), True, "unavailable_year"
        if any(token in query for token in ("为什么", "原因", "导致")) and not any(
            token in answer for token in ("无法证明", "不能证明", "无法确定", "数据不支持")
        ):
            return compose_deterministic_answer(query, result), True, "causality_boundary_missing"
        return answer, False, None

    def _metric_label_mismatch(self, answer: str, result: ToolResult) -> bool:
        rows = result.data if isinstance(result.data, list) else [result.data]
        charges = self._metric_values(rows, "avg_total_charges")
        costs = self._metric_values(rows, "avg_total_costs")
        plain_answer = answer.replace("*", "")
        patterns = (
            (
                re.compile(
                    r"(?:平均)?(?:总)?费用(?:\s*[（(][^）)]{0,30}[）)])?"
                    r"\s*(?:为|是|[:：])?\s*(\d[\d,]*(?:\.\d+)?)"
                ),
                charges,
            ),
            (
                re.compile(
                    r"(?:平均)?(?:总)?成本(?:\s*[（(][^）)]{0,30}[）)])?"
                    r"\s*(?:为|是|[:：])?\s*(\d[\d,]*(?:\.\d+)?)"
                ),
                costs,
            ),
        )
        for pattern, allowed_values in patterns:
            if not allowed_values:
                continue
            for match in pattern.finditer(plain_answer):
                numeric = float(match.group(1).replace(",", ""))
                if not self._number_matches(numeric, allowed_values):
                    return True
        return False

    @staticmethod
    def _metric_values(rows: list[dict[str, Any]], field: str) -> set[float]:
        values: set[float] = set()
        for row in rows:
            value = row.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                number = float(value)
                values.update({number, round(number), round(number, 1), round(number, 2)})
        return values

    @staticmethod
    def _number_matches(number: float, allowed_values: set[float]) -> bool:
        return any(
            abs(number - allowed) <= max(0.01, abs(allowed) * 1e-6)
            for allowed in allowed_values
        )

    @staticmethod
    def _category_labels_grounded(answer: str, result: ToolResult) -> bool:
        if not isinstance(result.data, list) or not result.data:
            return True
        category_field = {
            "get_top_diseases": "diagnosis",
            "get_disease_cost_analysis": "diagnosis",
            "get_hospital_analysis": "hospital",
            "get_payment_distribution": "payment_type",
            "get_severity_analysis": "severity",
        }.get(result.tool)
        if not category_field:
            return True
        labels = [
            str(row[category_field])
            for row in result.data
            if row.get(category_field) not in (None, "")
        ]
        return not labels or any(label in answer for label in labels)

    def _collect(self, value: Any, numbers: set[float], tokens: set[str]) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            numbers.add(float(value))
            tokens.add(str(value))
            return
        if isinstance(value, str):
            for token in self.NUMBER_PATTERN.findall(value):
                tokens.add(token.rstrip("%"))
                try:
                    numbers.add(float(token.rstrip("%").replace(",", "")))
                except ValueError:
                    pass
            return
        if isinstance(value, dict):
            for item in value.values():
                self._collect(item, numbers, tokens)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                self._collect(item, numbers, tokens)


class MedicalAnalyticsAgent:
    def __init__(self, *, provider, registry, conversation_store, chart_planner=None):
        self.provider = provider
        self.registry = registry
        self.conversation_store = conversation_store
        self.chart_planner = chart_planner or ChartPlanner()
        self.grounding_guard = GroundingGuard()

    def query(self, query: str, session_id: str | None = None) -> tuple[AIQueryData, dict[str, Any]]:
        started = perf_counter()
        if any(
            token in query
            for token in (
                "给我开药",
                "用药建议",
                "治疗方案",
                "诊断我",
                "我该吃什么药",
                "我是否应该手术",
                "查看个人病历",
            )
        ):
            from .errors import UnsupportedQuery

            raise UnsupportedQuery("individual medical advice is outside analytics scope")
        if not self.provider.configured:
            # Check before touching analytics storage so Phase 1 APIs stay independent.
            self.provider.choose_tool(query, [], self.registry)

        session_id = session_id or self.conversation_store.create_session()
        history = self.conversation_store.history(session_id)

        routing_started = perf_counter()
        decision = self.provider.choose_tool(query, history, self.registry)
        routing_ms = self._elapsed(routing_started)

        definition = self.registry.definition(decision.tool)
        result = self.registry.execute(decision.tool, decision.arguments)
        normalized_arguments = definition.schema.model_validate(
            decision.arguments
        ).model_dump(exclude_none=True)
        chart = self.chart_planner.plan(result)

        summary_started = perf_counter()
        provider_summary = self.provider.summarize(query, result)
        if isinstance(provider_summary, str):
            # Backward-compatible boundary for explicitly injected legacy test providers.
            provider_summary = ProviderSummary(text=provider_summary)
        summary_ms = self._elapsed(summary_started)
        answer, grounding_fallback, grounding_fallback_reason = self.grounding_guard.validate_or_fallback(
            query,
            provider_summary.text,
            result,
        )
        combined_usage = decision.token_usage + provider_summary.token_usage

        turn_count = self.conversation_store.append(
            session_id,
            ConversationTurn(
                query=query,
                tool=result.tool,
                arguments=normalized_arguments,
                result_summary=self._small_summary(result),
            ),
        )
        data = AIQueryData(
            answer=answer,
            tool_calls=[
                ToolCallAudit(
                    tool=result.tool,
                    arguments=normalized_arguments,
                    elapsed_ms=result.elapsed_ms,
                )
            ],
            chart=chart,
            sources=[result.source],
            session_id=session_id,
            turn_count=turn_count,
            provider=self.provider.public_info,
        )
        return data, {
            "elapsed_ms": self._elapsed(started),
            "provider_routing_ms": routing_ms,
            "tool_elapsed_ms": result.elapsed_ms,
            "provider_summary_ms": summary_ms,
            "grounded": True,
            "grounding_fallback": grounding_fallback,
            "grounding_fallback_reason": grounding_fallback_reason,
            "token_usage": combined_usage.model_dump(mode="json"),
            "routing_token_usage": decision.token_usage.model_dump(mode="json"),
            "summary_token_usage": provider_summary.token_usage.model_dump(mode="json"),
        }

    @staticmethod
    def _small_summary(result: ToolResult):
        if isinstance(result.data, list):
            return result.data[:3]
        keys = (
            "total_records",
            "facility_count",
            "avg_length_of_stay",
            "avg_total_charges",
        )
        return {key: result.data.get(key) for key in keys if key in result.data}

    @staticmethod
    def _elapsed(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))
