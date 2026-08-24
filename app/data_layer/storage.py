"""SQL Server 持久化层。

一期负责建表、批量写入与查询连接；增量、备份和分布式写入保留稳定接口供二期实现。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from config import BATCH_SIZE, DB_CONFIG

logger = logging.getLogger(__name__)

TABLE_NAME = "dbo.inpatient_discharge"
PARAM = "%s" if DB_CONFIG.get("backend") == "pymssql" else "?"

COLUMN_MAPPING = {
    "Hospital Service Area": "hospital_service_area",
    "Hospital County": "hospital_county",
    "Operating Certificate Number": "operating_certificate_number",
    "Permanent Facility Id": "permanent_facility_id",
    "Facility Name": "facility_name",
    "Age Group": "age_group",
    "Zip Code - 3 digits": "zip_code_3",
    "Gender": "gender",
    "Race": "race",
    "Ethnicity": "ethnicity",
    "Length of Stay": "length_of_stay",
    "Type of Admission": "type_of_admission",
    "Patient Disposition": "patient_disposition",
    "Discharge Year": "discharge_year",
    "CCSR Diagnosis Code": "ccsr_diagnosis_code",
    "CCSR Diagnosis Description": "ccsr_diagnosis_description",
    "CCSR Procedure Code": "ccsr_procedure_code",
    "CCSR Procedure Description": "ccsr_procedure_description",
    "APR DRG Code": "apr_drg_code",
    "APR DRG Description": "apr_drg_description",
    "APR MDC Code": "apr_mdc_code",
    "APR MDC Description": "apr_mdc_description",
    "APR Severity of Illness Code": "apr_severity_of_illness_code",
    "APR Severity of Illness Description": "apr_severity_of_illness_desc",
    "APR Risk of Mortality": "apr_risk_of_mortality",
    "APR Medical Surgical Description": "apr_medical_surgical_desc",
    "Payment Typology 1": "payment_typology_1",
    "Payment Typology 2": "payment_typology_2",
    "Payment Typology 3": "payment_typology_3",
    "Birth Weight": "birth_weight",
    "Emergency Department Indicator": "emergency_department_indicator",
    "Total Charges": "total_charges",
    "Total Costs": "total_costs",
}
SQL_COLUMNS = list(COLUMN_MAPPING.values())


def build_connection_string(config: dict | None = None) -> str:
    cfg = config or DB_CONFIG
    trust = "yes" if cfg["trust_server_certificate"] else "no"
    return (
        f"DRIVER={{{cfg['driver']}}};"
        f"SERVER={cfg['host']},{cfg['port']};"
        f"DATABASE={cfg['database']};UID={cfg['user']};PWD={cfg['password']};"
        f"Encrypt={cfg['encrypt']};TrustServerCertificate={trust};"
        f"Connection Timeout={cfg['timeout']};"
    )


def get_connection(*, autocommit: bool = False, query_timeout: int | None = None):
    """创建 SQL Server 连接；默认 FreeTDS，允许通过环境变量切换 ODBC。"""
    if DB_CONFIG.get("backend") == "pymssql":
        try:
            import pymssql
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 pymssql，请执行 pip install -r requirements.txt") from exc
        return pymssql.connect(
            server=f"{DB_CONFIG['host']}:{DB_CONFIG['port']}",
            user=DB_CONFIG["user"], password=DB_CONFIG["password"], database=DB_CONFIG["database"],
            login_timeout=DB_CONFIG["timeout"],
            timeout=DB_CONFIG["query_timeout"] if query_timeout is None else int(query_timeout),
            autocommit=autocommit,
            charset="UTF-8",
        )
    try:
        import pyodbc
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("缺少 pyodbc，请执行 pip install -r requirements.txt") from exc
    connection = pyodbc.connect(build_connection_string(), autocommit=autocommit)
    if query_timeout is not None:
        connection.timeout = int(query_timeout)
    return connection


def ping() -> dict:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DB_NAME(), @@VERSION")
        row = cursor.fetchone()
        return {"database": row[0], "version": str(row[1]).splitlines()[0]}
    finally:
        conn.close()


def init_schema(schema_file: str | None = None) -> None:
    from config import BASE_DIR

    path = Path(schema_file or BASE_DIR / "sql" / "schema.sql")
    sql = path.read_text(encoding="utf-8-sig")
    batches = [part.strip() for part in re.split(r"^\s*GO\s*$", sql, flags=re.I | re.M) if part.strip()]
    conn = get_connection(query_timeout=300)
    try:
        cursor = conn.cursor()
        for batch in batches:
            cursor.execute(batch)
        conn.commit()
        logger.info("SQL Server Schema 初始化完成: %s", path)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            logger.warning("Schema 初始化失败后连接已不可用，无法回滚", exc_info=True)
        raise
    finally:
        conn.close()


def truncate_table() -> None:
    """显式清空业务表，仅供用户主动全量重导。"""
    conn = get_connection()
    try:
        conn.cursor().execute(f"TRUNCATE TABLE {TABLE_NAME}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _to_python(value):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def dataframe_records(df: pd.DataFrame) -> tuple[list[str], Iterable[tuple]]:
    renamed = df.rename(columns=COLUMN_MAPPING)
    columns = [name for name in SQL_COLUMNS if name in renamed.columns]
    if columns != SQL_COLUMNS:
        missing = [name for name in SQL_COLUMNS if name not in columns]
        raise ValueError(f"入库字段缺失: {missing}")
    values = renamed[columns].astype(object).where(pd.notnull(renamed[columns]), None)
    records = (tuple(_to_python(v) for v in row) for row in values.itertuples(index=False, name=None))
    return columns, records


def bulk_insert(df: pd.DataFrame, table: str = TABLE_NAME, batch_size: int = BATCH_SIZE) -> int:
    if df.empty:
        return 0
    columns, records_iter = dataframe_records(df)
    quoted = ", ".join(f"[{column}]" for column in columns)
    placeholders = ", ".join(PARAM for _ in columns)
    sql = f"INSERT INTO {table} ({quoted}) VALUES ({placeholders})"
    conn = get_connection()
    total = 0
    try:
        cursor = conn.cursor()
        if hasattr(cursor, "fast_executemany"):
            cursor.fast_executemany = True
        batch = []
        for record in records_iter:
            batch.append(record)
            if len(batch) >= batch_size:
                cursor.executemany(sql, batch)
                total += len(batch)
                batch.clear()
        if batch:
            cursor.executemany(sql, batch)
            total += len(batch)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    logger.info("SQL Server 批量入库完成: %d 条", total)
    return total


def start_ingestion(
    source_file: str,
    source_size: int | None,
    *,
    source_sha256: str | None = None,
    mode: str = "full",
    source_columns: list[str] | None = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.ingestion_run(source_file,source_size_bytes,source_sha256,ingestion_mode,"
            f"source_columns_json,status) OUTPUT INSERTED.id VALUES ({','.join([PARAM] * 6)})",
            (
                str(source_file), source_size, source_sha256, mode,
                json.dumps(source_columns, ensure_ascii=False) if source_columns else None, "running",
            ),
        )
        run_id = int(cursor.fetchone()[0])
        conn.commit()
        return run_id
    finally:
        conn.close()


def update_ingestion(run_id: int, *, chunks: int, rows_read: int, rows_inserted: int, rows_dropped: int) -> None:
    conn = get_connection()
    try:
        conn.cursor().execute(
            f"UPDATE dbo.ingestion_run SET chunks_processed={PARAM},rows_read={PARAM},rows_inserted={PARAM},rows_dropped={PARAM} WHERE id={PARAM}",
            (chunks, rows_read, rows_inserted, rows_dropped, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def finish_ingestion(run_id: int, *, status: str, quality: dict | None = None, error: str | None = None) -> None:
    conn = get_connection()
    try:
        conn.cursor().execute(
            f"UPDATE dbo.ingestion_run SET status={PARAM},finished_at=SYSUTCDATETIME(),quality_json={PARAM},error_message={PARAM} WHERE id={PARAM}",
            (status, json.dumps(quality, ensure_ascii=False) if quality else None, (error or "")[:2000] or None, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def latest_ingestion() -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 1 id,source_file,source_size_bytes,source_sha256,ingestion_mode,started_at,finished_at,status,"
            "chunks_processed,rows_read,rows_inserted,rows_dropped,rows_skipped,quality_json,error_message "
            "FROM dbo.ingestion_run ORDER BY id DESC"
        )
        row = cursor.fetchone()
        if not row:
            return None
        keys = [column[0] for column in cursor.description]
        result = dict(zip(keys, row))
        for key in ("started_at", "finished_at"):
            if result.get(key):
                result[key] = result[key].isoformat()
        if result.get("quality_json"):
            result["quality"] = json.loads(result.pop("quality_json"))
        return result
    finally:
        conn.close()


def get_ingestion(run_id: int) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id,source_file,source_size_bytes,source_sha256,ingestion_mode,started_at,finished_at,status,"
            "chunks_processed,rows_read,rows_inserted,rows_dropped,rows_skipped,quality_json,error_message "
            f"FROM dbo.ingestion_run WHERE id={PARAM}",
            (run_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(zip([column[0] for column in cursor.description], row))
        for key in ("started_at", "finished_at"):
            if result.get(key):
                result[key] = result[key].isoformat()
        if result.get("quality_json"):
            result["quality"] = json.loads(result.pop("quality_json"))
        return result
    finally:
        conn.close()


def completed_ingestion_by_hash(source_sha256: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT TOP 1 id,source_file,finished_at,rows_read,rows_inserted,rows_skipped "
            f"FROM dbo.ingestion_run WHERE source_sha256={PARAM} AND status='completed' ORDER BY id DESC",
            (source_sha256,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(zip([column[0] for column in cursor.description], row))
        if result.get("finished_at"):
            result["finished_at"] = result["finished_at"].isoformat()
        return result
    finally:
        conn.close()


def mark_stale_ingestions(older_than_minutes: int = 120) -> list[int]:
    """关闭异常中断后遗留的running批次，不触碰仍在合理窗口内的任务。"""
    if older_than_minutes < 30:
        raise ValueError("过期窗口不能小于30分钟")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.ingestion_run SET status='failed',finished_at=SYSUTCDATETIME(),"
            "error_message=COALESCE(error_message,N'任务异常中断，已由后续运行标记为过期') OUTPUT INSERTED.id "
            f"WHERE status='running' AND started_at<DATEADD(MINUTE,-{int(older_than_minutes)},SYSUTCDATETIME())"
        )
        stale_ids = [int(row[0]) for row in cursor.fetchall()]
        conn.commit()
        return stale_ids
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_data_version() -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT int_value FROM dbo.system_state WHERE state_key=N'data_version'")
        row = cursor.fetchone()
        return int(row[0]) if row else 1
    finally:
        conn.close()


def bump_data_version() -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.system_state SET int_value=ISNULL(int_value,0)+1,updated_at=SYSUTCDATETIME() "
            "OUTPUT INSERTED.int_value WHERE state_key=N'data_version'"
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO dbo.system_state(state_key,int_value) OUTPUT INSERTED.int_value VALUES (N'data_version',1)"
            )
            row = cursor.fetchone()
        conn.commit()
        return int(row[0])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def incremental_update(df: pd.DataFrame, *_, **__) -> int:
    """二期预留：后续以 source_row_hash + staging table 实现幂等 MERGE。"""
    raise NotImplementedError("增量更新已预留，二期将使用 source_row_hash 与 staging table 实现")


def backup(*_, **__) -> str:
    """二期预留：SQL Server BACKUP DATABASE / 对象存储归档。"""
    raise NotImplementedError("数据库备份恢复属于二期能力，当前仅保留接口")


def restore(*_, **__) -> int:
    raise NotImplementedError("数据库备份恢复属于二期能力，当前仅保留接口")
