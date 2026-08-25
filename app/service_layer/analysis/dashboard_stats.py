"""运营总览轻量预汇总，避免 Redis 冷启动时重复扫描全量业务表。"""
from __future__ import annotations

from app.data_layer import storage
from app.data_layer.sql_tasks import run_long_sql
from app.service_layer.analysis import registry

ALL_SCOPE = "__ALL__"
NULL_VALUE = "(未标注)"
STAT_DIMENSIONS = {
    key: registry.DIMENSIONS[key].expression
    for key in ("disease", "age_group", "year", "payment", "gender", "severity")
}


def _scope_expression() -> str:
    return (
        f"CASE WHEN GROUPING({registry.SERVICE_AREA_SQL})=1 THEN N'{ALL_SCOPE}' "
        f"ELSE ({registry.SERVICE_AREA_SQL}) END"
    )


def _dimension_select(name: str, expression: str) -> str:
    scope = _scope_expression()
    value = f"COALESCE(CONVERT(NVARCHAR(300),({expression})),N'{NULL_VALUE}')"
    return f"""
SELECT {scope} AS scope_service_area,N'{name}' AS dimension_name,{value} AS dimension_value,
       COUNT_BIG(*) AS record_count,
       COALESCE(SUM(CONVERT(BIGINT,length_of_stay)),0) AS length_of_stay_sum,
       COUNT_BIG(length_of_stay) AS length_of_stay_count,
       COALESCE(SUM(CONVERT(DECIMAL(38,2),total_charges)),0) AS total_charges_sum,
       COUNT_BIG(total_charges) AS total_charges_count,
       COALESCE(SUM(CONVERT(DECIMAL(38,2),total_costs)),0) AS total_costs_sum,
       COUNT_BIG(total_costs) AS total_costs_count
FROM {storage.TABLE_NAME}
GROUP BY GROUPING SETS ((({expression})),(({registry.SERVICE_AREA_SQL}),({expression})))
""".strip()


