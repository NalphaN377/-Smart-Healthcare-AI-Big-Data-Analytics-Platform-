from app.ai_layer.agent import MedicalAgent
from app.ai_layer.knowledge import compact_context, retrieve
from app.ai_layer.text_gen import template_summary


def test_static_knowledge_retrieves_metric_definition_without_database():
    results = retrieve("费用和成本有什么区别", "doctor")
    assert results
    assert results[0]["id"] == "metric_charges_costs"
    assert "Total Charges" in results[0]["content"]


def test_agent_routes_definition_question_to_knowledge_mode():
    context = MedicalAgent(use_llm_intent=False).prepare("CCSR诊断编码是什么意思", "doctor")
    assert context["answer_mode"] == "knowledge"
    assert context["chart"] is None
    assert "CCSR诊断与手术编码" in context["knowledge_sources"]


def test_personal_medical_question_never_bypasses_safety_with_rag():
    context = MedicalAgent(use_llm_intent=False).prepare("我得了高血压应该吃什么药？", "patient")
    assert context["answer_mode"] == "direct"
    assert context["knowledge"] == []
    assert "专业医务人员" in context["direct_answer"]


def test_compact_context_is_bounded_to_three_documents():
    documents = [
        {"title": f"知识{i}", "content": "内容"}
        for i in range(5)
    ]
    text = compact_context(documents)
    assert "知识0" in text and "知识2" in text
    assert "知识3" not in text


def test_compact_context_truncates_each_document():
    text = compact_context([{"title": "长文档", "content": "x" * 900}])
    assert text.count("x") == 700


def test_named_disease_summary_answers_the_selected_disease_directly():
    summary = template_summary({
        "dimension": "disease", "dimension_label": "疾病",
        "metrics": ["avg_length_of_stay"], "filters": {"disease": "Septicemia"},
        "rows": [{"dimension_value": "SEPTICEMIA", "avg_length_of_stay": 9.2898}],
    })
    assert "SEPTICEMIA" in summary
    assert "9.3 天" in summary
    assert "排序首位" not in summary
    assert "不代表个人" in summary
