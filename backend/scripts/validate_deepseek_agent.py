#!/usr/bin/env python3
"""Run the real DeepSeek Phase 2B acceptance without exposing credentials."""

from __future__ import annotations

import json
import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import create_app


EXPECTED_RECORDS = 2_094_483
EXPECTED_YEAR = 2021


@dataclass(frozen=True)
class ValidationCase:
    question: str
    expected_tool: str
    expected_arguments: dict[str, Any]


SINGLE_TURN_CASES = (
    ValidationCase("总体住院情况如何？", "get_overview", {}),
    ValidationCase("住院人数最多的五种疾病是什么？", "get_top_diseases", {"limit": 5}),
    ValidationCase("哪些疾病平均费用最高？", "get_disease_cost_analysis", {"limit": 10}),
    ValidationCase(
        "哪些医院病例最多？",
        "get_hospital_analysis",
        {"limit": 10, "metric": "record_count"},
    ),
    ValidationCase(
        "哪些医院平均费用最高？",
        "get_hospital_analysis",
        {"limit": 10, "metric": "average_cost"},
    ),
    ValidationCase(
        "不同年龄组住院量如何？",
        "get_age_analysis",
        {"limit": 10, "metric": "distribution"},
    ),
    ValidationCase(
        "不同年龄组平均费用有什么差异？",
        "get_age_analysis",
        {"limit": 10, "metric": "average_cost"},
    ),
    ValidationCase("不同支付方式占比是多少？", "get_payment_distribution", {"limit": 10}),
    ValidationCase(
        "不同病情严重程度平均住院时间是多少？",
        "get_severity_analysis",
        {"limit": 10, "metric": "average_length_of_stay"},
    ),
    ValidationCase("2020–2024 年住院趋势如何？", "get_year_trend", {"limit": 20}),
)


MULTI_TURN_CASES = (
    (
        "A",
        ValidationCase(
            "住院费用最高的五种疾病是什么？",
            "get_disease_cost_analysis",
            {"limit": 5},
        ),
        ValidationCase(
            "那70岁以上呢？",
            "get_disease_cost_analysis",
            {"limit": 5, "age_group": "70 or Older"},
        ),
    ),
    (
        "B",
        ValidationCase("住院人数最多的五种疾病是什么？", "get_top_diseases", {"limit": 5}),
        ValidationCase("改成前三", "get_top_diseases", {"limit": 3}),
    ),
    (
        "C",
        ValidationCase(
            "哪些医院病例最多？",
            "get_hospital_analysis",
            {"limit": 10, "metric": "record_count"},
        ),
        ValidationCase(
            "那这些医院的费用呢？",
            "get_hospital_analysis",
            {"limit": 10, "metric": "average_cost"},
        ),
    ),
)


def validate_case(agent, case: ValidationCase, session_id: str | None = None):
    data, meta = agent.query(case.question, session_id)
    call = data.tool_calls[0]
    assert call.tool == case.expected_tool, (case.question, call.tool, case.expected_tool)
    for key, expected in case.expected_arguments.items():
        assert call.arguments.get(key) == expected, (
            case.question,
            key,
            call.arguments,
            expected,
        )
    source = data.sources[0]
    assert source.record_count == EXPECTED_RECORDS
    assert source.years == [EXPECTED_YEAR]
    assert source.storage == "MySQL analytics service"
    assert data.provider["model"] == "deepseek-v4-flash"
    assert data.provider["thinking_mode"] == "disabled"
    assert meta["grounded"] is True
    if call.tool == "get_year_trend":
        assert data.chart.status == "unavailable"
        assert "仅包含 2021 年" in data.answer
        assert "无法形成跨年度趋势" in data.answer
        # The refusal may repeat the user's requested range, but it must not attach
        # fabricated record counts or trend values to unavailable years.
        assert not re.search(r"202[0234]\s*年[^。；\n]{0,30}\d[\d,]*\s*条", data.answer)
    else:
        assert data.chart.status == "available"
        assert data.chart.data

    output = {
        "question": case.question,
        "model": data.provider["model"],
        "thinking_mode": data.provider["thinking_mode"],
        "selected_tool": call.tool,
        "arguments": call.arguments,
        "llm_latency_ms": meta["provider_routing_ms"] + meta["provider_summary_ms"],
        "routing_latency_ms": meta["provider_routing_ms"],
        "tool_mysql_latency_ms": meta["tool_elapsed_ms"],
        "summary_latency_ms": meta["provider_summary_ms"],
        "total_latency_ms": meta["elapsed_ms"],
        "token_usage": meta["token_usage"],
        "routing_token_usage": meta["routing_token_usage"],
        "summary_token_usage": meta["summary_token_usage"],
        "grounding_fallback": meta["grounding_fallback"],
        "grounding_fallback_reason": meta["grounding_fallback_reason"],
        "chart": {"type": data.chart.type, "status": data.chart.status},
        "source": source.model_dump(mode="json"),
        "answer": data.answer,
        "session_id": data.session_id,
        "turn_count": data.turn_count,
    }
    print(json.dumps(output, ensure_ascii=False), flush=True)
    return data, meta


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--single-start",
        type=int,
        default=1,
        choices=range(1, len(SINGLE_TURN_CASES) + 2),
        metavar=f"1-{len(SINGLE_TURN_CASES) + 1}",
    )
    parser.add_argument("--skip-multi", action="store_true")
    args = parser.parse_args()
    app = create_app()
    provider = app.extensions["ai_provider"]
    if not provider.configured:
        raise RuntimeError("real LLM provider is not configured")
    safe_status = {
        "event": "start",
        "provider": provider.public_info,
        "single_turn_cases": len(SINGLE_TURN_CASES),
        "multi_turn_groups": len(MULTI_TURN_CASES),
    }
    print(json.dumps(safe_status, ensure_ascii=False), flush=True)
    agent = app.extensions["medical_analytics_agent"]
    results = []

    for index, case in enumerate(SINGLE_TURN_CASES[args.single_start - 1 :], args.single_start):
        data, meta = validate_case(agent, case)
        results.append((data, meta))
        print(json.dumps({"event": "single_turn_pass", "case": index}), flush=True)

    for group, first, follow_up in (() if args.skip_multi else MULTI_TURN_CASES):
        first_data, first_meta = validate_case(agent, first)
        second_data, second_meta = validate_case(agent, follow_up, first_data.session_id)
        assert second_data.session_id == first_data.session_id
        assert second_data.turn_count == 2
        results.extend(((first_data, first_meta), (second_data, second_meta)))
        print(json.dumps({"event": "multi_turn_pass", "group": group}), flush=True)

    total_usage = {
        key: sum(meta["token_usage"][key] for _, meta in results)
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_read_tokens",
            "cache_miss_tokens",
        )
    }
    totals = {
        "event": "complete",
        "queries": len(results),
        "all_passed": True,
        "total_token_usage": total_usage,
        "total_latency_ms": sum(meta["elapsed_ms"] for _, meta in results),
        "total_llm_latency_ms": sum(
            meta["provider_routing_ms"] + meta["provider_summary_ms"]
            for _, meta in results
        ),
        "total_tool_mysql_latency_ms": sum(meta["tool_elapsed_ms"] for _, meta in results),
        "grounding_fallbacks": sum(
            1 for _, meta in results if meta["grounding_fallback"]
        ),
    }
    print(json.dumps(totals, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
