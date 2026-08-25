"""四年数据挖掘专题服务。

通用趋势尽量复用角色感知聚合内核；医院病例组合校正和数据质量使用专用、
只读 SQL。所有财务和医院排名能力在服务端强制要求管理员角色。
"""
from __future__ import annotations

from collections import defaultdict

from app.data_layer import storage
from app.service_layer.analysis import aggregation, registry

YEARS = (2021, 2022, 2023, 2024)


def _year_filters(filters: dict | None) -> dict:
    result = dict(filters or {})
    if not any(key in result for key in ("year", "year_from", "year_to")):
        result.update(year_from=YEARS[0], year_to=YEARS[-1])
    return result


def cross_year_trend(
    dimension: str,
    metrics: list[str],
    *,
    filters: dict | None = None,
    role: str = "doctor",
    limit: int = 100,
) -> dict:
    """按年份与一个业务维度分析，并为数值指标补充同比。"""
    if dimension == "year":
        dimensions = ["year"]
    else:
        dimensions = ["year", dimension]
    requested = list(dict.fromkeys(["count", *metrics]))
    data = aggregation.aggregate(
        dimensions, requested, limit=limit, filters=_year_filters(filters), role=role,
    )
    previous: dict[tuple, dict] = {}
    for row in sorted(data["rows"], key=lambda item: (str(item.get(dimension, "")), int(item.get("year") or 0))):
        series_key = tuple(row.get(key) for key in dimensions if key != "year")
        before = previous.get(series_key)
        for metric in requested:
            current = row.get(metric)
            old = before.get(metric) if before else None
            row[f"{metric}_yoy_pct"] = (
                round((float(current) / float(old) - 1) * 100, 2)
                if current is not None and old not in (None, 0) else None
            )
        previous[series_key] = row
    data.update(
        analysis_type="cross_year_trend",
        years=list(YEARS),
        caveats=["金额为名义美元，未进行通胀调整", "同比变化不代表因果关系"],
    )
    return data


def growth_ranking(
    dimension: str,
    metric: str,
    *,
    filters: dict | None = None,
    role: str = "doctor",
    limit: int = 20,
) -> dict:
    """比较每个分组首末年度的指标变化，返回绝对增长与增长率排名。"""
    if dimension == "year":
        raise ValueError("增长排名需要疾病、医院或区域等比较对象，不能只使用年份")
    dimension_spec = registry.require_dimension(dimension, role)
    metric_spec = registry.require_metric(metric, role)
    requested_filters = _year_filters(filters)
    where_sql, params = aggregation._filter_clause(requested_filters, role)
    # 增长率对小基数极其敏感，每个年度至少100条才进入排名。
    minimum = max(100, 11 if role == "patient" else 1, dimension_spec.min_count)
    rows = aggregation._run_query(
        f"SELECT discharge_year AS [year],({dimension_spec.expression}) AS dimension_value,"
        f"COUNT_BIG(*) AS [count],{metric_spec.expression} AS metric_value "
        f"FROM {storage.TABLE_NAME}{where_sql} GROUP BY discharge_year,({dimension_spec.expression}) "
        f"HAVING COUNT_BIG(*)>={int(minimum)} ORDER BY discharge_year ASC",
        params,
    )
    series: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("metric_value") is not None:
            series[str(row.get("dimension_value") or "(未标注)")].append(row)
    ranked = []
    for label, points in series.items():
        points.sort(key=lambda item: int(item["year"]))
        if len(points) < 2:
            continue
        first, last = points[0], points[-1]
        baseline = float(first["metric_value"])
        latest = float(last["metric_value"])
        absolute = latest - baseline
        ranked.append({
            dimension: label,
            "dimension_value": label,
            "baseline_year": int(first["year"]),
            "latest_year": int(last["year"]),
            "baseline_value": baseline,
            "latest_value": latest,
            "absolute_growth": round(absolute, 4),
            "growth_pct": round(absolute * 100.0 / baseline, 2) if baseline else None,
            "latest_count": int(last["count"]),
            "yearly_values": [
                {"year": int(point["year"]), "value": point["metric_value"], "count": int(point["count"])}
                for point in points
            ],
        })
    limit = max(1, min(int(limit), 100))
    comparable = [item for item in ranked if item["growth_pct"] is not None]
    growth_rows = sorted(comparable, key=lambda item: item["growth_pct"], reverse=True)[:limit]
    decline_rows = sorted(comparable, key=lambda item: item["growth_pct"])[:limit]
    absolute_rows = sorted(ranked, key=lambda item: abs(item["absolute_growth"]), reverse=True)[:limit]
    return {
        "analysis_type": "cross_year_growth_ranking",
        "dimension": dimension,
        "dimensions": [dimension],
        "dimension_label": dimension_spec.label,
        "metrics": ["growth_pct", "absolute_growth"],
        "source_metric": metric,
        "source_metric_label": metric_spec.label,
        "filters": requested_filters,
        "rows": growth_rows,
        "ranking_views": {
            "growth": growth_rows,
            "decline": decline_rows,
            "absolute": absolute_rows,
        },
        "suppression_threshold": minimum,
        "caveats": [
            "增长率按该分组最早可用年度与最晚可用年度计算",
            "金额为名义美元，未进行通胀或病例组合调整",
            "基数较小的分组可能出现较高增长率，应同时查看绝对增长和记录量",
        ],
    }