def refresh_dashboard_stats() -> dict:
    """全量重建小型统计表；使用临时表构建，交换阶段才持有短事务。"""
    storage.init_schema()
    data_version = storage.get_data_version()
    dimension_columns = (
        "scope_service_area,dimension_name,dimension_value,record_count,length_of_stay_sum,"
        "length_of_stay_count,total_charges_sum,total_charges_count,total_costs_sum,total_costs_count"
    )
    dimension_inserts = "\n".join(
        f"INSERT INTO #dimension_build({dimension_columns})\n"
        f"{_dimension_select(name, column)}\nOPTION (MAXDOP 1, MAX_GRANT_PERCENT=5);"
        for name, column in STAT_DIMENSIONS.items()
    )
    scope = _scope_expression()
    sql = f"""
SET NOCOUNT ON;
SET XACT_ABORT ON;
SELECT {scope} AS scope_service_area,COUNT_BIG(*) AS discharges,
       COALESCE(SUM(CONVERT(BIGINT,length_of_stay)),0) AS length_of_stay_sum,
       COUNT_BIG(length_of_stay) AS length_of_stay_count,
       COALESCE(SUM(CONVERT(DECIMAL(38,2),total_charges)),0) AS total_charges_sum,
       COUNT_BIG(total_charges) AS total_charges_count
INTO #summary_build
FROM {storage.TABLE_NAME}
GROUP BY GROUPING SETS ((),(({registry.SERVICE_AREA_SQL})))
OPTION (MAXDOP 1, MAX_GRANT_PERCENT=5);

CREATE TABLE #dimension_build (
    scope_service_area NVARCHAR(100) NOT NULL,dimension_name NVARCHAR(30) NOT NULL,
    dimension_value NVARCHAR(300) NOT NULL,record_count BIGINT NOT NULL,
    length_of_stay_sum BIGINT NOT NULL,length_of_stay_count BIGINT NOT NULL,
    total_charges_sum DECIMAL(38,2) NOT NULL,total_charges_count BIGINT NOT NULL,
    total_costs_sum DECIMAL(38,2) NOT NULL,total_costs_count BIGINT NOT NULL
);
{dimension_inserts}

SELECT {scope} AS scope_service_area,facility_name
INTO #facility_build
FROM {storage.TABLE_NAME}
WHERE facility_name IS NOT NULL
GROUP BY GROUPING SETS ((facility_name),(({registry.SERVICE_AREA_SQL}),facility_name))
OPTION (MAXDOP 1, MAX_GRANT_PERCENT=5);

BEGIN TRANSACTION;
TRUNCATE TABLE dbo.analytics_summary_stat;
TRUNCATE TABLE dbo.analytics_dimension_stat;
TRUNCATE TABLE dbo.analytics_facility_stat;
INSERT INTO dbo.analytics_summary_stat
    (scope_service_area,discharges,length_of_stay_sum,length_of_stay_count,total_charges_sum,total_charges_count)
SELECT scope_service_area,discharges,length_of_stay_sum,length_of_stay_count,total_charges_sum,total_charges_count
FROM #summary_build;
INSERT INTO dbo.analytics_dimension_stat
    (scope_service_area,dimension_name,dimension_value,record_count,length_of_stay_sum,length_of_stay_count,
     total_charges_sum,total_charges_count,total_costs_sum,total_costs_count)
SELECT scope_service_area,dimension_name,dimension_value,record_count,length_of_stay_sum,length_of_stay_count,
       total_charges_sum,total_charges_count,total_costs_sum,total_costs_count
FROM #dimension_build;
INSERT INTO dbo.analytics_facility_stat(scope_service_area,facility_name)
SELECT scope_service_area,facility_name FROM #facility_build;
MERGE dbo.system_state AS target
USING (SELECT N'analytics_data_version' AS state_key,CAST({int(data_version)} AS BIGINT) AS int_value) AS source
ON target.state_key=source.state_key
WHEN MATCHED THEN UPDATE SET int_value=source.int_value,updated_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT(state_key,int_value) VALUES(source.state_key,source.int_value);
MERGE dbo.system_state AS target
USING (SELECT N'analytics_schema_version' AS state_key,CAST(2 AS BIGINT) AS int_value) AS source
ON target.state_key=source.state_key
WHEN MATCHED THEN UPDATE SET int_value=source.int_value,updated_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT(state_key,int_value) VALUES(source.state_key,source.int_value);
COMMIT TRANSACTION;
"""
    run_long_sql(sql)
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT (SELECT COUNT_BIG(*) FROM dbo.analytics_summary_stat),"
            "(SELECT COUNT_BIG(*) FROM dbo.analytics_dimension_stat),"
            "(SELECT COUNT_BIG(*) FROM dbo.analytics_facility_stat)"
        )
        summary_rows, dimension_rows, facility_rows = (int(value) for value in cursor.fetchone())
    finally:
        conn.close()
    return {
        "refreshed": True, "data_version": data_version, "summary_rows": summary_rows,
        "dimension_rows": dimension_rows, "facility_rows": facility_rows,
    }


def _batch_dimension_merge(name: str, expression: str, run_id: int) -> str:
    scope = _scope_expression()
    value = f"COALESCE(CONVERT(NVARCHAR(300),({expression})),N'{NULL_VALUE}')"
    return f"""
MERGE dbo.analytics_dimension_stat AS target
USING (
    SELECT {scope} AS scope_service_area,N'{name}' AS dimension_name,{value} AS dimension_value,
           COUNT_BIG(*) AS record_count,
           COALESCE(SUM(CONVERT(BIGINT,length_of_stay)),0) AS length_of_stay_sum,
           COUNT_BIG(length_of_stay) AS length_of_stay_count,
           COALESCE(SUM(CONVERT(DECIMAL(38,2),total_charges)),0) AS total_charges_sum,
           COUNT_BIG(total_charges) AS total_charges_count,
           COALESCE(SUM(CONVERT(DECIMAL(38,2),total_costs)),0) AS total_costs_sum,
           COUNT_BIG(total_costs) AS total_costs_count
    FROM {storage.TABLE_NAME} WHERE source_batch_id={int(run_id)}
    GROUP BY GROUPING SETS ((({expression})),(({registry.SERVICE_AREA_SQL}),({expression})))
) AS source
ON target.scope_service_area=source.scope_service_area
AND target.dimension_name=source.dimension_name AND target.dimension_value=source.dimension_value
WHEN MATCHED THEN UPDATE SET
    record_count=target.record_count+source.record_count,
    length_of_stay_sum=target.length_of_stay_sum+source.length_of_stay_sum,
    length_of_stay_count=target.length_of_stay_count+source.length_of_stay_count,
    total_charges_sum=target.total_charges_sum+source.total_charges_sum,
    total_charges_count=target.total_charges_count+source.total_charges_count,
    total_costs_sum=target.total_costs_sum+source.total_costs_sum,
    total_costs_count=target.total_costs_count+source.total_costs_count,
    updated_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT
    (scope_service_area,dimension_name,dimension_value,record_count,length_of_stay_sum,length_of_stay_count,
     total_charges_sum,total_charges_count,total_costs_sum,total_costs_count)
VALUES
    (source.scope_service_area,source.dimension_name,source.dimension_value,source.record_count,
     source.length_of_stay_sum,source.length_of_stay_count,source.total_charges_sum,
     source.total_charges_count,source.total_costs_sum,source.total_costs_count);
"""


