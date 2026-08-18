from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor


def connect_from_config(config: Mapping[str, Any], with_database: bool = True) -> pymysql.Connection:
    options: dict[str, Any] = {
        "host": config["MYSQL_HOST"],
        "port": int(config["MYSQL_PORT"]),
        "user": config["MYSQL_USER"],
        "password": config.get("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "connect_timeout": int(config.get("MYSQL_CONNECT_TIMEOUT", 5)),
        "read_timeout": 30,
        "write_timeout": 30,
        "autocommit": False,
    }
    if with_database:
        options["database"] = config["MYSQL_DATABASE"]
    return pymysql.connect(**options)


@contextmanager
def database_connection(
    config: Mapping[str, Any], with_database: bool = True
) -> Iterator[pymysql.Connection]:
    connection = connect_from_config(config, with_database=with_database)
    try:
        yield connection
    finally:
        connection.close()

