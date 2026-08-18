from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import monotonic, perf_counter
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from ..services.cost_service import CostService
from ..services.disease_service import DiseaseService
from ..services.hospital_service import HospitalService
from ..services.overview_service import OverviewService
from ..utils.responses import to_json_value
from .errors import ToolValidationFailure, UnsupportedQuery
from .schemas import (
    AgeAnalysisQuery,
    DataSource,
    DiseaseCostQuery,
    DiseaseTopQuery,
    HospitalAnalysisQuery,
    OverviewQuery,
    PaymentQuery,
    SeverityQuery,
    ToolResult,
    YearTrendQuery,
)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    label: str
    description: str
    schema: type[BaseModel]
    handler: Callable[[BaseModel], Any]


class ToolRegistry:
    """Allow-listed analytics tools backed exclusively by the existing service layer."""

    FILTER_FIELDS = ("year", "age_group", "hospital", "diagnosis", "admission_type")

    def __init__(self, repository, source_cache_seconds: int = 300):
        self.repository = repository
        self.overview_service = OverviewService(repository)
        self.disease_service = DiseaseService(repository)
        self.cost_service = CostService(repository)
        self.hospital_service = HospitalService(repository)
        self.source_cache_seconds = source_cache_seconds
        self._source_cache: tuple[float, DataSource] | None = None
        self._source_lock = RLock()
        self._definitions = {
            definition.name: definition
            for definition in (
                ToolDefinition(
                    "get_overview",
                    "总体住院情况",
                    "获取住院记录数、医疗机构数、平均住院日、费用、成本和急诊占比。",
                    OverviewQuery,
                    self._overview,
                ),
                ToolDefinition(
                    "get_top_diseases",
                    "疾病病例排名",
                    "按住院记录数返回疾病 Top N；limit 必须为 1 到 50。",
                    DiseaseTopQuery,
                    self._top_diseases,
                ),
                ToolDefinition(
                    "get_disease_cost_analysis",
                    "疾病费用分析",
                    "比较疾病的平均总费用和平均总成本。",
                    DiseaseCostQuery,
                    self._disease_cost,
                ),
                ToolDefinition(
                    "get_hospital_analysis",
                    "医院分析",
                    "按病例数或平均费用分析医院。",
                    HospitalAnalysisQuery,
                    self._hospital,
                ),
                ToolDefinition(
                    "get_age_analysis",
                    "年龄组分析",
                    "分析不同年龄组的病例量、平均住院日或平均费用。",
                    AgeAnalysisQuery,
                    self._age,
                ),
                ToolDefinition(
                    "get_payment_distribution",
                    "支付方式分析",
                    "统计第一支付方式的病例数和占比。",
                    PaymentQuery,
                    self._payment,
                ),
                ToolDefinition(
                    "get_severity_analysis",
                    "病情严重程度分析",
                    "比较严重程度的病例量、平均费用和平均住院日。",
                    SeverityQuery,
                    self._severity,
                ),
                ToolDefinition(
                    "get_year_trend",
                    "年度趋势",
                    "检查可用年份并返回年度住院量和费用；单一年份时明确不可形成跨年趋势。",
                    YearTrendQuery,
                    self._year_trend,
                ),
            )
        }

    @property
    def definitions(self) -> list[ToolDefinition]:
        return list(self._definitions.values())

    def definition(self, name: str) -> ToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise UnsupportedQuery(f"unsupported analytics tool: {name}") from exc

    def langchain_tools(self):
        from langchain_core.tools import StructuredTool

        tools = []
        for definition in self.definitions:
            def invoke(_name=definition.name, **kwargs):
                return self.execute(_name, kwargs).model_dump(mode="json")

            tools.append(
                StructuredTool.from_function(
                    func=invoke,
                    name=definition.name,
                    description=definition.description,
                    args_schema=definition.schema,
                )
            )
        return tools

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        definition = self.definition(name)
        try:
            query = definition.schema.model_validate(arguments or {})
        except ValidationError as exc:
            raise ToolValidationFailure(str(exc)) from exc

        started = perf_counter()
        raw_data, extra_meta = definition.handler(query)
        elapsed_ms = max(0, round((perf_counter() - started) * 1000))
        cache_telemetry = getattr(self.repository, "cache_telemetry", lambda: {})()
        data = to_json_value(raw_data)
        meta = {
            "filters": self._filters(query),
            "count": len(data) if isinstance(data, list) else 1,
            **extra_meta,
            **cache_telemetry,
        }
        return ToolResult(
            tool=name,
            label=definition.label,
            data=data,
            meta=to_json_value(meta),
            source=self._data_source(),
            elapsed_ms=elapsed_ms,
        )

    def _filters(self, query: BaseModel) -> dict[str, Any]:
        values = query.model_dump(exclude_none=True)
        return {key: values[key] for key in self.FILTER_FIELDS if key in values}

    def _data_source(self) -> DataSource:
        now = monotonic()
        with self._source_lock:
            if self._source_cache and now - self._source_cache[0] < self.source_cache_seconds:
                return self._source_cache[1]
            overview = to_json_value(self.repository.overview({}))
            years_data = to_json_value(self.repository.yearly_trends({}, 50))
            years = sorted(
                {int(row["year"]) for row in years_data if row.get("year") is not None}
            )
            year_label = "/".join(str(year) for year in years) or "未知年份"
            source = DataSource(
                name=f"医疗住院数据 {year_label}",
                dataset="medical_platform.hospital_discharges",
                record_count=int(overview.get("total_records") or 0),
                years=years,
            )
            self._source_cache = (now, source)
            return source

    def _overview(self, query: OverviewQuery):
        return self.overview_service.get(self._filters(query)), {}

    def _top_diseases(self, query: DiseaseTopQuery):
        return self.disease_service.top(self._filters(query), query.limit), {"limit": query.limit}

    def _disease_cost(self, query: DiseaseCostQuery):
        return self.cost_service.diseases(self._filters(query), query.limit), {"limit": query.limit}

    def _hospital(self, query: HospitalAnalysisQuery):
        if query.metric == "average_cost":
            data = self.cost_service.hospitals(self._filters(query), query.limit)
        else:
            data = self.hospital_service.top(self._filters(query), query.limit)
        return data, {"limit": query.limit, "metric": query.metric}

    def _age(self, query: AgeAnalysisQuery):
        if query.metric == "average_cost":
            data = self.repository.age_cost(self._filters(query), query.limit)
        else:
            data = self.repository.age_distribution(self._filters(query), query.limit)
        return data, {"limit": query.limit, "metric": query.metric}

    def _payment(self, query: PaymentQuery):
        return self.repository.payment_distribution(self._filters(query), query.limit), {"limit": query.limit}

    def _severity(self, query: SeverityQuery):
        return self.repository.severity_distribution(self._filters(query), query.limit), {
            "limit": query.limit,
            "metric": query.metric,
        }

    def _year_trend(self, query: YearTrendQuery):
        data = self.repository.yearly_trends(self._filters(query), query.limit)
        available_years = sorted(
            {int(row["year"]) for row in data if row.get("year") is not None}
        )
        unavailable_message = (
            f"当前筛选结果仅包含 {available_years[0]} 年，无法形成跨年度趋势。"
            if len(available_years) == 1
            else "当前筛选结果没有可用年份，无法形成跨年度趋势。"
        )
        return data, {
            "limit": query.limit,
            "available_years": available_years,
            "trend_available": len(available_years) > 1,
            "message": None if len(available_years) > 1 else unavailable_message,
        }
