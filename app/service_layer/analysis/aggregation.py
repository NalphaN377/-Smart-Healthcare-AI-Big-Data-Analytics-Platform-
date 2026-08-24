"""SQL Server 多维聚合分析。

所有动态列名均来自白名单；用户输入只能作为参数值进入 SQL。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional

import numpy as np

from app.data_layer import storage
from app.service_layer.analysis import registry

TABLE_NAME = storage.TABLE_NAME

DIMENSIONS = {key: spec.expression for key, spec in registry.DIMENSIONS.items()}
DIMENSION_LABELS = {key: spec.label for key, spec in registry.DIMENSIONS.items()}
METRICS = {key: spec.expression for key, spec in registry.METRICS.items()}
FILTERS = registry.FILTERS

STAT_METRICS = {
    "count": "record_count",
    "avg_length_of_stay": "length_of_stay_sum*1.0/NULLIF(length_of_stay_count,0)",
    "avg_total_charges": "total_charges_sum*1.0/NULLIF(total_charges_count,0)",
    "sum_total_charges": "total_charges_sum",
    "avg_total_costs": "total_costs_sum*1.0/NULLIF(total_costs_count,0)",
    "sum_total_costs": "total_costs_sum",
    "charge_cost_spread": "total_charges_sum-total_costs_sum",
    "charge_cost_spread_ratio": "(total_charges_sum-total_costs_sum)*100.0/NULLIF(total_charges_sum,0)",
    "cost_to_charge_ratio": "total_costs_sum*100.0/NULLIF(total_charges_sum,0)",
    "charge_to_cost_multiple": "total_charges_sum*1.0/NULLIF(total_costs_sum,0)",
    "charges_per_day": "total_charges_sum*1.0/NULLIF(length_of_stay_sum,0)",
    "costs_per_day": "total_costs_sum*1.0/NULLIF(length_of_stay_sum,0)",
}


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _run_query(sql: str, params: Iterable = ()) -> list[dict]:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        columns = [column[0] for column in cursor.description]
        return [{key: _json_value(value) for key, value in zip(columns, row)} for row in cursor.fetchall()]
    finally:
        conn.close()


def _filter_clause(filters: dict | None, role: str = "doctor") -> tuple[str, list]:
    clauses, params = [], []
    operators = {"year_from": ">=", "year_to": "<="}
    for key, value in (filters or {}).items():
        if value in (None, ""):
            continue
        if key not in FILTERS:
            raise ValueError(f"不支持的筛选项: {key}，可选 {list(FILTERS)}")
        expression, caster = FILTERS[key]
        if key not in {"year", "year_from", "year_to"}:
            registry.require_dimension(key, role)
        try:
            params.append(caster(registry.normalize_filter_value(key, value)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"筛选项 {key} 的值不合法") from exc
        clauses.append(f"({expression}) {operators.get(key, '=')} {storage.PARAM}")
    return (" WHERE " + " AND ".join(clauses), params) if clauses else ("", params)


def _stats_current() -> bool:
    rows = _run_query(
        "SELECT CASE WHEN analytics.int_value=data_version.int_value AND schema_version.int_value>=2 THEN 1 ELSE 0 END AS is_current "
        "FROM dbo.system_state analytics CROSS JOIN dbo.system_state data_version CROSS JOIN dbo.system_state schema_version "
        "WHERE analytics.state_key=N'analytics_data_version' AND data_version.state_key=N'data_version' "
        "AND schema_version.state_key=N'analytics_schema_version'"
    )
    return bool(rows and rows[0]["is_current"])


def _aggregate_from_stats(
    dimension: str, metrics: list[str], limit: int, filters: dict | None,
    sort_by: str | None, sort_order: str, role: str,
) -> dict | None:
    from app.service_layer.analysis.dashboard_stats import STAT_DIMENSIONS, scope_for

    scope = scope_for(filters)
    if scope is None or dimension not in STAT_DIMENSIONS or not set(metrics) <= set(STAT_METRICS) or not _stats_current():
        return None
    registry.require_dimension(dimension, role)
    for metric in metrics:
        registry.require_metric(metric, role)
    minimum = max(11 if role == "patient" else 1, registry.DIMENSIONS[dimension].min_count)
    select_metrics = [f"{STAT_METRICS[name]} AS [{name}]" for name in metrics]
    order_metric = sort_by or ("count" if "count" in metrics else metrics[0])
    order = "dimension_value ASC" if dimension == "year" and sort_by is None else f"[{order_metric}] {sort_order.upper()}"
    rows = _run_query(
        f"SELECT TOP {int(limit)} dimension_value,{','.join(select_metrics)} "
        "FROM dbo.analytics_dimension_stat "
        f"WHERE scope_service_area={storage.PARAM} AND dimension_name={storage.PARAM} "
        f"AND record_count>={int(minimum)} ORDER BY {order}",
        (scope, dimension),
    )
    if dimension == "year":
        for row in rows:
            if str(row.get("dimension_value") or "").isdigit():
                row["dimension_value"] = int(row["dimension_value"])
    return {
        "dimension": dimension, "dimensions": [dimension], "dimension_label": DIMENSION_LABELS[dimension], "metrics": metrics,
        "filters": filters or {}, "sort_by": sort_by, "sort_order": sort_order if sort_by else None,
        "rows": rows, "engine": "sqlserver_preaggregated", "suppression_threshold": minimum,
        "metric_meta": _metric_meta(metrics),
    }


def _metric_meta(metrics: list[str]) -> list[dict]:
    return [
        {"key": key, "label": registry.METRICS[key].label, "unit": registry.METRICS[key].unit,
         "description": registry.METRICS[key].description, "disclaimer": registry.METRICS[key].disclaimer}
        for key in metrics
    ]


def aggregate(
    dimension: str | list[str],
    metrics: Optional[list[str]] = None,
    limit: int = 20,
    filters: dict | None = None,
    sort_by: str | None = None,
    sort_order: str = "desc",
    role: str = "doctor",
) -> dict:
    dimensions = [dimension] if isinstance(dimension, str) else list(dimension or [])
    if not 1 <= len(dimensions) <= 2 or len(set(dimensions)) != len(dimensions):
        raise ValueError("分析维度必须为1到2个且不能重复")
    dimension_specs = [registry.require_dimension(key, role) for key in dimensions]
    metrics = metrics or ["count", "avg_length_of_stay"]
    metric_specs = [registry.require_metric(key, role) for key in metrics]
    if sort_by is not None and sort_by not in metrics:
        raise ValueError("排序指标必须包含在本次查询指标中")
    sort_order = str(sort_order).lower()
    if sort_order not in {"asc", "desc"}:
        raise ValueError("sort_order 仅支持 asc 或 desc")
    limit = max(1, min(int(limit), 100))
    preaggregated = _aggregate_from_stats(dimensions[0], metrics, limit, filters, sort_by, sort_order, role) if len(dimensions) == 1 else None
    if preaggregated is not None:
        return preaggregated
    where_sql, params = _filter_clause(filters, role)
    dimension_select = [f"({spec.expression}) AS [{spec.key}]" for spec in dimension_specs]
    select = dimension_select + [f"{spec.expression} AS [{spec.key}]" for spec in metric_specs]
    if len(dimensions) == 1:
        select.insert(1, f"({dimension_specs[0].expression}) AS dimension_value")
    if sort_by:
        order = f"[{sort_by}] {sort_order.upper()}"
    elif dimensions == ["year"]:
        order = "[year] ASC"
    elif "count" in metrics:
        order = "[count] DESC"
    else:
        order = f"[{metrics[0]}] DESC"
    minimum = max([11 if role == "patient" else 1, *(spec.min_count for spec in dimension_specs)])
    group_by = ",".join(f"({spec.expression})" for spec in dimension_specs)
    sql = (f"SELECT TOP {limit} {', '.join(select)} FROM {TABLE_NAME}{where_sql} "
           f"GROUP BY {group_by} HAVING COUNT_BIG(*)>={int(minimum)} ORDER BY {order}")
    rows = _run_query(sql, params)
    if len(dimensions) == 2:
        for row in rows:
            row["dimension_value"] = " | ".join(str(row.get(key) or "(未标注)") for key in dimensions)
    return {
        "dimension": dimensions[0],
        "dimensions": dimensions,
        "dimension_label": " × ".join(spec.label for spec in dimension_specs),
        "metrics": metrics,
        "filters": filters or {},
        "sort_by": sort_by,
        "sort_order": sort_order if sort_by else None,
        "rows": rows,
        "engine": "sqlserver_live",
        "suppression_threshold": minimum,
        "metric_meta": _metric_meta(metrics),
    }


def avg_length_of_stay_by(dimension: str = "age_group", limit: int = 20, filters: dict | None = None, role: str = "doctor") -> dict:
    return aggregate(dimension, ["count", "avg_length_of_stay", "avg_total_charges"], limit, filters, role=role)


def cost_distribution(dimension: str = "disease", limit: int = 20, filters: dict | None = None, role: str = "doctor") -> dict:
    return aggregate(dimension, ["count", "sum_total_charges", "avg_total_charges", "avg_total_costs"], limit, filters, role=role)


def payment_ratio(limit: int = 20, filters: dict | None = None, role: str = "doctor") -> dict:
    limit = max(1, min(int(limit), 100))
    preaggregated = _aggregate_from_stats("payment", ["count"], limit, filters, "count", "desc", role)
    if preaggregated is not None:
        rows = [{"payment": row["dimension_value"], "count": row["count"]} for row in preaggregated["rows"]]
        from app.service_layer.analysis.dashboard_stats import scope_for
        total_rows = _run_query(
            "SELECT COALESCE(SUM(record_count),0) AS total FROM dbo.analytics_dimension_stat "
            f"WHERE scope_service_area={storage.PARAM} AND dimension_name=N'payment'",
            (scope_for(filters),),
        )
        total = int(total_rows[0]["total"] or 0) if total_rows else 0
        for row in rows:
            row["ratio"] = round(row["count"] / total, 6) if total else 0
        return {
            "dimension": "payment", "dimension_label": "支付方式", "metrics": ["count", "ratio"],
            "rows": rows, "total": total, "engine": "sqlserver_preaggregated",
        }
    where_sql, params = _filter_clause(filters, role)
    dim = DIMENSIONS["payment"]
    total_row = _run_query(f"SELECT COUNT_BIG(*) AS total FROM {TABLE_NAME}{where_sql}", params)
    total = int(total_row[0]["total"]) if total_row else 0
    rows = _run_query(
        f"SELECT TOP {limit} ({dim}) AS payment, COUNT_BIG(*) AS count FROM {TABLE_NAME}{where_sql} "
        f"GROUP BY ({dim}) ORDER BY COUNT_BIG(*) DESC",
        params,
    )
    for row in rows:
        row["ratio"] = round(row["count"] / total, 6) if total else 0
    return {"dimension": "payment", "dimension_label": "支付方式", "metrics": ["count", "ratio"], "rows": rows, "total": total}


def year_trend(filters: dict | None = None, role: str = "doctor") -> dict:
    data = aggregate("year", ["count", "avg_total_charges", "avg_length_of_stay"], limit=50, filters=filters, role=role)
    data["rows"] = [{"year": row.pop("dimension_value"), **row} for row in data["rows"]]
    return data


def overview(filters: dict | None = None) -> dict:
    where_sql, params = _filter_clause(filters)
    def summary_query():
        from app.service_layer.analysis.dashboard_stats import scope_for

        scope = scope_for(filters)
        if scope is not None and _stats_current():
            rows = _run_query(
                "SELECT discharges,(SELECT COUNT_BIG(*) FROM dbo.analytics_facility_stat f "
                "WHERE f.scope_service_area=s.scope_service_area) AS facilities,"
                "length_of_stay_sum*1.0/NULLIF(length_of_stay_count,0) AS avg_length_of_stay,"
                "total_charges_sum*1.0/NULLIF(total_charges_count,0) AS avg_total_charges,"
                "total_charges_sum AS total_charges FROM dbo.analytics_summary_stat s "
                f"WHERE scope_service_area={storage.PARAM}",
                (scope,),
            )
            if rows:
                return {**rows[0], "engine": "sqlserver_preaggregated"}
        rows = _run_query(
            f"SELECT COUNT_BIG(*) AS discharges, COUNT(DISTINCT facility_name) AS facilities, "
            f"AVG(CAST(length_of_stay AS FLOAT)) AS avg_length_of_stay, "
            f"AVG(CAST(total_charges AS FLOAT)) AS avg_total_charges, "
            f"SUM(CAST(total_charges AS FLOAT)) AS total_charges FROM {TABLE_NAME}{where_sql}",
            params,
        )
        return rows[0] if rows else {}

    jobs = {
        "summary": summary_query,
        "trend": lambda: year_trend(filters)["rows"],
        "diseases": lambda: aggregate("disease", ["count", "avg_length_of_stay", "avg_total_charges"], 8, filters)["rows"],
        "ages": lambda: aggregate("age_group", ["count", "avg_length_of_stay"], 10, filters)["rows"],
        "payments": lambda: payment_ratio(20, filters)["rows"],
        "genders": lambda: aggregate("gender", ["count"], 10, filters)["rows"],
        "severity": lambda: aggregate("severity", ["count", "avg_length_of_stay"], 10, filters)["rows"],
    }
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = {key: executor.submit(func) for key, func in jobs.items()}
        results = {key: future.result() for key, future in futures.items()}
    return {
        **results,
        "filters": filters or {},
    }


def dimension_values(dimension: str, limit: int = 100, role: str = "doctor") -> list:
    data = aggregate(dimension, ["count"], limit, role=role)
    return [row["dimension_value"] for row in data["rows"] if row["dimension_value"] not in (None, "")]
