"""AI 智能层意图识别单元测试。

运行：pytest tests/test_intent.py
"""
from app.ai_layer.intent import _validated_llm_intent, detect_intent, detect_intent_with_llm


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


def test_year_range_is_not_reduced_to_first_year():
    intent = detect_intent("2021到2024年出院人数趋势")
    assert intent["status"] == "ready"
    assert intent["dimension"] == "year"
    assert intent["metrics"] == ["count"]
    assert intent["filters"] == {"year_from": 2021, "year_to": 2024}


def test_reversed_year_range_is_normalized():
    intent = detect_intent("2024至2022年住院量变化")
    assert intent["filters"] == {"year_from": 2022, "year_to": 2024}


def test_named_disease_is_used_as_filter_instead_of_global_ranking():
    intent = detect_intent("Septicemia类疾病，需要住多久医院？")
    assert intent["status"] == "ready"
    assert intent["dimension"] == "disease"
    assert intent["metrics"] == ["avg_length_of_stay"]
    assert intent["filters"] == {"disease": "Septicemia"}


def test_chinese_disease_alias_is_used_as_database_filter():
    intent = detect_intent("心脏衰竭的平均费用是多少？")

    assert intent["status"] == "ready"
    assert intent["dimension"] == "disease"
    assert intent["metrics"][0] == "avg_total_charges"
    assert intent["filters"] == {"disease": "Heart failure"}


def test_chinese_disease_short_name_works_without_external_llm():
    intent = detect_intent("心衰住院量")

    assert intent["status"] == "ready"
    assert intent["metrics"] == ["count"]
    assert intent["filters"] == {"disease": "Heart failure"}


def test_named_chinese_disease_trend_uses_year_dimension_and_filter():
    intent = detect_intent("心衰历年趋势")

    assert intent["status"] == "ready"
    assert intent["dimension"] == "year"
    assert intent["metrics"] == ["count"]
    assert intent["filters"] == {"disease": "Heart failure"}


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


def test_llm_year_range_is_whitelist_validated():
    intent = _validated_llm_intent("2021到2024年出院人数趋势", {
        "status": "ready", "dimension": "year", "metrics": ["count"], "chart_type": "line",
        "filters": {"year": 2021, "year_from": "2021", "year_to": "2024"},
        "confidence": 0.99,
    })
    assert intent["filters"] == {"year_from": 2021, "year_to": 2024}


def test_explicit_query_range_overrides_llm_single_year_mistake():
    intent = _validated_llm_intent("2021到2024年出院人数趋势", {
        "status": "ready", "dimension": "year", "metrics": ["count"], "chart_type": "line",
        "filters": {"year": 2021}, "confidence": 0.99,
    })
    assert intent["filters"] == {"year_from": 2021, "year_to": 2024}


def test_explicit_disease_overrides_missing_llm_filter():
    intent = _validated_llm_intent("Septicemia类疾病，需要住多久医院？", {
        "status": "ready", "dimension": "disease", "metrics": ["avg_length_of_stay"],
        "chart_type": "bar", "filters": {}, "confidence": 0.99,
    })
    assert intent["filters"] == {"disease": "Septicemia"}


def test_chinese_disease_dictionary_overrides_llm_chinese_filter():
    intent = _validated_llm_intent("心脏衰竭平均费用", {
        "status": "ready", "dimension": "disease", "metrics": ["avg_total_charges"],
        "chart_type": "bar", "filters": {"disease": "心脏衰竭"}, "confidence": 0.99,
    })

    assert intent["filters"] == {"disease": "Heart failure"}


def test_financial_proxy_metric_is_recognized_but_not_called_real_profit():
    intent = detect_intent("按年度分析利润率")
    assert intent["status"] == "ready"
    assert intent["dimension"] == "year"
    assert "charge_cost_spread_ratio" in intent["metrics"]


def test_four_year_charge_cost_spread_ratio_is_executable_and_focused():
    intent = detect_intent("四年收费成本差额率有什么变化？")
    assert intent["status"] == "ready"
    assert intent["dimension"] == "year"
    assert intent["metrics"] == ["charge_cost_spread_ratio", "count"]
    assert intent["chart_type"] == "line"
    assert intent["sort_by"] is None


def test_specialized_analysis_topics_are_recognized():
    assert detect_intent("做病例组合校正后的医院成本比较")["topic"] == "hospital_benchmark"
    assert detect_intent("检查四年数据质量和异常")["topic"] == "data_quality"
    assert detect_intent("分析新生儿出生体重")["topic"] == "maternal_newborn"


def test_growth_question_routes_to_cross_year_growth_analysis():
    intent = detect_intent("哪些疾病带来的总成本增长最快？")
    assert intent["status"] == "ready"
    assert intent["topic"] == "growth_ranking"
    assert intent["dimension"] == "disease"
    assert intent["metrics"] == ["sum_total_costs"]
    assert intent["sort_by"] == "growth_pct"


def test_clear_rule_intent_is_not_downgraded_by_external_llm(monkeypatch):
    from app.ai_layer import intent as intent_module

    monkeypatch.setitem(intent_module.LLM_CONFIG, "api_key", "should-not-be-used")
    result = detect_intent_with_llm("不同医院的急诊率如何？")
    assert result["status"] == "ready"
    assert result["dimension"] == "hospital"
    assert result["metrics"] == ["ed_rate", "count"]
    assert result["sort_by"] == "ed_rate"
    assert result["source"] == "rules"