def case_mix_adjusted_hospitals(
    *, filters: dict | None = None, role: str = "admin", limit: int = 20,
) -> dict:
    """在年度×APR DRG×严重程度层内计算医院成本和住院日观察/预期指数。"""
    if role != "admin":
        raise PermissionError("病例组合校正后的医院比较仅限管理员")
    requested_filters = _year_filters(filters)
    unsupported = set(requested_filters) - {"year", "year_from", "year_to", "service_area", "hospital"}
    if unsupported:
        raise ValueError(f"病例组合校正暂不支持筛选项: {sorted(unsupported)}")
    operators = {"year": "=", "year_from": ">=", "year_to": "<="}
    baseline_clauses, baseline_params = [], []
    detail_clauses, detail_params = [], []
    hospital_expr = registry.HOSPITAL_SQL.replace("facility_name", "d.facility_name")
    for key in ("year", "year_from", "year_to"):
        if key in requested_filters:
            baseline_clauses.append(f"discharge_year {operators[key]} {storage.PARAM}")
            detail_clauses.append(f"d.discharge_year {operators[key]} {storage.PARAM}")
            baseline_params.append(int(requested_filters[key]))
            detail_params.append(int(requested_filters[key]))
    if requested_filters.get("service_area"):
        value = registry.normalize_filter_value("service_area", requested_filters["service_area"])
        baseline_clauses.append(f"({registry.SERVICE_AREA_SQL})={storage.PARAM}")
        detail_clauses.append(
            f"(CASE WHEN d.hospital_service_area IN (N'Capital/Adirond',N'Capital/Adirondacks') "
            f"THEN N'Capital/Adirondacks' ELSE COALESCE(NULLIF(LTRIM(RTRIM(d.hospital_service_area)),N''),N'(未标注)') END)={storage.PARAM}"
        )
        baseline_params.append(value); detail_params.append(value)
    if requested_filters.get("hospital"):
        detail_clauses.append(f"({hospital_expr})={storage.PARAM}")
        detail_params.append(registry.normalize_filter_value("hospital", requested_filters["hospital"]))
    baseline_where = " AND ".join(baseline_clauses) or "1=1"
    detail_where = " AND ".join(detail_clauses) or "1=1"
    limit = max(1, min(int(limit), 50))
    sql = f"""
WITH baseline AS (
    SELECT discharge_year,apr_drg_code,apr_severity_of_illness_code,
           AVG(CAST(total_costs AS FLOAT)) AS expected_cost,
           AVG(CAST(length_of_stay AS FLOAT)) AS expected_los
    FROM {storage.TABLE_NAME}
    WHERE {baseline_where} AND total_costs IS NOT NULL AND length_of_stay IS NOT NULL
      AND apr_drg_code IS NOT NULL AND apr_severity_of_illness_code IS NOT NULL
    GROUP BY discharge_year,apr_drg_code,apr_severity_of_illness_code
), scored AS (
    SELECT {hospital_expr} AS hospital,
           COUNT_BIG(*) AS case_count,
           SUM(CAST(d.total_costs AS FLOAT)) AS actual_cost,
           SUM(b.expected_cost) AS expected_cost,
           SUM(CAST(d.length_of_stay AS FLOAT)) AS actual_los,
           SUM(b.expected_los) AS expected_los
    FROM {storage.TABLE_NAME} d
    JOIN baseline b ON b.discharge_year=d.discharge_year
      AND b.apr_drg_code=d.apr_drg_code
      AND b.apr_severity_of_illness_code=d.apr_severity_of_illness_code
    WHERE {detail_where} AND d.total_costs IS NOT NULL AND d.length_of_stay IS NOT NULL AND d.facility_name IS NOT NULL
    GROUP BY {hospital_expr}
    HAVING COUNT_BIG(*)>=100
)
SELECT TOP {limit} hospital,case_count,
       actual_cost/NULLIF(expected_cost,0) AS case_mix_cost_index,
       actual_los/NULLIF(expected_los,0) AS case_mix_los_index,
       actual_cost/NULLIF(case_count,0) AS avg_actual_cost,
       expected_cost/NULLIF(case_count,0) AS avg_expected_cost
FROM scored ORDER BY case_mix_cost_index DESC
"""
    # CTE与明细扫描各使用一次相同筛选参数。
    rows = aggregation._run_query(sql, [*baseline_params, *detail_params])
    for row in rows:
        row["dimension_value"] = row.get("hospital")
    return {
        "analysis_type": "case_mix_adjusted_hospital_benchmark",
        "dimensions": ["hospital"], "dimension": "hospital", "dimension_label": "医疗机构",
        "metrics": ["case_mix_cost_index", "case_mix_los_index"], "filters": _year_filters(filters),
        "rows": rows,
        "caveats": [
            "预期值按年度、APR DRG和严重程度分层计算",
            "这是运营基准而非医疗质量评级",
            "未包含医院净收入、固定成本和院外结局",
        ],
    }


