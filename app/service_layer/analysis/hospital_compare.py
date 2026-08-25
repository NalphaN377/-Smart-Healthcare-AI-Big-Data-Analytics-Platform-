"""角色感知的双医院运营比较。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.data_layer import storage
from app.service_layer.analysis import aggregation, mining, registry

MIN_CASES = 100


def _hospital_value(value: str) -> str:
    clean = registry.normalize_filter_value("hospital", str(value or ""))
    if not clean or clean == "(未标注)" or len(clean) > 200:
        raise ValueError("请选择有效的医疗机构")
    return clean


def list_hospitals(*, search: str = "", service_area: str = "", limit: int = 50) -> list[dict]:
    """从运营预汇总目录返回医院；样本阈值在实际比较时再次校验。"""
    clauses, params = [f"scope_service_area<>{storage.PARAM}"], ["__ALL__"]
    hospital = registry.HOSPITAL_SQL
    if search.strip():
        normalized_search = search.strip().replace("`", "'").upper()
        clauses.append(f"({hospital}) LIKE {storage.PARAM}")
        params.append(f"%{normalized_search}%")
    if service_area.strip():
        clauses.append(f"scope_service_area={storage.PARAM}")
        params.append(registry.normalize_filter_value("service_area", service_area))
    where = f"WHERE {' AND '.join(clauses)}"
    rows = aggregation._run_query(
        f"SELECT TOP {max(1, min(int(limit), 300))} ({hospital}) AS hospital,"
        f"MIN(scope_service_area) AS service_area,CAST(NULL AS BIGINT) AS count "
        f"FROM dbo.analytics_facility_stat {where} GROUP BY ({hospital}) ORDER BY hospital",
        params,
    )
    return rows


def _hospital_where(hospital: str, filters: dict, role: str) -> tuple[str, list]:
    where, params = aggregation._filter_clause(filters, role)
    connector = " AND " if where else " WHERE "
    # facility_name 已有普通索引；不要在筛选谓词上包 UPPER/LTRIM，否则 850 万行会退化为全表扫描。
    # SQL Server 默认不区分大小写且字符串等值会忽略尾随空格，第二个候选兼容历史反引号转义。
    legacy = hospital.replace("'", "`")
    return (
        f"{where}{connector}facility_name IN ({storage.PARAM},{storage.PARAM})",
        [*params, hospital, legacy],
    )


def _summary(hospital: str, filters: dict, role: str) -> dict:
    metric_keys = ["count", "avg_length_of_stay", "avg_total_charges"]
    if role != "patient":
        metric_keys += ["avg_total_costs", "costs_per_day", "ed_rate", "surgical_rate", "long_stay_rate"]
    where, params = _hospital_where(hospital, filters, role)
    metrics = [registry.require_metric(key, role) for key in metric_keys]
    rows = aggregation._run_query(
        f"SELECT {','.join(f'{metric.expression} AS [{metric.key}]' for metric in metrics)} "
        f"FROM {storage.TABLE_NAME}{where} HAVING COUNT_BIG(*)>={MIN_CASES}",
        params,
    )
    return {"hospital": hospital, **(rows[0] if rows else {})}


def _group(hospital: str, dimension: str, filters: dict, role: str, limit: int = 10) -> list[dict]:
    spec = registry.require_dimension(dimension, role)
    where, params = _hospital_where(hospital, filters, role)
    minimum = max(MIN_CASES if role == "patient" else 30, spec.min_count)
    rows = aggregation._run_query(
        f"SELECT TOP {max(1, min(int(limit), 20))} ({spec.expression}) AS dimension_value,"
        f"COUNT_BIG(*) AS count,COUNT_BIG(*)*100.0/NULLIF(SUM(COUNT_BIG(*)) OVER(),0) AS share_pct,"
        f"AVG(CAST(length_of_stay AS FLOAT)) AS avg_length_of_stay "
        f"FROM {storage.TABLE_NAME}{where} GROUP BY ({spec.expression}) "
        f"HAVING COUNT_BIG(*)>={minimum} ORDER BY COUNT_BIG(*) DESC",
        params,
    )
    return rows


def _trend(hospital: str, filters: dict, role: str) -> list[dict]:
    requested = {key: value for key, value in filters.items() if key != "year"}
    where, params = _hospital_where(hospital, requested, role)
    rows = aggregation._run_query(
        f"SELECT discharge_year AS [year],COUNT_BIG(*) AS count,"
        f"AVG(CAST(length_of_stay AS FLOAT)) AS avg_length_of_stay,"
        f"AVG(CAST(total_charges AS FLOAT)) AS avg_total_charges "
        f"FROM {storage.TABLE_NAME}{where} GROUP BY discharge_year ORDER BY discharge_year",
        params,
    )
    return rows


def compare_hospitals(
    hospital_a: str, hospital_b: str, *, filters: dict | None = None, role: str = "patient",
) -> dict:
    """在同一筛选范围内比较两家医院。"""
    a, b = _hospital_value(hospital_a), _hospital_value(hospital_b)
    if a == b:
        raise ValueError("请选择两家不同的医疗机构")
    requested_filters = dict(filters or {})
    requested_filters.pop("hospital", None)
    jobs = {
        "summary_a": lambda: _summary(a, requested_filters, role),
        "summary_b": lambda: _summary(b, requested_filters, role),
        "disease_a": lambda: _group(a, "disease", requested_filters, role),
        "disease_b": lambda: _group(b, "disease", requested_filters, role),
        "trend_a": lambda: _trend(a, requested_filters, role),
        "trend_b": lambda: _trend(b, requested_filters, role),
    }
    if role != "patient":
        jobs.update(
            severity_a=lambda: _group(a, "severity", requested_filters, role, 6),
            severity_b=lambda: _group(b, "severity", requested_filters, role, 6),
            admission_a=lambda: _group(a, "admission_type", requested_filters, role, 8),
            admission_b=lambda: _group(b, "admission_type", requested_filters, role, 8),
        )
    if role == "admin":
        case_mix_filters = {key: value for key, value in requested_filters.items() if key in {"year", "year_from", "year_to", "service_area"}}
        jobs.update(
            case_mix_a=lambda: mining.case_mix_adjusted_hospitals(filters={**case_mix_filters, "hospital": a}, role=role, limit=1),
            case_mix_b=lambda: mining.case_mix_adjusted_hospitals(filters={**case_mix_filters, "hospital": b}, role=role, limit=1),
        )
    with ThreadPoolExecutor(max_workers=min(len(jobs), 10)) as executor:
        futures = {key: executor.submit(job) for key, job in jobs.items()}
        result = {key: future.result() for key, future in futures.items()}
    if not result["summary_a"].get("count") or not result["summary_b"].get("count"):
        raise ValueError(f"当前筛选下每家医院至少需要 {MIN_CASES} 条记录")
    return {
        "hospitals": [{"key": "a", **result["summary_a"]}, {"key": "b", **result["summary_b"]}],
        "yearly_trend": {"a": result["trend_a"], "b": result["trend_b"]},
        "mixes": {
            "disease": {"a": result["disease_a"], "b": result["disease_b"]},
            **({"severity": {"a": result["severity_a"], "b": result["severity_b"]},
                "admission": {"a": result["admission_a"], "b": result["admission_b"]}} if role != "patient" else {}),
        },
        "case_mix": ({"a": result["case_mix_a"]["rows"], "b": result["case_mix_b"]["rows"]} if role == "admin" else None),
        "filters": requested_filters,
        "role_scope": role,
        "caveats": [
            "住院记录不是去重患者人数",
            "账单收费不是实际收入，收费与成本之差不代表利润",
            "医院差异仅用于运营分析，不代表医疗质量评级",
        ],
    }
