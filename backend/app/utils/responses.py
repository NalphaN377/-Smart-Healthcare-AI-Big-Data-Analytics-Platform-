from __future__ import annotations

from decimal import Decimal
from typing import Any

from flask import jsonify


def to_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    return value


def success_response(data: Any, meta: dict[str, Any] | None = None, status: int = 200):
    return (
        jsonify(
            {
                "success": True,
                "data": to_json_value(data),
                "meta": to_json_value(meta or {}),
                "message": None,
            }
        ),
        status,
    )


def error_response(message: str, status: int, meta: dict[str, Any] | None = None):
    return jsonify({"success": False, "data": None, "meta": meta or {}, "message": message}), status

