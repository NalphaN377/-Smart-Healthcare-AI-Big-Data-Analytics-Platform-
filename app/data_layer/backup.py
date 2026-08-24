"""SQL Server原生备份、校验和隔离恢复。"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from app.data_layer import storage
from app.data_layer.sql_tasks import run_long_sql
from config import BACKUP_DIR, DB_CONFIG

TARGET_DATABASE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")


def _run_long_sql(sql: str, *, database: str = "master") -> None:
    """兼容原有内部调用；具体执行器由通用长任务模块提供。"""
    run_long_sql(sql, database=database)


def _identifier(value: str) -> str:
    return "[" + value.replace("]", "]]" ) + "]"


def _literal(value: str | Path) -> str:
    return "N'" + str(value).replace("'", "''") + "'"


def validate_target_database(target_database: str) -> str:
    target = str(target_database or "").strip()
    if not TARGET_DATABASE_RE.fullmatch(target):
        raise ValueError("恢复目标数据库名只能包含字母、数字和下划线，且必须以字母开头")
    if target.casefold() == DB_CONFIG["database"].casefold():
        raise ValueError("禁止覆盖当前业务数据库，请使用新的恢复验证数据库名")
    return target


def default_backup_path() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (BACKUP_DIR / f"{DB_CONFIG['database']}_full_{timestamp}.bak").resolve()


def _record_started(path: Path) -> int:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.backup_job(backup_path,backup_type,status) OUTPUT INSERTED.id "
            f"VALUES ({storage.PARAM},{storage.PARAM},{storage.PARAM})",
            (str(path), "full", "running"),
        )
        job_id = int(cursor.fetchone()[0])
        conn.commit()
        return job_id
    finally:
        conn.close()


def _record_finished(job_id: int, path: Path, *, verified: bool, error: str | None = None) -> None:
    conn = storage.get_connection()
    try:
        conn.cursor().execute(
            "UPDATE dbo.backup_job SET status=%s,size_bytes=%s,checksum_verified=%s,"
            "finished_at=SYSUTCDATETIME(),error_message=%s WHERE id=%s".replace("%s", storage.PARAM),
            (
                "failed" if error else "completed", path.stat().st_size if path.exists() else None,
                1 if verified else 0, (error or "")[:2000] or None, job_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def verify_backup(path: str | Path) -> dict:
    backup_path = Path(path).resolve()
    if not backup_path.is_file():
        raise FileNotFoundError(f"备份文件不存在: {backup_path}")
    conn = storage.get_connection(autocommit=True)
    try:
        cursor = conn.cursor()
        cursor.execute(f"RESTORE VERIFYONLY FROM DISK={_literal(backup_path)} WITH CHECKSUM")
        # pymssql可能返回多个无行结果集；执行成功即表示VERIFYONLY通过。
        while cursor.nextset():
            pass
        return {"path": str(backup_path), "size_bytes": backup_path.stat().st_size, "verified": True}
    finally:
        conn.close()


def create_full_backup(path: str | Path | None = None) -> dict:
    backup_path = Path(path).resolve() if path else default_backup_path()
    backup_root = BACKUP_DIR.resolve()
    if backup_root not in backup_path.parents:
        raise ValueError(f"备份文件必须位于项目备份目录: {backup_root}")
    if backup_path.suffix.lower() != ".bak":
        raise ValueError("备份文件扩展名必须为.bak")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    storage.init_schema()
    job_id = _record_started(backup_path)
    try:
        sql = (
            f"BACKUP DATABASE {_identifier(DB_CONFIG['database'])} TO DISK={_literal(backup_path)} "
            "WITH COPY_ONLY,COMPRESSION,CHECKSUM,INIT,STATS=10"
        )
        _run_long_sql(sql)
        verification = verify_backup(backup_path)
        _record_finished(job_id, backup_path, verified=True)
        return {"job_id": job_id, **verification, "database": DB_CONFIG["database"], "type": "full_copy_only"}
    except Exception as exc:
        _record_finished(job_id, backup_path, verified=False, error=str(exc))
        raise


def list_backups(limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 100:
        raise ValueError("limit必须在1到100之间")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT TOP {int(limit)} id,backup_path,backup_type,status,size_bytes,checksum_verified,"
            "started_at,finished_at,error_message FROM dbo.backup_job ORDER BY id DESC"
        )
        keys = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            item = dict(zip(keys, row))
            for key in ("started_at", "finished_at"):
                if item.get(key):
                    item[key] = item[key].isoformat()
            item["file_exists"] = Path(item["backup_path"]).is_file()
            results.append(item)
        return results
    finally:
        conn.close()


def restore_to_new_database(path: str | Path, target_database: str, confirmation: str) -> dict:
    target = validate_target_database(target_database)
    if confirmation != f"RESTORE:{target}":
        raise ValueError(f"确认字符串必须为 RESTORE:{target}")
    backup_path = Path(path).resolve()
    verify_backup(backup_path)

    conn = storage.get_connection(autocommit=True)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DB_ID(%s)".replace("%s", storage.PARAM), (target,))
        if cursor.fetchone()[0] is not None:
            raise ValueError(f"目标数据库已存在: {target}")

        cursor.execute(f"RESTORE FILELISTONLY FROM DISK={_literal(backup_path)}")
        files = cursor.fetchall()
        if not files:
            raise RuntimeError("备份文件不包含可恢复的数据文件")
        cursor.execute(
            "SELECT CONVERT(NVARCHAR(4000),SERVERPROPERTY('InstanceDefaultDataPath'))," 
            "CONVERT(NVARCHAR(4000),SERVERPROPERTY('InstanceDefaultLogPath'))"
        )
        default_data, default_log = cursor.fetchone()
        if not default_data or not default_log:
            raise RuntimeError("无法获取SQL Server默认数据目录")

        moves = []
        data_index = log_index = 0
        restored_files = []
        for row in files:
            logical_name, file_type = str(row[0]), str(row[2])
            if file_type == "L":
                log_index += 1
                filename = f"{target}_log{'' if log_index == 1 else log_index}.ldf"
                destination = Path(str(default_log)) / filename
            else:
                data_index += 1
                extension = ".mdf" if data_index == 1 else ".ndf"
                filename = f"{target}{'' if data_index == 1 else '_' + str(data_index)}{extension}"
                destination = Path(str(default_data)) / filename
            moves.append(f"MOVE {_literal(logical_name)} TO {_literal(destination)}")
            restored_files.append(str(destination))

        sql = (
            f"RESTORE DATABASE {_identifier(target)} FROM DISK={_literal(backup_path)} WITH "
            + ",".join(moves)
            + ",RECOVERY,STATS=10"
        )
        _run_long_sql(sql)
        cursor.execute(f"SELECT COUNT_BIG(1) FROM {_identifier(target)}.dbo.inpatient_discharge")
        row_count = int(cursor.fetchone()[0])
        return {
            "source_backup": str(backup_path), "target_database": target,
            "row_count": row_count, "files": restored_files, "restored": True,
        }
    finally:
        conn.close()
