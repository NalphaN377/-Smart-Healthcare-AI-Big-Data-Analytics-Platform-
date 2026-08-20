"""AI 智能层意图识别单元测试。

运行：pytest tests/test_intent.py
"""
from app.ai_layer.intent import detect_intent


def test_detect_intent_age_group():
    intent = detect_intent("不同年龄段的平均住院时长是多少？")
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
