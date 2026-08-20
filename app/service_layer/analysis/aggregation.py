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

TABLE_NAME = storage.TABLE_NAME

DIMENSIONS = {
    "disease": "ccsr_diagnosis_description",
    "disease_code": "ccsr_diagnosis_code",
    "age_group": "age_group",
    "hospital": "facility_name",
    "county": "hospital_county",
    "service_area": "hospital_service_area",
    "year": "discharge_year",
    "payment": "payment_typology_1",
    "gender": "gender",
    "admission_type": "type_of_admission",
    "severity": "apr_severity_of_illness_desc",
    "mortality_risk": "apr_risk_of_mortality",
    "disposition": "patient_disposition",
}

DIMENSION_LABELS = {
    "disease": "疾病", "disease_code": "疾病编码", "age_group": "年龄段",
    "hospital": "医疗机构", "county": "地区", "service_area": "服务区域",
    "year": "出院年份", "payment": "支付方式", "gender": "性别",
    "admission_type": "入院类型", "severity": "病情严重程度",
    "mortality_risk": "死亡风险", "disposition": "离院去向",
}

METRICS = {
    "count": "COUNT_BIG(*)",
    "avg_length_of_stay": "AVG(CAST(length_of_stay AS FLOAT))",
    "avg_total_charges": "AVG(CAST(total_charges AS FLOAT))",
    "sum_total_charges": "SUM(CAST(total_charges AS FLOAT))",
    "avg_total_costs": "AVG(CAST(total_costs AS FLOAT))",
    "sum_total_costs": "SUM(CAST(total_costs AS FLOAT))",
}

FILTERS = {
    "year": ("discharge_year", int),
    "hospital": ("facility_name", str),
    "county": ("hospital_county", str),
    "service_area": ("hospital_service_area", str),
    "gender": ("gender", str),
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


def _filter_clause(filters: dict | None) -> tuple[str, list]:
    clauses, params = [], []
    for key, value in (filters or {}).items():
        if value in (None, ""):
            continue
        if key not in FILTERS:
            raise ValueError(f"不支持的筛选项: {key}，可选 {list(FILTERS)}")
        column, caster = FILTERS[key]
        try:
            params.append(caster(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"筛选项 {key} 的值不合法") from exc
        clauses.append(f"[{column}] = {storage.PARAM}")
    return (" WHERE " + " AND ".join(clauses), params) if clauses else ("", params)


def aggregate(
    dimension: str,
    metrics: Optional[list[str]] = None,
    limit: int = 20,
    filters: dict | None = None,
) -> dict:
    if dimension not in DIMENSIONS:
        raise ValueError(f"未知维度: {dimension}，可选 {list(DIMENSIONS)}")
    metrics = metrics or ["count", "avg_length_of_stay"]
    unknown_metrics = [metric for metric in metrics if metric not in METRICS]
    if unknown_metrics:
        raise ValueError(f"未知指标: {unknown_metrics}，可选 {list(METRICS)}")
    limit = max(1, min(int(limit), 100))
    dim_col = DIMENSIONS[dimension]
    where_sql, params = _filter_clause(filters)
    select = [f"[{dim_col}] AS dimension_value"] + [f"{METRICS[key]} AS [{key}]" for key in metrics]
    order = f"[{dim_col}] ASC" if dimension == "year" else "COUNT_BIG(*) DESC"
    sql = (
        f"SELECT TOP {limit} {', '.join(select)} FROM {TABLE_NAME}{where_sql} "
        f"GROUP BY [{dim_col}] ORDER BY {order}"
    )
    return {
        "dimension": dimension,
        "dimension_label": DIMENSION_LABELS[dimension],
        "metrics": metrics,
        "filters": filters or {},
        "rows": _run_query(sql, params),
    }


def avg_length_of_stay_by(dimension: str = "age_group", limit: int = 20, filters: dict | None = None) -> dict:
    return aggregate(dimension, ["count", "avg_length_of_stay", "avg_total_charges"], limit, filters)


def cost_distribution(dimension: str = "disease", limit: int = 20, filters: dict | None = None) -> dict:
    return aggregate(dimension, ["count", "sum_total_charges", "avg_total_charges", "avg_total_costs"], limit, filters)


def payment_ratio(limit: int = 20, filters: dict | None = None) -> dict:
    limit = max(1, min(int(limit), 100))
    where_sql, params = _filter_clause(filters)
    dim = DIMENSIONS["payment"]
    total_row = _run_query(f"SELECT COUNT_BIG(*) AS total FROM {TABLE_NAME}{where_sql}", params)
    total = int(total_row[0]["total"]) if total_row else 0
    rows = _run_query(
        f"SELECT TOP {limit} [{dim}] AS payment, COUNT_BIG(*) AS count FROM {TABLE_NAME}{where_sql} "
        f"GROUP BY [{dim}] ORDER BY COUNT_BIG(*) DESC",
        params,
    )
    for row in rows:
        row["ratio"] = round(row["count"] / total, 6) if total else 0
    return {"dimension": "payment", "dimension_label": "支付方式", "metrics": ["count", "ratio"], "rows": rows, "total": total}


def year_trend(filters: dict | None = None) -> dict:
    data = aggregate("year", ["count", "avg_total_charges", "avg_length_of_stay"], limit=50, filters=filters)
    data["rows"] = [{"year": row.pop("dimension_value"), **row} for row in data["rows"]]
    return data


def overview(filters: dict | None = None) -> dict:
    where_sql, params = _filter_clause(filters)
    def summary_query():
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


def dimension_values(dimension: str, limit: int = 100) -> list:
    data = aggregate(dimension, ["count"], limit)
    return [row["dimension_value"] for row in data["rows"] if row["dimension_value"] not in (None, "")]
