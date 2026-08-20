"""SQL Server 原生快速全量导入。

保留 ``scripts/ingest.py`` 作为 Pandas 分块标准链路；本脚本用于百万级本地 CSV，
通过 BULK INSERT + SQL 清洗显著缩短首次装载时间。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.data_layer import storage  # noqa: E402
from config import DB_CONFIG, SOURCE_DATA_PATH  # noqa: E402


FINAL_COLUMNS = storage.SQL_COLUMNS

TEXT_EXPRESSIONS = {
    name: f"NULLIF(LTRIM(RTRIM([{name}])), '')"
    for name in FINAL_COLUMNS
    if name not in {"length_of_stay", "discharge_year", "apr_severity_of_illness_code", "birth_weight", "total_charges", "total_costs"}
}
TEXT_EXPRESSIONS.update({
    "length_of_stay": "CASE WHEN TRY_CONVERT(INT, REPLACE([length_of_stay], ' +', '')) >= 0 THEN TRY_CONVERT(INT, REPLACE([length_of_stay], ' +', '')) END",
    "discharge_year": "TRY_CONVERT(SMALLINT, [discharge_year])",
    "apr_severity_of_illness_code": "TRY_CONVERT(TINYINT, [apr_severity_of_illness_code])",
    "birth_weight": "CASE WHEN [type_of_admission] = 'Newborn' THEN NULLIF(LTRIM(RTRIM([birth_weight])), '') END",
    "total_charges": "CASE WHEN TRY_CONVERT(DECIMAL(14,2), REPLACE(REPLACE([total_charges], ',', ''), '$', '')) >= 0 THEN TRY_CONVERT(DECIMAL(14,2), REPLACE(REPLACE([total_charges], ',', ''), '$', '')) END",
    "total_costs": "CASE WHEN TRY_CONVERT(DECIMAL(14,2), REPLACE(REPLACE(REPLACE([total_costs], CHAR(13), ''), ',', ''), '$', '')) >= 0 THEN TRY_CONVERT(DECIMAL(14,2), REPLACE(REPLACE(REPLACE([total_costs], CHAR(13), ''), ',', ''), '$', '')) END",
})


def _run_dotnet_sql(sql: str) -> None:
    """通过 .NET SqlClient 执行不限时长的 SQL，规避部分机器的 ODBC TLS 问题。"""
    encoded = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    env = os.environ.copy()
    env.update({
        "SHCP_SQL_B64": encoded,
        "SHCP_DB_SERVER": f"{DB_CONFIG['host']},{DB_CONFIG['port']}",
        "SHCP_DB_NAME": DB_CONFIG["database"],
        "SHCP_DB_USER": DB_CONFIG["user"],
        "SHCP_DB_PASSWORD": DB_CONFIG["password"],
    })
    ps_script = (
        "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Data; "
        "$sql=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:SHCP_SQL_B64)); "
        "$cs=\"Server=$env:SHCP_DB_SERVER;Database=$env:SHCP_DB_NAME;User ID=$env:SHCP_DB_USER;"
        "Password=$env:SHCP_DB_PASSWORD;Encrypt=False;TrustServerCertificate=True;Connection Timeout=15\"; "
        "$conn=New-Object System.Data.SqlClient.SqlConnection $cs; "
        "try{$conn.Open();$cmd=$conn.CreateCommand();$cmd.CommandTimeout=0;$cmd.CommandText=$sql;"
        "[void]$cmd.ExecuteNonQuery()}finally{$conn.Close()}"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or "SQL Server bulk command failed").strip())


def bulk_ingest(filepath: str | Path, *, truncate: bool = False) -> dict:
    path = Path(filepath).resolve()
    if not path.exists() or path.suffix.lower() != ".csv":
        raise ValueError(f"必须提供存在的 CSV 文件: {path}")
    storage.init_schema()
    if not truncate:
        conn = storage.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT_BIG(*) FROM dbo.inpatient_discharge")
            existing_rows = int(cursor.fetchone()[0])
        finally:
            conn.close()
        if existing_rows:
            raise ValueError(
                f"目标表已有 {existing_rows:,} 行。为防止重复导入，重新全量装载时请显式传入 --truncate"
            )
    run_id = storage.start_ingestion(str(path), path.stat().st_size)
    started = time.perf_counter()
    try:
        escaped_path = str(path).replace("'", "''")
        truncate_sql = "TRUNCATE TABLE dbo.inpatient_discharge;" if truncate else ""
        columns_sql = ", ".join(f"[{name}]" for name in FINAL_COLUMNS)
        expressions_sql = ", ".join(f"{TEXT_EXPRESSIONS[name]} AS [{name}]" for name in FINAL_COLUMNS)
        bulk_sql = (
            "SET NOCOUNT ON; TRUNCATE TABLE dbo.inpatient_discharge_stage; " + truncate_sql +
            " BULK INSERT dbo.inpatient_discharge_stage "
            f"FROM '{escaped_path}' WITH (FORMAT='CSV', FIRSTROW=2, FIELDQUOTE='\"', "
            "ROWTERMINATOR='0x0a', CODEPAGE='65001', TABLOCK, BATCHSIZE=50000, MAXERRORS=100); "
            f"INSERT INTO dbo.inpatient_discharge ({columns_sql}) "
            f"SELECT DISTINCT {expressions_sql} FROM dbo.inpatient_discharge_stage;"
        )
        _run_dotnet_sql(bulk_sql)

        conn = storage.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT_BIG(*) FROM dbo.inpatient_discharge_stage")
        rows_read = int(cursor.fetchone()[0])
        cursor.execute("SELECT COUNT_BIG(*) FROM dbo.inpatient_discharge")
        rows_inserted = int(cursor.fetchone()[0])
        rows_dropped = max(0, rows_read - rows_inserted) if truncate else 0

        cursor.execute(
            "SELECT "
            "AVG(CASE WHEN facility_name IS NOT NULL AND age_group IS NOT NULL AND discharge_year IS NOT NULL "
            "AND ccsr_diagnosis_description IS NOT NULL AND payment_typology_1 IS NOT NULL THEN 1.0 ELSE 0.0 END), "
            "AVG(CASE WHEN length_of_stay >= 0 AND total_charges >= 0 AND total_costs >= 0 THEN 1.0 ELSE 0.0 END), "
            "AVG(CASE WHEN gender IN ('M','F','U') AND emergency_department_indicator IN ('Y','N') THEN 1.0 ELSE 0.0 END), "
            "AVG(CASE WHEN discharge_year BETWEEN 2000 AND YEAR(GETDATE()) THEN 1.0 ELSE 0.0 END) "
            "FROM dbo.inpatient_discharge"
        )
        scores = cursor.fetchone()
        quality = {
            "completeness": round(float(scores[0] or 0), 4), "accuracy": round(float(scores[1] or 0), 4),
            "consistency": round(float(scores[2] or 0), 4), "timeliness": round(float(scores[3] or 0), 4),
            "uniqueness": round(1 - rows_dropped / rows_read, 4) if rows_read else 0, "sample_size": rows_read,
        }
        quality["overall"] = round(sum(quality[key] for key in ("completeness", "accuracy", "consistency", "timeliness")) / 4, 4)
        result = {
            "engine": "sqlserver_bulk", "rows_read": rows_read, "rows_inserted": rows_inserted,
            "rows_dropped": rows_dropped, "elapsed_seconds": round(time.perf_counter() - started, 2),
            "quality": quality, "source_file": str(path),
        }
        storage.update_ingestion(run_id, chunks=1, rows_read=rows_read, rows_inserted=rows_inserted, rows_dropped=rows_dropped)
        storage.finish_ingestion(run_id, status="completed", quality=quality)
        conn.close()
        return result
    except Exception as exc:
        storage.finish_ingestion(run_id, status="failed", error=str(exc))
        raise


def main():
    parser = argparse.ArgumentParser(description="SQL Server BULK INSERT 快速全量导入")
    parser.add_argument("--file", default=str(SOURCE_DATA_PATH))
    parser.add_argument("--truncate", action="store_true", help="导入前清空目标业务表")
    args = parser.parse_args()
    print(json.dumps(bulk_ingest(args.file, truncate=args.truncate), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
