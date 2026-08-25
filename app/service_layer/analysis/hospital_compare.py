"""角色感知的双医院运营比较。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.common import cache
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


def _case_mix_pair(hospital_a: str, hospital_b: str, filters: dict) -> dict[str, list[dict]]:
    """一次计算并缓存全院病例组合基准，避免每个医院组合重复扫描全表基线。"""
    benchmark_filters = {
        key: value for key, value in filters.items()
        if key in {"year", "year_from", "year_to", "service_area"}
    }
    benchmark, _hit = cache.remember(
        "hospital_case_mix_benchmark",
        {"filters": benchmark_filters, "contract_version": 1},
        lambda: mining.case_mix_adjusted_hospitals(
            filters=benchmark_filters, role="admin", limit=300,
        ),
        ttl=86400,
    )
    by_hospital = {
        registry.normalize_filter_value("hospital", row.get("hospital")): row
        for row in benchmark.get("rows", []) if row.get("hospital")
    }
    return {
        "a": [by_hospital[hospital_a]] if hospital_a in by_hospital else [],
        "b": [by_hospital[hospital_b]] if hospital_b in by_hospital else [],
    }


def _hospital_profile(hospital: str, filters: dict, role: str) -> dict:
    """缓存单院画像，使任意A/B组合复用，而不是为24,531个医院对分别缓存。"""
    def produce():
        profile = {
            "summary": _summary(hospital, filters, role),
            "disease": _group(hospital, "disease", filters, role),
            "trend": _trend(hospital, filters, role),
        }
        if role != "patient":
            profile["severity"] = _group(hospital, "severity", filters, role, 6)
            profile["admission"] = _group(hospital, "admission_type", filters, role, 8)
        return profile

    profile, _hit = cache.remember(
        "hospital_operation_profile",
        {"hospital": hospital, "filters": filters, "role": role, "contract_version": 1},
        produce,
        ttl=86400,
    )
    return profile


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
        "profile_a": lambda: _hospital_profile(a, requested_filters, role),
        "profile_b": lambda: _hospital_profile(b, requested_filters, role),
    }
    if role == "admin":
        jobs["case_mix"] = lambda: _case_mix_pair(a, b, requested_filters)
    with ThreadPoolExecutor(max_workers=min(len(jobs), 10)) as executor:
        futures = {key: executor.submit(job) for key, job in jobs.items()}
        result = {key: future.result() for key, future in futures.items()}
    profile_a, profile_b = result["profile_a"], result["profile_b"]
    if not profile_a["summary"].get("count") or not profile_b["summary"].get("count"):
        raise ValueError(f"当前筛选下每家医院至少需要 {MIN_CASES} 条记录")
    return {
        "hospitals": [{"key": "a", **profile_a["summary"]}, {"key": "b", **profile_b["summary"]}],
        "yearly_trend": {"a": profile_a["trend"], "b": profile_b["trend"]},
        "mixes": {
            "disease": {"a": profile_a["disease"], "b": profile_b["disease"]},
            **({"severity": {"a": profile_a["severity"], "b": profile_b["severity"]},
                "admission": {"a": profile_a["admission"], "b": profile_b["admission"]}} if role != "patient" else {}),
        },
        "case_mix": result["case_mix"] if role == "admin" else None,
        "filters": requested_filters,
        "role_scope": role,
        "caveats": [
            "住院记录不是去重患者人数",
            "账单收费不是实际收入，收费与成本之差不代表利润",
            "医院差异仅用于运营分析，不代表医疗质量评级",
        ],
    }
