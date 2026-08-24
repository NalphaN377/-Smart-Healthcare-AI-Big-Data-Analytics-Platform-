"""AI 智能层意图识别单元测试。

运行：pytest tests/test_intent.py
"""
from app.ai_layer.intent import _validated_llm_intent, detect_intent


def test_detect_intent_age_group():
    intent = detect_intent("不同年龄段的平均住院时长是多少？")
    assert intent["status"] == "ready"
    assert intent["dimension"] == "age_group"
    assert "avg_length_of_stay" in intent["metrics"]


def test_detect_intent_payment_pie():
    intent = detect_intent("不同支付方式占比")
    assert intent["dimension"] == "payment"
    assert intent["chart_type"] == "pie"


def test_detect_intent_year_trend():
    intent = detect_intent("各年份住院量的变化趋势")
    assert intent["dimension"] == "year"
    assert intent["chart_type"] == "line"


def test_natural_language_synonyms_are_understood():
    intent = detect_intent("把各医疗机构按次均费用从高到低排一下")
    assert intent["status"] == "ready"
    assert intent["dimension"] == "hospital"
    assert intent["metrics"] == ["avg_total_charges"]
    assert intent["sort_by"] == "avg_total_charges"
    assert intent["sort_order"] == "desc"


def test_natural_disease_ranking_is_understood():
    intent = detect_intent("哪些病的患者住得最久？")
    assert intent["status"] == "ready"
    assert intent["dimension"] == "disease"
    assert "avg_length_of_stay" in intent["metrics"]


def test_chinese_top_number_and_colloquial_metric_are_understood():
    intent = detect_intent("想看看哪些病种通常住院更久，列出前五名")
    assert intent["metrics"] == ["avg_length_of_stay"]
    assert intent["limit"] == 5
    assert intent["sort_by"] == "avg_length_of_stay"


def test_missing_dimension_requests_clarification_without_chart():
    intent = detect_intent("平均住院费用是多少？")
    assert intent["status"] == "clarification"
    assert intent["chart_requested"] is False
    assert intent["dimension"] is None


def test_out_of_scope_question_is_not_mapped_to_default_dimension():
    intent = detect_intent("北京明天天气怎么样？")
    assert intent["status"] == "unsupported"
    assert intent["dimension"] is None
    assert intent["metrics"] == []
    assert intent["chart_requested"] is False


def test_personal_medical_advice_is_rejected_without_chart():
    intent = detect_intent("我得了高血压应该吃什么药？")
    assert intent["status"] == "unsupported"
    assert intent["chart_requested"] is False
    assert "专业医务人员" in intent["message"]


def test_llm_result_is_whitelist_validated():
    intent = _validated_llm_intent("按疾病看费用", {
        "status": "ready", "dimension": "unsafe_column",
        "metrics": ["avg_total_charges", "drop_table"], "chart_type": "map",
        "filters": {"year": "2021", "unsafe": "x"}, "sort_by": "drop_table",
        "confidence": 0.99,
    })
    assert intent["status"] == "clarification"
    assert intent["dimension"] is None
    assert intent["metrics"] == ["avg_total_charges"]
    assert intent["filters"] == {"year": 2021}
    assert intent["chart_requested"] is False
