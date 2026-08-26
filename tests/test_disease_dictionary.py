import re

from app.ai_layer.chart_gen import build_bar_option
from app.common import disease_dictionary
from app.service_layer.analysis import registry


def test_chinese_alias_resolves_to_ccsr_database_description():
    resolved = disease_dictionary.resolve("请分析心脏衰竭的平均费用")

    assert resolved["code"] == "CIR019"
    assert resolved["canonical"] == "HEART FAILURE"
    assert resolved["chinese"] == "心力衰竭"


def test_longest_alias_wins_for_specific_hypertension_category():
    resolved = disease_dictionary.resolve("继发性高血压住院量")

    assert resolved["code"] == "CIR008"


def test_registry_normalizes_chinese_disease_filter():
    assert registry.normalize_filter_value("disease", "心衰") == "HEART FAILURE"


def test_disease_chart_uses_chinese_label():
    option = build_bar_option({
        "dimension": "disease", "metrics": ["count"],
        "rows": [{"dimension_value": "HEART FAILURE", "count": 12}],
    })

    assert option["xAxis"]["data"] == ["心力衰竭"]


def test_display_dictionary_covers_all_database_categories_without_english_labels():
    names = disease_dictionary.display_names()
    assert len(names) == 491
    assert all(not re.search(r"[A-Za-z]", value) for value in names.values())
    assert disease_dictionary.chinese_label("LIVEBORN") == "活产儿"
    assert disease_dictionary.chinese_label("ABDOMINAL HERNIA") == "腹疝"
