#!/usr/bin/env python3
"""Run Phase 2B routing/grounding/chart checks against the configured real MySQL data.

This script deliberately uses the deterministic test provider so it never consumes an
external API key or represents test output as a production LLM response.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ai.agent import MedicalAnalyticsAgent  # noqa: E402
from backend.app.ai.provider import DeterministicTestProvider  # noqa: E402
from backend.app.ai.session import InMemoryConversationStore  # noqa: E402
from backend.app.ai.tools import ToolRegistry  # noqa: E402
from backend.app.config import Config  # noqa: E402
from backend.app.repositories.analytics_repository import AnalyticsRepository  # noqa: E402


QUESTIONS = [
    "总体住院情况如何？",
    "住院人数最多的五种疾病是什么？",
    "哪些疾病的平均住院费用最高？",
    "哪些医院的住院病例最多？",
    "哪些医院的平均费用最高？",
    "不同年龄组的住院量是多少？",
    "不同年龄组的平均费用有什么差异？",
    "不同支付方式占比是多少？",
    "不同病情严重程度的平均住院时间是多少？",
    "2020到2024趋势如何？",
]

MULTI_TURN = [
    ("住院费用最高的五种疾病是什么？", "那70岁以上呢？"),
    ("住院人数最多的五种疾病是什么？", "改成前三"),
    ("哪些医院的住院病例最多？", "那这些医院的费用呢？"),
]


def main() -> int:
    repository = AnalyticsRepository(vars(Config))
    agent = MedicalAnalyticsAgent(
        provider=DeterministicTestProvider(),
        registry=ToolRegistry(repository),
        conversation_store=InMemoryConversationStore(max_turns=10),
    )
    started = perf_counter()
    validations = []
    for question in QUESTIONS:
        data, meta = agent.query(question)
        validations.append(
            {
                "question": question,
                "tool": data.tool_calls[0].tool,
                "arguments": data.tool_calls[0].arguments,
                "tool_elapsed_ms": data.tool_calls[0].elapsed_ms,
                "total_elapsed_ms": meta["elapsed_ms"],
                "chart_type": data.chart.type,
                "chart_status": data.chart.status,
                "source_records": data.sources[0].record_count,
                "source_years": data.sources[0].years,
                "answer": data.answer,
            }
        )

    conversations = []
    for first_question, follow_up in MULTI_TURN:
        first, _ = agent.query(first_question)
        second, meta = agent.query(follow_up, first.session_id)
        conversations.append(
            {
                "first": first_question,
                "follow_up": follow_up,
                "inherited_tool": second.tool_calls[0].tool,
                "inherited_arguments": second.tool_calls[0].arguments,
                "turn_count": second.turn_count,
                "total_elapsed_ms": meta["elapsed_ms"],
            }
        )

    overview = repository.overview({})
    report = {
        "provider": "deterministic_test (validation only; never production UI)",
        "database": {
            "total_records": int(overview["total_records"]),
            "facility_count": int(overview["facility_count"]),
        },
        "questions": validations,
        "multi_turn": conversations,
        "elapsed_ms": round((perf_counter() - started) * 1000),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
