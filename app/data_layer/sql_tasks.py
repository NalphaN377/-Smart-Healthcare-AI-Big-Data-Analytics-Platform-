"""执行不应受普通 Web 查询超时限制的受控 SQL Server 长任务。"""
from __future__ import annotations

import base64
import os
import subprocess

from config import DB_CONFIG


def run_long_sql(sql: str, *, database: str | None = None) -> None:
    """通过 .NET SqlClient 执行可信的内部 SQL，命令超时设为无限。"""
    encoded = base64.b64encode(sql.encode("utf-8")).decode("ascii")
    process_env = os.environ.copy()
    process_env.update({
        "SHCP_SQL_B64": encoded,
        "SHCP_DB_SERVER": f"{DB_CONFIG['host']},{DB_CONFIG['port']}",
        "SHCP_DB_NAME": database or DB_CONFIG["database"],
        "SHCP_DB_USER": DB_CONFIG["user"],
        "SHCP_DB_PASSWORD": DB_CONFIG["password"],
    })
    powershell = (
        "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Data; "
        "$sql=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:SHCP_SQL_B64)); "
        "$cs=\"Server=$env:SHCP_DB_SERVER;Database=$env:SHCP_DB_NAME;User ID=$env:SHCP_DB_USER;"
        "Password=$env:SHCP_DB_PASSWORD;Encrypt=False;TrustServerCertificate=True;Connection Timeout=15\"; "
        "$conn=New-Object System.Data.SqlClient.SqlConnection $cs; "
        "try{$conn.Open();$cmd=$conn.CreateCommand();$cmd.CommandTimeout=0;$cmd.CommandText=$sql;"
        "[void]$cmd.ExecuteNonQuery()}finally{$conn.Close()}"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", powershell],
        env=process_env, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or "SQL Server 长任务执行失败").strip())
