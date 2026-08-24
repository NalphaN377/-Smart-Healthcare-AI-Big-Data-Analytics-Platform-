"""Create the first administrator after the database schema is initialized."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from werkzeug.security import generate_password_hash

from app.auth.service import validate_password
from app.data_layer import storage


def main():
    parser = argparse.ArgumentParser(description="创建智慧医疗平台初始管理员")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--display-name", default="系统管理员")
    args = parser.parse_args()
    password = getpass.getpass("请输入初始密码（至少10位，包含字母和数字）: ")
    validate_password(password)
    normalized = args.username.strip().lower()
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.users(username,username_normalized,password_hash,display_name,role,must_change_password) "
            f"VALUES ({','.join([storage.PARAM] * 6)})",
            (args.username.strip(), normalized, generate_password_hash(password), args.display_name[:100], "admin", True),
        )
        conn.commit()
        print(f"管理员 {args.username} 已创建，首次登录后必须修改密码。")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