def regional_concentration(*, filters: dict | None = None, role: str = "admin") -> dict:
    """计算服务区域内医院住院量集中度（HHI）。"""
    if role != "admin":
        raise PermissionError("医院和区域运营集中度仅限管理员")
    where_sql, params = aggregation._filter_clause(_year_filters(filters), role)
    service_expr = registry.DIMENSIONS["service_area"].expression
    hospital_expr = registry.DIMENSIONS["hospital"].expression
    rows = aggregation._run_query(
        f"SELECT ({service_expr}) AS service_area,({hospital_expr}) AS hospital,COUNT_BIG(*) AS count "
        f"FROM {storage.TABLE_NAME}{where_sql} GROUP BY ({service_expr}),({hospital_expr})",
        params,
    )
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row["service_area"])].append(row)
    result = []
    for area, hospitals in grouped.items():
        total = sum(int(item["count"]) for item in hospitals)
        hhi = sum((int(item["count"]) / total * 100) ** 2 for item in hospitals) if total else 0
        result.append({
            "service_area": area, "dimension_value": area, "records": total,
            "hospital_count": len(hospitals), "hhi": round(hhi, 2),
            "top_hospital_share_pct": round(max((int(item["count"]) for item in hospitals), default=0) / total * 100, 2) if total else 0,
        })
    return {
        "analysis_type": "regional_hospital_concentration", "dimension": "service_area",
        "dimensions": ["service_area"], "metrics": ["hhi", "hospital_count"],
        "filters": _year_filters(filters), "rows": sorted(result, key=lambda item: item["hhi"], reverse=True),
        "caveats": ["HHI基于住院记录份额，不等同于完整医疗市场份额"],
    }


def data_quality_insights(*, role: str = "admin") -> dict:
    """按年度返回关键完整率、异常率和跨年标签漂移。"""
    if role != "admin":
        raise PermissionError("数据质量和异常分析仅限管理员")
    rows = aggregation._run_query(f"""
SELECT discharge_year AS [year],COUNT_BIG(*) AS records,
 COUNT_BIG(hospital_service_area)*100.0/COUNT_BIG(*) AS service_area_completeness_pct,
 COUNT_BIG(zip_code_3)*100.0/COUNT_BIG(*) AS zip_completeness_pct,
 COUNT_BIG(ccsr_diagnosis_code)*100.0/COUNT_BIG(*) AS diagnosis_completeness_pct,
 SUM(CASE WHEN NULLIF(LTRIM(RTRIM(ccsr_procedure_code)),N'') IS NOT NULL THEN 1.0 ELSE 0 END)*100.0/COUNT_BIG(*) AS procedure_applicable_pct,
 COUNT_BIG(payment_typology_2)*100.0/COUNT_BIG(*) AS secondary_payment_present_pct,
 COUNT_BIG(payment_typology_3)*100.0/COUNT_BIG(*) AS tertiary_payment_present_pct,
 SUM(CASE WHEN total_costs>total_charges THEN 1.0 ELSE 0 END)*100.0/COUNT_BIG(*) AS costs_above_charges_pct,
 SUM(CASE WHEN length_of_stay>=30 THEN 1.0 ELSE 0 END)*100.0/COUNT_BIG(*) AS long_stay_pct,
 SUM(CASE WHEN emergency_department_indicator=N'Y' AND type_of_admission<>N'Emergency' THEN 1.0 ELSE 0 END)*100.0/COUNT_BIG(*) AS ed_admission_mismatch_pct
FROM {storage.TABLE_NAME} GROUP BY discharge_year ORDER BY discharge_year
""")
    return {
        "analysis_type": "data_quality_and_anomaly", "dimension": "year", "dimensions": ["year"],
        "metrics": [key for key in rows[0] if key not in {"year"}] if rows else [], "rows": rows,
        "label_drift": [
            {"field": "age_group", "before": ["0 to 17", "18 to 29", "30 to 49", "50 to 69"], "after": ["0-17", "18-29", "30-49", "50-69"], "normalized": True},
            {"field": "hospital_service_area", "before": "Capital/Adirond", "after": "Capital/Adirondacks", "normalized": True},
            {"field": "source_columns", "before": ["Hospital Service Area", "Zip Code - 3 digits"], "after": ["Health Service Area", "Zip Code"], "normalized": True},
        ],
        "caveats": ["手术编码、支付方式2/3和出生体重属于条件适用字段，空值不能一概视为质量问题"],
    }


