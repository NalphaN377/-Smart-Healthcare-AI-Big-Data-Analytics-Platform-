"""主要诊断—主要手术关联分析。

SPARCS 脱敏出院数据每条记录只有一个主要诊断和一个主要手术，因此这里计算的是
出院记录级组合强度，不代表同一患者的多疾病共现或因果关系。
"""
from __future__ import annotations

from app.data_layer import storage
from app.data_layer.sql_tasks import run_long_sql
from app.service_layer.analysis.aggregation import _run_query

STAT_TABLE = "dbo.disease_procedure_stat"


def _validate_filters(filters: dict | None) -> tuple[str, list]:
    filters = filters or {}
    unsupported = sorted(set(filters) - {"year", "year_from", "year_to", "disease", "disease_code", "procedure_code"})
    if unsupported:
        raise ValueError(f"关联预聚合当前仅支持 year 筛选，不支持: {unsupported}")
    clauses, params = [], []
    operators = {"year": "=", "year_from": ">=", "year_to": "<="}
    for key, operator in operators.items():
        if filters.get(key) in (None, ""):
            continue
        try:
            params.append(int(filters[key]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"筛选项 {key} 的值不合法") from exc
        clauses.append(f"discharge_year{operator}{storage.PARAM}")
    if filters.get("disease") not in (None, ""):
        clauses.append(f"UPPER(diagnosis_description)={storage.PARAM}")
        params.append(str(filters["disease"]).strip().upper())
    if filters.get("disease_code") not in (None, ""):
        clauses.append(f"diagnosis_code={storage.PARAM}")
        params.append(str(filters["disease_code"]).strip())
    if filters.get("procedure_code") not in (None, ""):
        clauses.append(f"procedure_code={storage.PARAM}")
        params.append(str(filters["procedure_code"]).strip())
    return (" WHERE " + " AND ".join(clauses), params) if clauses else ("", [])


def refresh_association_stats() -> dict:
    """从业务表重建预聚合统计；仅供初始化或修复，不在 Web 请求内调用。"""
    storage.init_schema()
    data_version = storage.get_data_version()
    sql = f"""
SET NOCOUNT ON;
SET XACT_ABORT ON;
SELECT discharge_year,
       ccsr_diagnosis_code AS diagnosis_code,
       MAX(ccsr_diagnosis_description) AS diagnosis_description,
       ccsr_procedure_code AS procedure_code,
       MAX(ccsr_procedure_description) AS procedure_description,
       COUNT_BIG(*) AS pair_count
INTO #disease_procedure_stat_build
FROM {storage.TABLE_NAME}
WHERE discharge_year IS NOT NULL
  AND ccsr_diagnosis_code IS NOT NULL AND LTRIM(RTRIM(ccsr_diagnosis_code))<>''
  AND ccsr_procedure_code IS NOT NULL AND LTRIM(RTRIM(ccsr_procedure_code))<>''
GROUP BY discharge_year, ccsr_diagnosis_code, ccsr_procedure_code;

BEGIN TRANSACTION;
TRUNCATE TABLE {STAT_TABLE};
INSERT INTO {STAT_TABLE}
    (discharge_year,diagnosis_code,diagnosis_description,procedure_code,procedure_description,pair_count)
SELECT discharge_year,diagnosis_code,diagnosis_description,procedure_code,procedure_description,pair_count
FROM #disease_procedure_stat_build;
MERGE dbo.system_state AS target
USING (SELECT N'association_data_version' AS state_key, CAST({int(data_version)} AS BIGINT) AS int_value) AS source
ON target.state_key=source.state_key
WHEN MATCHED THEN UPDATE SET int_value=source.int_value,updated_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT(state_key,int_value) VALUES(source.state_key,source.int_value);
COMMIT TRANSACTION;
"""
    run_long_sql(sql)
    status = association_status()
    return {"refreshed": True, **status}


def association_status() -> dict:
    rows = _run_query(
        f"SELECT COUNT_BIG(*) AS pair_groups,COALESCE(SUM(pair_count),0) AS represented_records,"
        "MIN(discharge_year) AS min_year,MAX(discharge_year) AS max_year,MAX(updated_at) AS updated_at "
        f"FROM {STAT_TABLE}"
    )
    state = _run_query(
        "SELECT int_value AS association_data_version,updated_at AS version_updated_at "
        "FROM dbo.system_state WHERE state_key=N'association_data_version'"
    )
    return {**(rows[0] if rows else {}), **(state[0] if state else {})}


def disease_procedure_associations(
    *,
    limit: int = 20,
    min_count: int = 100,
    filters: dict | None = None,
) -> dict:
    """返回支持度、置信度和提升度最高的主要诊断—主要手术组合。"""
    if not 1 <= int(limit) <= 100:
        raise ValueError("limit 必须在 1 到 100 之间")
    if not 11 <= int(min_count) <= 1_000_000:
        raise ValueError("min_count 必须在 11 到 1000000 之间")

    where_sql, params = _validate_filters(filters)

    # 先聚合组合，再用窗口函数在一次分组结果上计算边际频数，避免三次全表扫描。
    sql = f"""
WITH pair_counts AS (
    SELECT
        diagnosis_code,
        MAX(diagnosis_description) AS diagnosis,
        procedure_code,
        MAX(procedure_description) AS [procedure],
        SUM(pair_count) AS pair_count
    FROM {STAT_TABLE}{where_sql}
    GROUP BY diagnosis_code, procedure_code
), scored AS (
    SELECT *,
        SUM(pair_count) OVER () AS total_count,
        SUM(pair_count) OVER (PARTITION BY diagnosis_code) AS diagnosis_count,
        SUM(pair_count) OVER (PARTITION BY procedure_code) AS procedure_count
    FROM pair_counts
)
SELECT TOP {int(limit)}
    diagnosis_code, diagnosis, procedure_code, [procedure], pair_count,
    CAST(pair_count * 1.0 / NULLIF(total_count, 0) AS DECIMAL(18,8)) AS support,
    CAST(pair_count * 1.0 / NULLIF(diagnosis_count, 0) AS DECIMAL(18,8)) AS confidence,
    CAST(pair_count * 1.0 * total_count /
        NULLIF(CAST(diagnosis_count AS FLOAT) * CAST(procedure_count AS FLOAT), 0)
        AS DECIMAL(18,6)) AS lift
FROM scored
WHERE pair_count >= {storage.PARAM}
ORDER BY lift DESC, pair_count DESC;
"""
    rows = _run_query(sql, [*params, int(min_count)])
    return {
        "analysis_level": "discharge_primary_diagnosis_primary_procedure",
        "engine": "sqlserver_preaggregated",
        "interpretation": "提升度大于1表示该主要诊断与主要手术组合出现频率高于独立假设下的预期。",
        "limitations": [
            "每条记录仅含一个主要诊断和一个主要手术，不能用于患者级多疾病共现分析。",
            "关联不代表因果关系，也不能用于个体诊疗决策。",
        ],
        "filters": filters or {},
        "min_count": int(min_count),
        "rows": rows,
    }
