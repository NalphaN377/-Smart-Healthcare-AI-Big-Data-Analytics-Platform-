"""用户通知服务。

目前只保存“公开报告已发布”通知；每条通知归属于一个用户，
查询和已读操作都强制带入 user_id，防止跨账户访问。
"""
from __future__ import annotations

from app.data_layer import storage


def enqueue_report_published(cursor, report_id: int, report_title: str) -> int:
    """在报告发布事务内，为现有的活跃患者和医生创建幂等通知。"""
    title = f"新的公开报告：{str(report_title or '')[:130]}"
    message = f"管理员已发布《{str(report_title or '')[:100]}》，点击查看报告详情。"
    cursor.execute(
        "INSERT INTO dbo.user_notification(user_id,notification_type,title,message,report_id) "
        "SELECT u.id,N'report_published',"
        f"{storage.PARAM},{storage.PARAM},{storage.PARAM} FROM dbo.users u "
        "WHERE u.role IN (N'patient',N'doctor') AND u.is_active=1 AND u.deleted_at IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM dbo.user_notification n WHERE n.user_id=u.id "
        f"AND n.notification_type=N'report_published' AND n.report_id={storage.PARAM})",
        (title, message, int(report_id), int(report_id)),
    )
    return max(int(cursor.rowcount or 0), 0)


def list_for_user(user_id: int, limit: int = 50) -> dict:
    limit = max(1, min(int(limit), 100))
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT TOP {limit} id,notification_type,title,message,report_id,is_read,read_at,created_at "
            f"FROM dbo.user_notification WHERE user_id={storage.PARAM} ORDER BY created_at DESC,id DESC",
            (int(user_id),),
        )
        columns = [column[0] for column in cursor.description]
        items = []
        for row in cursor.fetchall():
            item = dict(zip(columns, row))
            item["id"] = int(item["id"])
            item["report_id"] = int(item["report_id"])
            item["is_read"] = bool(item["is_read"])
            for key in ("read_at", "created_at"):
                if item.get(key):
                    item[key] = item[key].isoformat()
            items.append(item)
        cursor.execute(
            f"SELECT COUNT_BIG(1) FROM dbo.user_notification WHERE user_id={storage.PARAM} AND is_read=0",
            (int(user_id),),
        )
        unread_count = int(cursor.fetchone()[0])
        return {"items": items, "unread_count": unread_count}
    finally:
        conn.close()


def mark_read(user_id: int, notification_id: int) -> bool:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.user_notification SET is_read=1,"
            "read_at=CASE WHEN read_at IS NULL THEN SYSUTCDATETIME() ELSE read_at END "
            f"WHERE id={storage.PARAM} AND user_id={storage.PARAM}",
            (int(notification_id), int(user_id)),
        )
        found = cursor.rowcount > 0
        if found:
            conn.commit()
        else:
            conn.rollback()
        return found
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_all_read(user_id: int) -> int:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dbo.user_notification SET is_read=1,read_at=SYSUTCDATETIME() "
            f"WHERE user_id={storage.PARAM} AND is_read=0",
            (int(user_id),),
        )
        changed = max(int(cursor.rowcount or 0), 0)
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