TOPIC_DEFAULTS = {
    "disease_trend": ("disease", ["count", "avg_length_of_stay", "avg_total_costs"]),
    "complexity": ("severity", ["count", "avg_length_of_stay", "avg_total_costs"]),
    "pathway": ("procedure", ["count", "avg_length_of_stay", "avg_total_costs"]),
    "emergency": ("admission_type", ["count", "ed_rate", "avg_length_of_stay"]),
    "outcome": ("mortality_risk", ["count", "expired_disposition_rate", "avg_length_of_stay"]),
    "payment": ("payment", ["count", "record_share", "avg_total_costs"]),
    "demographic": ("race", ["count", "avg_length_of_stay", "avg_total_costs"]),
    "maternal_newborn": ("birth_weight_group", ["count", "avg_birth_weight", "avg_total_costs"]),
    "operations": ("service_area", ["count", "avg_length_of_stay", "avg_total_costs"]),
}

TOPIC_ROLES = {
    "growth_ranking": registry.ALL_ROLES,
    "disease_trend": registry.ALL_ROLES,
    "operations": registry.ALL_ROLES,
    "complexity": registry.CLINICAL_ROLES,
    "pathway": registry.CLINICAL_ROLES,
    "emergency": registry.CLINICAL_ROLES,
    "outcome": registry.CLINICAL_ROLES,
    "payment": registry.CLINICAL_ROLES,
    "demographic": registry.CLINICAL_ROLES,
    "maternal_newborn": registry.CLINICAL_ROLES,
    "hospital_benchmark": registry.ADMIN_ONLY,
    "regional_concentration": registry.ADMIN_ONLY,
    "data_quality": registry.ADMIN_ONLY,
}


def topic_analysis(
    topic: str, *, role: str, filters: dict | None = None, limit: int = 100,
    dimension: str | None = None, metrics: list[str] | None = None,
) -> dict:
    """供AI工具路由调用的专题入口。"""
    if topic not in TOPIC_ROLES:
        raise ValueError(f"未知挖掘专题: {topic}")
    if role not in TOPIC_ROLES[topic]:
        raise PermissionError("当前角色无权访问该分析专题")
    if topic == "growth_ranking":
        return growth_ranking(
            dimension or "disease", (metrics or ["count"])[0],
            filters=filters, role=role, limit=limit,
        )
    if topic == "hospital_benchmark":
        return case_mix_adjusted_hospitals(filters=filters, role=role, limit=min(limit, 50))
    if topic == "regional_concentration":
        return regional_concentration(filters=filters, role=role)
    if topic == "data_quality":
        return data_quality_insights(role=role)
    if topic == "pathway" and any((filters or {}).get(key) for key in ("disease", "disease_code", "procedure_code")):
        from app.service_layer.analysis.association import disease_procedure_associations

        data = disease_procedure_associations(limit=min(limit, 100), min_count=11, filters=_year_filters(filters))
        data.update(
            analysis_type="disease_procedure_pathway", dimension="procedure", dimensions=["procedure"],
            dimension_label="手术/操作", metrics=["pair_count", "support", "confidence", "lift"],
        )
        for row in data["rows"]:
            row["dimension_value"] = row.get("procedure")
        return data
    dimension, metrics = TOPIC_DEFAULTS[topic]
    if role == "patient":
        metrics = ["count", "avg_length_of_stay", "avg_total_charges"]
    return cross_year_trend(dimension, metrics, filters=filters, role=role, limit=limit)
