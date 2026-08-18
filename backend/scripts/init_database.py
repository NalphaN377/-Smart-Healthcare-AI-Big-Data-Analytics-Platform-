#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymysql


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Config  # noqa: E402
from backend.app.database import connect_from_config  # noqa: E402


def configuration() -> dict:
    return {
        key: getattr(Config, key)
        for key in (
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_CONNECT_TIMEOUT",
        )
    }


def ensure_database(config: dict) -> None:
    database = config["MYSQL_DATABASE"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise ValueError("MYSQL_DATABASE may contain only letters, numbers and underscores")
    try:
        connection = connect_from_config(config)
        connection.close()
        return
    except pymysql.err.OperationalError as exc:
        if exc.args[0] != 1049:
            raise
    connection = connect_from_config(config, with_database=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
        connection.commit()
    finally:
        connection.close()


def main() -> int:
    config = configuration()
    schema_path = PROJECT_ROOT / "backend" / "sql" / "schema.sql"
    ensure_database(config)
    statements = [statement.strip() for statement in schema_path.read_text(encoding="utf-8").split(";")]
    connection = connect_from_config(config)
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                if statement:
                    cursor.execute(statement)
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES LIKE 'hospital_discharges'")
            if cursor.fetchone() is None:
                raise RuntimeError("hospital_discharges table was not created")
    finally:
        connection.close()
    print(f"Database ready: {config['MYSQL_DATABASE']}")
    print("Table ready: hospital_discharges")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (pymysql.MySQLError, OSError, ValueError, RuntimeError) as exc:
        print(f"Database initialization failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