def batch_merge_sql(run_id: int) -> str:
    """返回可嵌入导入事务的本批次预汇总增量 SQL。"""
    scope = _scope_expression()
    dimensions = "\n".join(
        _batch_dimension_merge(name, column, run_id) for name, column in STAT_DIMENSIONS.items()
    )
    return f"""
IF EXISTS (
    SELECT 1 FROM dbo.system_state analytics CROSS JOIN dbo.system_state data_version
    CROSS JOIN dbo.system_state schema_version
    WHERE analytics.state_key=N'analytics_data_version' AND data_version.state_key=N'data_version'
      AND schema_version.state_key=N'analytics_schema_version' AND schema_version.int_value>=2
      AND analytics.int_value=data_version.int_value
)
BEGIN
MERGE dbo.analytics_summary_stat AS target
USING (
    SELECT {scope} AS scope_service_area,COUNT_BIG(*) AS discharges,
           COALESCE(SUM(CONVERT(BIGINT,length_of_stay)),0) AS length_of_stay_sum,
           COUNT_BIG(length_of_stay) AS length_of_stay_count,
           COALESCE(SUM(CONVERT(DECIMAL(38,2),total_charges)),0) AS total_charges_sum,
           COUNT_BIG(total_charges) AS total_charges_count
    FROM {storage.TABLE_NAME} WHERE source_batch_id={int(run_id)}
    GROUP BY GROUPING SETS ((),(({registry.SERVICE_AREA_SQL})))
) AS source ON target.scope_service_area=source.scope_service_area
WHEN MATCHED THEN UPDATE SET
    discharges=target.discharges+source.discharges,
    length_of_stay_sum=target.length_of_stay_sum+source.length_of_stay_sum,
    length_of_stay_count=target.length_of_stay_count+source.length_of_stay_count,
    total_charges_sum=target.total_charges_sum+source.total_charges_sum,
    total_charges_count=target.total_charges_count+source.total_charges_count,
    updated_at=SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT
    (scope_service_area,discharges,length_of_stay_sum,length_of_stay_count,total_charges_sum,total_charges_count)
VALUES
    (source.scope_service_area,source.discharges,source.length_of_stay_sum,source.length_of_stay_count,
     source.total_charges_sum,source.total_charges_count);

MERGE dbo.analytics_facility_stat AS target
USING (
    SELECT {scope} AS scope_service_area,facility_name
    FROM {storage.TABLE_NAME}
    WHERE source_batch_id={int(run_id)} AND facility_name IS NOT NULL
    GROUP BY GROUPING SETS ((facility_name),(({registry.SERVICE_AREA_SQL}),facility_name))
) AS source
ON target.scope_service_area=source.scope_service_area AND target.facility_name=source.facility_name
WHEN NOT MATCHED THEN INSERT(scope_service_area,facility_name)
VALUES(source.scope_service_area,source.facility_name);

{dimensions}
END;
"""


def advance_version(previous_version: int, new_version: int) -> None:
    """仅当统计表此前与业务版本一致时推进其水位。"""
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.system_state SET int_value=%s,updated_at=SYSUTCDATETIME() "
            "WHERE state_key=N'analytics_data_version' AND int_value=%s".replace("%s", storage.PARAM),
            (int(new_version), int(previous_version)),
        )
        conn.commit()
    finally:
        conn.close()


def scope_for(filters: dict | None) -> str | None:
    filters = filters or {}
    if set(filters) - {"service_area"}:
        return None
    return str(registry.normalize_filter_value("service_area", filters.get("service_area")) or ALL_SCOPE)
