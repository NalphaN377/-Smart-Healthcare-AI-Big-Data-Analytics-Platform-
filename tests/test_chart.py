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
    assert option["toolbox"]["feature"]["saveAsImage"]["show"] is True
    assert option["aria"]["enabled"] is True


def test_pie_chart_shape():
    option = generate_chart_option(DATA, "pie")
    assert option["series"][0]["type"] == "pie"
    assert option["series"][0]["data"][1] == {"name": "30 to 49", "value": 20}


def test_empty_or_non_numeric_data_does_not_generate_chart():
    assert generate_chart_option({"dimension": "year", "metrics": ["count"], "rows": []}) is None
    assert generate_chart_option({"dimension": "year", "metrics": ["count"], "rows": [{"dimension_value": 2021}]}) is None


def test_long_time_series_has_inside_and_slider_zoom():
    data = {
        "dimension": "year", "metrics": ["count"],
        "rows": [{"dimension_value": year, "count": year} for year in range(2000, 2021)],
    }
    option = generate_chart_option(data, "line")
    assert [item["type"] for item in option["dataZoom"]] == ["inside", "slider"]
    assert option["series"][0]["smooth"] is True


def test_two_dimension_year_trend_creates_separate_series():
    data = {
        "dimension": "disease", "dimensions": ["year", "disease"],
        "metrics": ["count"],
        "rows": [
            {"year": 2021, "disease": "A", "count": 10},
            {"year": 2022, "disease": "A", "count": 12},
            {"year": 2021, "disease": "B", "count": 8},
            {"year": 2022, "disease": "B", "count": 9},
        ],
    }
    option = generate_chart_option(data, "line")
    assert option["xAxis"]["data"] == [2021, 2022]
    assert [series["name"] for series in option["series"]] == ["A", "B"]
    assert option["series"][0]["data"] == [10, 12]
