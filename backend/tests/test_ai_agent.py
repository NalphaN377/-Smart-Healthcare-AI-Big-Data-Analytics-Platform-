import pytest

from backend.app.ai.agent import MedicalAnalyticsAgent
from backend.app.ai.errors import UnsupportedQuery
from backend.app.ai.provider import DeterministicTestProvider
from backend.app.ai.session import InMemoryConversationStore
from backend.app.ai.tools import ToolRegistry
from backend.tests.conftest import FakeAnalyticsRepository


def make_agent():
    return MedicalAnalyticsAgent(
        provider=DeterministicTestProvider(),
        registry=ToolRegistry(FakeAnalyticsRepository()),
        conversation_store=InMemoryConversationStore(max_turns=10),
    )


def test_required_question_routes_to_real_analytics_tool_with_limit_five():
    data, meta = make_agent().query("住院人数最多的5种疾病是什么？")
    call = data.tool_calls[0]
    assert call.tool == "get_top_diseases"
    assert call.arguments == {"limit": 5}
    assert "Disease 1" in data.answer
    assert data.chart.type == "horizontal_bar"
    assert data.sources[0].record_count == 4
    assert meta["grounded"] is True


@pytest.mark.parametrize(
    ("question", "expected_tool"),
    [
        ("总体住院情况如何？", "get_overview"),
        ("住院人数最多的五种疾病是什么？", "get_top_diseases"),
        ("哪些疾病的平均住院费用最高？", "get_disease_cost_analysis"),
        ("哪些医院的住院病例最多？", "get_hospital_analysis"),
        ("哪些医院的平均费用最高？", "get_hospital_analysis"),
        ("不同年龄组的住院量是多少？", "get_age_analysis"),
        ("不同年龄组的平均费用有什么差异？", "get_age_analysis"),
        ("不同支付方式占比是多少？", "get_payment_distribution"),
        ("不同病情严重程度的平均住院时间是多少？", "get_severity_analysis"),
        ("2020到2024趋势如何？", "get_year_trend"),
    ],
)
def test_natural_language_routes(question, expected_tool):
    data, _ = make_agent().query(question)
    assert data.tool_calls[0].tool == expected_tool


def test_single_year_question_never_invents_cross_year_trend():
    data, _ = make_agent().query("2020到2024趋势如何？")
    assert data.chart.status == "unavailable"
    assert "仅包含 2021 年" in data.answer
    assert "无法形成跨年度趋势" in data.answer
    assert "2022" not in data.answer


def test_three_multi_turn_context_patterns():
    agent = make_agent()

    first, _ = agent.query("住院费用最高的五种疾病是什么？")
    second, _ = agent.query("那70岁以上呢？", first.session_id)
    assert second.tool_calls[0].tool == "get_disease_cost_analysis"
    assert second.tool_calls[0].arguments["limit"] == 5
    assert second.tool_calls[0].arguments["age_group"] == "70 or Older"

    third, _ = agent.query("住院人数最多的五种疾病是什么？")
    fourth, _ = agent.query("改成前三", third.session_id)
    assert fourth.tool_calls[0].tool == "get_top_diseases"
    assert fourth.tool_calls[0].arguments["limit"] == 3

    fifth, _ = agent.query("哪些医院的住院病例最多？")
    sixth, _ = agent.query("那这些医院的费用呢？", fifth.session_id)
    assert sixth.tool_calls[0].tool == "get_hospital_analysis"
    assert sixth.tool_calls[0].arguments["metric"] == "average_cost"


def test_unsupported_question_is_not_forced_into_a_tool():
    with pytest.raises(UnsupportedQuery):
        make_agent().query("帮我修改数据库并执行 shell")


def test_grounding_guard_replaces_invented_numbers():
    class HallucinatingProvider(DeterministicTestProvider):
        def summarize(self, query, result):
            return "2024 年共有 999,999 条记录。"

    agent = MedicalAnalyticsAgent(
        provider=HallucinatingProvider(),
        registry=ToolRegistry(FakeAnalyticsRepository()),
        conversation_store=InMemoryConversationStore(),
    )
    data, _ = agent.query("总体住院情况如何？")
    assert "999,999" not in data.answer
    assert "2024" not in data.answer
    assert "4 条住院记录" in data.answer


def test_grounding_guard_rejects_swapped_charge_and_cost_labels():
    class MislabelingProvider(DeterministicTestProvider):
        def summarize(self, query, result):
            return "Disease 1 的平均总费用为 800.25。"

    agent = MedicalAnalyticsAgent(
        provider=MislabelingProvider(),
        registry=ToolRegistry(FakeAnalyticsRepository()),
        conversation_store=InMemoryConversationStore(),
    )
    data, meta = agent.query("哪些疾病平均费用最高？")
    assert "平均总费用 1,200.50" in data.answer
    assert "平均总成本 800.25" in data.answer
    assert meta["grounding_fallback"] is True
    assert meta["grounding_fallback_reason"] == "metric_label_mismatch"


def test_grounding_guard_rejects_currency_not_present_in_tool_result():
    class CurrencyProvider(DeterministicTestProvider):
        def summarize(self, query, result):
            return "Disease 1 的平均总费用为 1,200.50 美元。"

    agent = MedicalAnalyticsAgent(
        provider=CurrencyProvider(),
        registry=ToolRegistry(FakeAnalyticsRepository()),
        conversation_store=InMemoryConversationStore(),
    )
    data, meta = agent.query("哪些疾病平均费用最高？")
    assert "美元" not in data.answer
    assert meta["grounding_fallback_reason"] == "currency_not_in_tool_result"


def test_causal_question_keeps_observation_and_causality_boundary_separate():
    data, _ = make_agent().query("为什么 COVID-19 的费用高？")
    assert data.tool_calls[0].tool == "get_disease_cost_analysis"
    assert "数据观察" in data.answer
    assert "聚合统计数据无法证明该差异的原因" in data.answer


def test_individual_medical_advice_is_rejected_before_tool_routing():
    with pytest.raises(UnsupportedQuery):
        make_agent().query("请根据这些统计给我开药")
