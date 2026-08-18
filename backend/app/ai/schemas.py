from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AgeGroup = Literal["0 to 17", "18 to 29", "30 to 49", "50 to 69", "70 or Older"]
AdmissionType = Literal[
    "Elective",
    "Emergency",
    "Newborn",
    "Not Available",
    "Trauma",
    "Urgent",
]
ChartType = Literal["bar", "horizontal_bar", "pie", "line", "table"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AnalyticsFilters(StrictModel):
    year: int | None = Field(default=None, ge=1900, le=2100)
    age_group: AgeGroup | None = None
    hospital: str | None = Field(default=None, min_length=1, max_length=255)
    diagnosis: str | None = Field(default=None, min_length=1, max_length=255)
    admission_type: AdmissionType | None = None

    @field_validator("hospital", "diagnosis")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if any(ord(character) < 32 for character in value):
            raise ValueError("control characters are not allowed")
        return value

    def repository_filters(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class LimitedQuery(AnalyticsFilters):
    limit: int = Field(default=10, ge=1, le=50)


class OverviewQuery(AnalyticsFilters):
    pass


class DiseaseTopQuery(LimitedQuery):
    pass


class DiseaseCostQuery(LimitedQuery):
    pass


class HospitalAnalysisQuery(LimitedQuery):
    metric: Literal["record_count", "average_cost"] = "record_count"


class AgeAnalysisQuery(LimitedQuery):
    metric: Literal["distribution", "average_cost"] = "distribution"


class PaymentQuery(LimitedQuery):
    pass


class SeverityQuery(LimitedQuery):
    metric: Literal["record_count", "average_cost", "average_length_of_stay"] = "record_count"


class YearTrendQuery(LimitedQuery):
    limit: int = Field(default=20, ge=1, le=50)


class ToolCallAudit(StrictModel):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any]
    elapsed_ms: int = Field(ge=0)


class DataSource(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    dataset: str = Field(min_length=1, max_length=120)
    record_count: int = Field(ge=0)
    years: list[int] = Field(default_factory=list, max_length=50)
    storage: Literal["MySQL analytics service"] = "MySQL analytics service"


class ToolResult(StrictModel):
    tool: str
    label: str
    data: dict[str, Any] | list[dict[str, Any]]
    meta: dict[str, Any] = Field(default_factory=dict)
    source: DataSource
    elapsed_ms: int = Field(ge=0)


class ChartSeries(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    field: str = Field(min_length=1, max_length=80)


class ChartSpec(StrictModel):
    type: ChartType
    status: Literal["available", "unavailable"] = "available"
    title: str = Field(min_length=1, max_length=100)
    x_field: str | None = Field(default=None, max_length=80)
    y_field: str | None = Field(default=None, max_length=80)
    series: list[ChartSeries] = Field(default_factory=list, max_length=3)
    data: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    message: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def validate_available_chart(self) -> "ChartSpec":
        if self.status == "unavailable":
            if self.data:
                raise ValueError("unavailable charts must not contain data")
            return self
        if not self.data:
            raise ValueError("available charts require data")
        if self.type != "table" and not self.series:
            raise ValueError("chart series are required")
        requested_fields = {
            field
            for field in (
                self.x_field,
                self.y_field,
                *(series.field for series in self.series),
            )
            if field
        }
        if any(not requested_fields.issubset(row.keys()) for row in self.data):
            raise ValueError("chart fields must exist in every result row")
        return self


class ConversationTurn(StrictModel):
    query: str = Field(min_length=1, max_length=1000)
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any]
    result_summary: dict[str, Any] | list[dict[str, Any]]


class AIQueryRequest(StrictModel):
    query: str = Field(min_length=1, max_length=1000)
    session_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )

    @field_validator("query")
    @classmethod
    def reject_query_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 and character not in "\n\t" for character in value):
            raise ValueError("query contains unsupported control characters")
        return value


class ToolDecision(StrictModel):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AIQueryData(StrictModel):
    answer: str = Field(min_length=1, max_length=5000)
    tool_calls: list[ToolCallAudit] = Field(min_length=1, max_length=3)
    chart: ChartSpec
    sources: list[DataSource] = Field(min_length=1, max_length=3)
    session_id: str
    turn_count: int = Field(ge=1)
    provider: dict[str, str]
