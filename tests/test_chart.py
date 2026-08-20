from app.ai_layer.chart_gen import generate_chart_option


DATA = {
    "dimension": "age_group",
    "metrics": ["count"],
    "rows": [
        {"dimension_value": "18 to 29", "count": 12},
        {"dimension_value": "30 to 49", "count": 20},
    ],
}


def test_bar_chart_uses_rows():
    option = generate_chart_option(DATA, "bar")
    assert option["xAxis"]["data"] == ["18 to 29", "30 to 49"]
    assert option["series"][0]["data"] == [12, 20]


def test_pie_chart_shape():
    option = generate_chart_option(DATA, "pie")
    assert option["series"][0]["type"] == "pie"
    assert option["series"][0]["data"][1] == {"name": "30 to 49", "value": 20}

