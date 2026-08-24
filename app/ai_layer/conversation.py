"""SQL Server 持久化多轮对话，按登录用户强制隔离。"""
from __future__ import annotations

import json
import re
import uuid

from app.data_layer import storage

PUBLIC_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def _row(cursor, row) -> dict | None:
    if not row:
        return None
    result = dict(zip([column[0] for column in cursor.description], row))
    for key in ("created_at", "updated_at"):
        if result.get(key):
            result[key] = result[key].isoformat()
    return result


def create(user_id: int, first_query: str) -> dict:
    public_id = str(uuid.uuid4())
    title = " ".join(str(first_query).split())[:100] or "新对话"
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.ai_conversation(public_id,user_id,title) "
            "OUTPUT INSERTED.id,INSERTED.public_id,INSERTED.title,INSERTED.status,"
            "INSERTED.created_at,INSERTED.updated_at "
            f"VALUES ({storage.PARAM},{storage.PARAM},{storage.PARAM})",
            (public_id, int(user_id), title),
        )
        result = _row(cursor, cursor.fetchone())
        conn.commit()
        return result
    finally:
        conn.close()


def get(user_id: int, public_id: str, *, include_archived: bool = False) -> dict | None:
    value = str(public_id or "").strip()
    if not PUBLIC_ID_RE.fullmatch(value):
        raise ValueError("conversation_id 格式不合法")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        status_sql = "" if include_archived else " AND status='active'"
        cursor.execute(
            "SELECT id,public_id,title,status,last_intent_json,state_json,created_at,updated_at "
            f"FROM dbo.ai_conversation WHERE public_id={storage.PARAM} AND user_id={storage.PARAM}{status_sql}",
            (value, int(user_id)),
        )
        result = _row(cursor, cursor.fetchone())
        if result:
            for source, target in (("last_intent_json", "last_intent"), ("state_json", "state")):
                raw = result.pop(source, None)
                result[target] = json.loads(raw) if raw else None
        return result
    finally:
        conn.close()


def resolve(user_id: int, public_id: str | None, first_query: str) -> dict:
    if not public_id:
        return create(user_id, first_query)
    conversation = get(user_id, public_id)
    if not conversation:
        raise LookupError("对话不存在或无权访问")
    return conversation


def history(user_id: int, public_id: str, limit: int = 12) -> list[dict]:
    conversation = get(user_id, public_id)
    if not conversation:
        raise LookupError("对话不存在或无权访问")
    limit = max(1, min(int(limit), 50))
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT role,content FROM (SELECT TOP {limit} id,role,content "
            f"FROM dbo.ai_conversation_message WHERE conversation_id={storage.PARAM} ORDER BY id DESC) recent "
            "ORDER BY id ASC",
            (conversation["id"],),
        )
        return [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    finally:
        conn.close()


def append_message(
    user_id: int,
    public_id: str,
    role: str,
    content: str,
    *,
    request_id: str | None = None,
    payload: dict | None = None,
) -> int:
    if role not in {"user", "assistant"}:
        raise ValueError("消息角色不合法")
    conversation = get(user_id, public_id)
    if not conversation:
        raise LookupError("对话不存在或无权访问")
    text = str(content or "").strip()
    if not text:
        raise ValueError("消息内容不能为空")
    serialized = json.dumps(payload, ensure_ascii=False, default=str) if payload else None
    intent = (payload or {}).get("intent") if role == "assistant" else None
    state = {
        "last_dimension": intent.get("dimension"),
        "last_metrics": intent.get("metrics"),
        "last_filters": intent.get("filters"),
    } if isinstance(intent, dict) else None
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.ai_conversation_message(conversation_id,role,content,request_id,payload_json) "
            f"OUTPUT INSERTED.id VALUES ({','.join([storage.PARAM] * 5)})",
            (conversation["id"], role, text[:20_000], (request_id or "")[:64] or None, serialized),
        )
        message_id = int(cursor.fetchone()[0])
        cursor.execute(
            f"UPDATE dbo.ai_conversation SET updated_at=SYSUTCDATETIME(),last_intent_json={storage.PARAM},"
            f"state_json={storage.PARAM} WHERE id={storage.PARAM}",
            (
                json.dumps(intent, ensure_ascii=False) if intent else conversation.get("last_intent") and json.dumps(conversation["last_intent"], ensure_ascii=False),
                json.dumps(state, ensure_ascii=False) if state else conversation.get("state") and json.dumps(conversation["state"], ensure_ascii=False),
                conversation["id"],
            ),
        )
        conn.commit()
        return message_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_for_user(user_id: int, limit: int = 30) -> list[dict]:
    if not 1 <= int(limit) <= 100:
        raise ValueError("limit 必须在 1 到 100 之间")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT TOP {int(limit)} c.public_id,c.title,c.status,c.created_at,c.updated_at,COUNT_BIG(m.id) AS message_count "
            "FROM dbo.ai_conversation c LEFT JOIN dbo.ai_conversation_message m ON m.conversation_id=c.id "
            f"WHERE c.user_id={storage.PARAM} AND c.status='active' "
            "GROUP BY c.id,c.public_id,c.title,c.status,c.created_at,c.updated_at ORDER BY c.updated_at DESC",
            (int(user_id),),
        )
        results = []
        for raw in cursor.fetchall():
            item = dict(zip([column[0] for column in cursor.description], raw))
            for key in ("created_at", "updated_at"):
                item[key] = item[key].isoformat()
            results.append(item)
        return results
    finally:
        conn.close()


def detail(user_id: int, public_id: str) -> dict:
    conversation = get(user_id, public_id, include_archived=True)
    if not conversation:
        raise LookupError("对话不存在或无权访问")
    conversation["messages"] = history(user_id, public_id, 50) if conversation["status"] == "active" else []
    return conversation


def archive(user_id: int, public_id: str) -> None:
    conversation = get(user_id, public_id)
    if not conversation:
        raise LookupError("对话不存在或无权访问")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.ai_conversation SET status='archived',updated_at=SYSUTCDATETIME() "
            f"WHERE id={storage.PARAM} AND user_id={storage.PARAM}",
            (conversation["id"], int(user_id)),
        )
        conn.commit()
    finally:
        conn.close()
