"""SQL Server-backed user authentication and security auditing."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from app.auth.permissions import ROLE_PERMISSIONS, permissions_for
from app.data_layer import storage

PUBLIC_USER_FIELDS = "id,username,display_name,role,email,is_active,must_change_password,last_login_at,created_at,updated_at"


def _normalize_username(username: str) -> str:
    return str(username or "").strip().lower()


def _serialize(row: Any, columns: list[str]) -> dict | None:
    if not row:
        return None
    result = dict(zip(columns, row))
    for key, value in list(result.items()):
        if isinstance(value, datetime):
            result[key] = value.isoformat()
    if result.get("id") is not None:
        result["id"] = int(result["id"])
    if result.get("is_active") is not None:
        result["is_active"] = bool(result["is_active"])
    if result.get("must_change_password") is not None:
        result["must_change_password"] = bool(result["must_change_password"])
    if result.get("role"):
        result["permissions"] = permissions_for(result["role"])
    return result


def _fetch_one(sql: str, params=()) -> dict | None:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, tuple(params))
        return _serialize(cursor.fetchone(), [column[0] for column in cursor.description])
    finally:
        conn.close()


def get_user(user_id: int) -> dict | None:
    return _fetch_one(f"SELECT {PUBLIC_USER_FIELDS} FROM dbo.users WHERE id={storage.PARAM} AND deleted_at IS NULL", (user_id,))


def authenticate(username: str, password: str, *, ip_address: str = "", user_agent: str = "") -> tuple[dict | None, str]:
    normalized = _normalize_username(username)
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id,username,password_hash,display_name,role,email,is_active,failed_login_attempts,"
            "locked_until,must_change_password,last_login_at,created_at,updated_at "
            f"FROM dbo.users WHERE username_normalized={storage.PARAM}",
            (normalized,),
        )
        columns = [column[0] for column in cursor.description]
        raw = cursor.fetchone()
        user = _serialize(raw, columns)
        now = datetime.utcnow()
        if not user:
            _write_audit(cursor, None, normalized, "auth.login_failed", "unknown_user", ip_address, user_agent)
            conn.commit()
            return None, "用户名或密码错误"
        locked_until = raw[columns.index("locked_until")]
        if locked_until and locked_until > now:
            _write_audit(cursor, user["id"], user["username"], "auth.login_blocked", "locked", ip_address, user_agent)
            conn.commit()
            return None, "账号暂时锁定，请稍后再试"
        password_hash = raw[columns.index("password_hash")]
        if not user["is_active"] or not check_password_hash(password_hash, password or ""):
            attempts = int(user.get("failed_login_attempts") or 0) + 1
            lock_until = now + timedelta(minutes=15) if attempts >= 5 else None
            cursor.execute(
                f"UPDATE dbo.users SET failed_login_attempts={storage.PARAM},locked_until={storage.PARAM},updated_at=SYSUTCDATETIME() WHERE id={storage.PARAM}",
                (0 if lock_until else attempts, lock_until, user["id"]),
            )
            _write_audit(cursor, user["id"], user["username"], "auth.login_failed", "invalid_credentials", ip_address, user_agent)
            conn.commit()
            return None, "用户名或密码错误"
        cursor.execute(
            "UPDATE dbo.users SET failed_login_attempts=0,locked_until=NULL,last_login_at=SYSUTCDATETIME(),"
            f"updated_at=SYSUTCDATETIME() WHERE id={storage.PARAM}",
            (user["id"],),
        )
        _write_audit(cursor, user["id"], user["username"], "auth.login", "success", ip_address, user_agent)
        conn.commit()
        return get_user(user["id"]), "success"
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_users() -> list[dict]:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {PUBLIC_USER_FIELDS} FROM dbo.users WHERE deleted_at IS NULL ORDER BY id")
        columns = [column[0] for column in cursor.description]
        return [_serialize(row, columns) for row in cursor.fetchall()]
    finally:
        conn.close()


def create_user(data: dict, actor: dict) -> dict:
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    role = str(data.get("role") or "patient")
    if not 3 <= len(username) <= 50:
        raise ValueError("用户名长度必须在 3 到 50 个字符之间")
    validate_password(password)
    if role not in ROLE_PERMISSIONS:
        raise ValueError("用户角色不合法")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.users(username,username_normalized,password_hash,display_name,role,email,must_change_password,created_by) "
            f"OUTPUT INSERTED.id VALUES ({','.join([storage.PARAM] * 8)})",
            (username, _normalize_username(username), generate_password_hash(password), str(data.get("display_name") or username)[:100], role,
             str(data.get("email") or "")[:200] or None, bool(data.get("must_change_password", True)), actor["id"]),
        )
        user_id = int(cursor.fetchone()[0])
        _write_audit(cursor, actor["id"], actor["username"], "user.create", str(user_id), "", "")
        conn.commit()
        return get_user(user_id)
    except Exception as exc:
        conn.rollback()
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            raise ValueError("用户名已存在") from exc
        raise
    finally:
        conn.close()


def register_user(data: dict) -> dict:
    """Self-register a patient or doctor; administrators are never public registrations."""
    role = str(data.get("role") or "patient")
    if role not in {"patient", "doctor"}:
        raise ValueError("注册角色只能选择患者用户或医生用户")
    payload = {
        "username": data.get("username"),
        "password": data.get("password"),
        "display_name": data.get("display_name"),
        "email": data.get("email"),
        "role": role,
        "must_change_password": False,
    }
    return create_user(payload, {"id": None, "username": str(data.get("username") or "").strip()})


def update_user(user_id: int, data: dict, actor: dict) -> dict:
    user = get_user(user_id)
    if not user:
        raise LookupError("用户不存在")
    role = str(data.get("role", user["role"]))
    if role not in ROLE_PERMISSIONS:
        raise ValueError("用户角色不合法")
    is_active = bool(data.get("is_active", user["is_active"]))
    if user_id == actor["id"] and (not is_active or role != actor["role"]):
        raise ValueError("不能禁用自己的账号或修改自己的角色")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.users SET display_name={0},email={0},role={0},is_active={0},updated_at=SYSUTCDATETIME() WHERE id={0}".format(storage.PARAM),
            (str(data.get("display_name", user.get("display_name") or ""))[:100] or None,
             str(data.get("email", user.get("email") or ""))[:200] or None, role, is_active, user_id),
        )
        _write_audit(cursor, actor["id"], actor["username"], "user.update", str(user_id), "", "")
        conn.commit()
        return get_user(user_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def change_password(user_id: int, current_password: str, new_password: str, actor: dict) -> None:
    validate_password(new_password)
    account = _fetch_one(f"SELECT id,password_hash FROM dbo.users WHERE id={storage.PARAM}", (user_id,))
    if not account or not check_password_hash(account["password_hash"], current_password or ""):
        raise ValueError("当前密码错误")
    _set_password(user_id, new_password, actor, "auth.password_changed")


def reset_password(user_id: int, new_password: str, actor: dict) -> None:
    validate_password(new_password)
    if not get_user(user_id):
        raise LookupError("用户不存在")
    _set_password(user_id, new_password, actor, "user.password_reset")


def cancel_own_account(user: dict, password: str, *, ip_address: str = "", user_agent: str = "") -> None:
    if user.get("role") == "admin":
        raise ValueError("管理员账号不能自助注销")
    account = _fetch_one(f"SELECT id,password_hash FROM dbo.users WHERE id={storage.PARAM} AND deleted_at IS NULL", (user["id"],))
    if not account or not check_password_hash(account["password_hash"], password or ""):
        raise ValueError("当前密码错误")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE dbo.users SET is_active=0,deleted_at=SYSUTCDATETIME(),updated_at=SYSUTCDATETIME() WHERE id={storage.PARAM}",
            (user["id"],),
        )
        _write_audit(cursor, user["id"], user["username"], "account.cancel", "self", ip_address, user_agent)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_user(user_id: int, actor: dict, *, ip_address: str = "", user_agent: str = "") -> None:
    if user_id == actor["id"]:
        raise ValueError("管理员不能删除自己的账号")
    target = get_user(user_id)
    if not target:
        raise LookupError("用户不存在")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE dbo.users SET is_active=0,deleted_at=SYSUTCDATETIME(),updated_at=SYSUTCDATETIME() WHERE id={storage.PARAM}",
            (user_id,),
        )
        _write_audit(cursor, actor["id"], actor["username"], "user.delete", f"{user_id}:{target['username']}", ip_address, user_agent)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _set_password(user_id: int, password: str, actor: dict, action: str) -> None:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.users SET password_hash={0},must_change_password={0},password_changed_at=SYSUTCDATETIME(),"
            "failed_login_attempts=0,locked_until=NULL,updated_at=SYSUTCDATETIME() WHERE id={0}".format(storage.PARAM),
            (generate_password_hash(password), action == "user.password_reset", user_id),
        )
        _write_audit(cursor, actor["id"], actor["username"], action, str(user_id), "", "")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def validate_password(password: str) -> None:
    if len(password) < 10 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError("密码至少 10 位，且必须同时包含字母和数字")


def audit(user: dict | None, action: str, detail: str = "", *, ip_address: str = "", user_agent: str = "") -> None:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        _write_audit(cursor, (user or {}).get("id"), (user or {}).get("username", ""), action, detail, ip_address, user_agent)
        conn.commit()
    finally:
        conn.close()


def list_audit_logs(limit: int = 100) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT TOP {limit} id,user_id,username,action,detail,ip_address,created_at FROM dbo.security_audit ORDER BY id DESC")
        columns = [column[0] for column in cursor.description]
        return [_serialize(row, columns) for row in cursor.fetchall()]
    finally:
        conn.close()


def _write_audit(cursor, user_id, username, action, detail, ip_address, user_agent) -> None:
    cursor.execute(
        "INSERT INTO dbo.security_audit(user_id,username,action,detail,ip_address,user_agent) "
        f"VALUES ({','.join([storage.PARAM] * 6)})",
        (user_id, str(username or "")[:50] or None, action[:80], str(detail or "")[:1000] or None,
         str(ip_address or "")[:64] or None, str(user_agent or "")[:500] or None),
    )
