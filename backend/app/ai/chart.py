from __future__ import annotations

from typing import Any

from .schemas import ChartSeries, ChartSpec, ToolResult


class ChartPlanner:
    """Deterministic allow-list mapping from tool output to safe chart specifications."""

    def plan(self, result: ToolResult) -> ChartSpec:
        rows = result.data if isinstance(result.data, list) else [result.data]
        if not rows:
            return self._unavailable("暂无可视化数据", "当前筛选条件没有返回结果。")
        if result.tool == "get_year_trend" and not result.meta.get("trend_available"):
            return self._unavailable(
                "年度趋势",
                result.meta.get("message") or "可用年份不足，无法形成跨年度趋势。",
            )

        builders = {
            "get_overview": self._overview,
            "get_top_diseases": self._top_diseases,
            "get_disease_cost_analysis": self._disease_cost,
            "get_hospital_analysis": self._hospital,
            "get_age_analysis": self._age,
            "get_payment_distribution": self._payment,
            "get_severity_analysis": self._severity,
            "get_year_trend": self._trend,
        }
        return builders[result.tool](rows[:50], result)

    @staticmethod
    def _unavailable(title: str, message: str) -> ChartSpec:
        return ChartSpec(
            type="table",
            status="unavailable",
            title=title,
            data=[],
            message=message,
        )

    @staticmethod
    def _overview(rows: list[dict[str, Any]], _result: ToolResult) -> ChartSpec:
        return ChartSpec(type="table", title="总体住院指标", data=rows)

    @staticmethod
    def _top_diseases(rows: list[dict[str, Any]], _result: ToolResult) -> ChartSpec:
        return ChartSpec(
            type="horizontal_bar",
            title="疾病住院记录数排名",
            x_field="diagnosis",
            series=[ChartSeries(name="住院记录数", field="record_count")],
            data=rows,
        )

    @staticmethod
    def _disease_cost(rows: list[dict[str, Any]], _result: ToolResult) -> ChartSpec:
        return ChartSpec(
            type="horizontal_bar",
            title="疾病平均费用与成本",
            x_field="diagnosis",
            series=[
                ChartSeries(name="平均总费用", field="avg_total_charges"),
                ChartSeries(name="平均总成本", field="avg_total_costs"),
            ],
            data=rows,
        )

    @staticmethod
    def _hospital(rows: list[dict[str, Any]], result: ToolResult) -> ChartSpec:
        is_cost = result.meta.get("metric") == "average_cost"
        series = (
            [
                ChartSeries(name="平均总费用", field="avg_total_charges"),
                ChartSeries(name="平均总成本", field="avg_total_costs"),
            ]
            if is_cost
            else [ChartSeries(name="住院记录数", field="record_count")]
        )
        return ChartSpec(
            type="horizontal_bar",
            title="医院平均费用排名" if is_cost else "医院住院记录数排名",
            x_field="hospital",
            series=series,
            data=rows,
        )

    @staticmethod
    def _age(rows: list[dict[str, Any]], result: ToolResult) -> ChartSpec:
        is_cost = result.meta.get("metric") == "average_cost"
        return ChartSpec(
            type="bar",
            title="不同年龄组平均费用" if is_cost else "不同年龄组住院记录数",
            x_field="age_group",
            series=[
                ChartSeries(
                    name="平均总费用" if is_cost else "住院记录数",
                    field="avg_total_charges" if is_cost else "record_count",
                )
            ],
            data=rows,
        )

    @staticmethod
    def _payment(rows: list[dict[str, Any]], _result: ToolResult) -> ChartSpec:
        return ChartSpec(
            type="pie",
            title="支付方式分布",
            x_field="payment_type",
            series=[ChartSeries(name="住院记录数", field="record_count")],
            data=rows,
        )

    @staticmethod
    def _severity(rows: list[dict[str, Any]], result: ToolResult) -> ChartSpec:
        metric = result.meta.get("metric", "record_count")
        field, name = {
            "record_count": ("record_count", "住院记录数"),
            "average_cost": ("avg_total_charges", "平均总费用"),
            "average_length_of_stay": ("avg_length_of_stay", "平均住院日"),
        }[metric]
        return ChartSpec(
            type="bar",
            title="病情严重程度分析",
            x_field="severity",
            series=[ChartSeries(name=name, field=field)],
            data=rows,
        )

    @staticmethod
    def _trend(rows: list[dict[str, Any]], _result: ToolResult) -> ChartSpec:
        return ChartSpec(
            type="line",
            title="年度住院与费用趋势",
            x_field="year",
            series=[
                ChartSeries(name="住院记录数", field="record_count"),
                ChartSeries(name="平均总费用", field="avg_total_charges"),
            ],
            data=rows,
        )
