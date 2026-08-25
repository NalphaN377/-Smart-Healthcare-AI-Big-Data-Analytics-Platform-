"""为 AI 解读提供服务端可信的双对象比较数据。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.service_layer.analysis import aggregation, hospital_compare, registry


def _metrics(role: str) -> list[str]:
    metrics = ["count", "avg_length_of_stay", "avg_total_charges"]
    if role != "patient":
        metrics += ["avg_total_costs"]
    return metrics


def _compact_hospitals(a: str, b: str, filters: dict, role: str) -> list[dict]:
    hospital_a = hospital_compare._hospital_value(a)
    hospital_b = hospital_compare._hospital_value(b)
    if hospital_a == hospital_b:
        raise ValueError("请选择两个不同的比较对象")
    requested = dict(filters)
    requested.pop("hospital", None)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(hospital_compare._summary, hospital, requested, role)
            for hospital in (hospital_a, hospital_b)
        ]
        rows = [future.result() for future in futures]
    if any(not row.get("count") for row in rows):
        raise ValueError("当前筛选下每家医院至少需要 100 条记录")
    return rows


def trusted_comparison(
    comparison_type: str, a, b, *, filters: dict | None = None, role: str = "patient",
) -> dict:
    """重新查询 A/B 的可信聚合指标，避免 AI 退化为知识库猜测。"""
    kind = str(comparison_type or "").strip().lower()
    if kind not in {"year", "region", "hospital"}:
        raise ValueError("comparison_type 仅支持 year、region 或 hospital")
    requested = dict(filters or {})
    if kind == "hospital":
        rows = _compact_hospitals(str(a or ""), str(b or ""), requested, role)
        dimension, label = "hospital", "医疗机构"
    else:
        dimension = "year" if kind == "year" else "service_area"
        label = "出院年份" if kind == "year" else "服务区域"
        requested.pop(dimension, None)
        if kind == "year":
            values = [int(a), int(b)]
        else:
            values = [registry.normalize_filter_value("service_area", str(a or "")), registry.normalize_filter_value("service_area", str(b or ""))]
        if values[0] == values[1] or any(value in {"", None} for value in values):
            raise ValueError("请选择两个不同的比较对象")
        result = aggregation.aggregate(dimension, _metrics(role), 100, requested, role=role)
        lookup = {
            str(row.get(dimension) if row.get(dimension) is not None else row.get("dimension_value")): row
            for row in result["rows"]
        }
        rows = [lookup.get(str(value)) for value in values]
        if any(row is None for row in rows):
            raise ValueError("当前筛选下缺少所选对象的聚合结果")
    return {
        "analysis_type": "trusted_pair_comparison",
        "dimension": dimension,
        "dimension_label": label,
        "metrics": _metrics(role),
        "filters": requested,
        "objects": {"a": a, "b": b},
        "rows": rows,
        "caveats": [
            "住院量按出院记录条数统计，不是去重患者人数",
            "费用为名义美元，账单收费不等于实际收入",
            "差异仅用于运营分析，不代表因果关系或医疗质量排名",
        ],
    }
