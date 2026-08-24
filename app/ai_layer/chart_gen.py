"""ECharts 可视化配置生成：根据分析结果类型自动生成图表配置。

对应文档功能「大屏可视化」：
根据大数据分析结果的类型，自动生成 ECharts 图表，支撑前端动态渲染。
后端只产出 JSON 配置，真正渲染由前端 ECharts 完成。
"""
import logging

logger = logging.getLogger(__name__)

# 支持的图表类型
CHART_TYPES = ("bar", "pie", "line")

# 指标中文标签（用于图表标题/坐标轴）
METRIC_LABELS = {
    "count": "住院量",
    "avg_length_of_stay": "平均住院时长(天)",
    "avg_total_charges": "平均费用",
    "sum_total_charges": "总费用",
    "avg_total_costs": "平均成本",
    "sum_total_costs": "总成本",
}

DIMENSION_LABELS = {
    "disease": "疾病",
    "age_group": "年龄段",
    "hospital": "医院",
    "county": "县",
    "service_area": "服务区域",
    "year": "年份",
    "payment": "支付方式",
    "gender": "性别",
    "admission_type": "入院类型",
    "severity": "病情严重程度",
}


def _toolbox() -> dict:
    return {
        "show": True,
        "right": 8,
        "feature": {
            "dataView": {"show": True, "readOnly": True, "title": "数据视图"},
            "restore": {"show": True, "title": "还原"},
            "saveAsImage": {"show": True, "title": "导出图片", "name": "智慧医疗分析图"},
        },
    }


def _data_zoom(size: int) -> list[dict]:
    if size <= 10:
        return []
    end = max(10, round(10 / size * 100, 2))
    return [
        {"type": "inside", "start": 0, "end": end},
        {"type": "slider", "start": 0, "end": end, "height": 18, "bottom": 8},
    ]


def _pick_value_field(data: dict) -> str:
    """优先取第一个非 count 的数值指标，否则取 count。"""
    for m in data.get("metrics", []):
        if m != "count":
            return m
    return "count"


def _rows(data: dict):
    rows = data.get("rows", [])
    if not rows and "rows" in data.get("data", {}):
        rows = data["data"]["rows"]
    return rows


def build_bar_option(data: dict, value_field: str = None) -> dict:
    """柱状图配置。"""
    rows = _rows(data)
    value_field = value_field or _pick_value_field(data)
    categories = [str(r.get("dimension_value") or r.get("payment") or r.get("year")) for r in rows]
    values = [r.get(value_field) for r in rows]
    dim_label = DIMENSION_LABELS.get(data.get("dimension", ""), "维度")
    return {
        "title": {"text": f"{dim_label} - {METRIC_LABELS.get(value_field, value_field)}"},
        "aria": {"enabled": True},
        "toolbox": _toolbox(),
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 40, "right": 20, "bottom": 90 if len(rows) > 10 else 60, "top": 50},
        "dataZoom": _data_zoom(len(rows)),
        "xAxis": {
            "type": "category", "data": categories,
            "axisLabel": {"rotate": 30, "interval": 0},
        },
        "yAxis": {"type": "value"},
        "series": [{
            "name": METRIC_LABELS.get(value_field, value_field), "type": "bar", "data": values,
            "emphasis": {"focus": "series"}, "itemStyle": {"borderRadius": [4, 4, 0, 0]},
        }],
    }


def build_pie_option(data: dict, value_field: str = None) -> dict:
    """饼图配置（占比/构成）。"""
    rows = _rows(data)
    value_field = value_field or _pick_value_field(data)
    pie_data = [
        {"name": str(r.get("dimension_value") or r.get("payment")), "value": r.get(value_field)}
        for r in rows
    ]
    dim_label = DIMENSION_LABELS.get(data.get("dimension", ""), "维度")
    return {
        "title": {"text": f"{dim_label} - {METRIC_LABELS.get(value_field, value_field)} 占比"},
        "aria": {"enabled": True},
        "toolbox": _toolbox(),
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "series": [{
            "name": dim_label, "type": "pie", "radius": ["38%", "65%"], "data": pie_data,
            "emphasis": {"scale": True, "scaleSize": 8},
        }],
    }


def build_line_option(data: dict, value_field: str = None) -> dict:
    """折线图配置（趋势）。"""
    rows = _rows(data)
    value_field = value_field or _pick_value_field(data)
    categories = [str(r.get("dimension_value") or r.get("year")) for r in rows]
    values = [r.get(value_field) for r in rows]
    dim_label = DIMENSION_LABELS.get(data.get("dimension", ""), "维度")
    return {
        "title": {"text": f"{dim_label} - {METRIC_LABELS.get(value_field, value_field)} 趋势"},
        "aria": {"enabled": True},
        "toolbox": _toolbox(),
        "tooltip": {"trigger": "axis"},
        "dataZoom": _data_zoom(len(rows)),
        "xAxis": {"type": "category", "data": categories, "boundaryGap": False},
        "yAxis": {"type": "value"},
        "series": [{
            "name": METRIC_LABELS.get(value_field, value_field), "type": "line", "data": values,
            "smooth": True, "showSymbol": len(rows) <= 30, "emphasis": {"focus": "series"},
        }],
    }


def generate_chart_option(data: dict, chart_type: str = "bar", value_field: str = None) -> dict:
    """根据分析结果类型自动生成 ECharts 配置（JSON）。

    Args:
        data: 分析结果（含 rows 列表）。
        chart_type: bar / pie / line。
        value_field: 指定取值的字段，默认自动选择。
    """
    rows = _rows(data)
    if not rows:
        logger.info("分析结果无数据，跳过图表生成")
        return None
    selected_field = value_field or _pick_value_field(data)
    if not any(isinstance(row.get(selected_field), (int, float)) for row in rows):
        logger.warning("分析结果缺少可绘制数值字段 %s，跳过图表生成", selected_field)
        return None
    if chart_type == "pie":
        return build_pie_option(data, value_field)
    if chart_type == "line":
        return build_line_option(data, value_field)
    return build_bar_option(data, value_field)
