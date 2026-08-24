"""统一 API 响应与耗时统计。"""
from __future__ import annotations

import logging
import time
import uuid
from functools import wraps

from flask import g, has_request_context

logger = logging.getLogger(__name__)


class APIError(Exception):
    """可安全返回给调用方的业务异常。"""

    def __init__(self, message: str, *, status_code: int = 400, code: int | None = None, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code if code is not None else status_code
        self.details = details


def request_id() -> str:
    """返回当前请求追踪号；非请求上下文也能安全调用。"""
    if not has_request_context():
        return uuid.uuid4().hex
    if not getattr(g, "request_id", None):
        g.request_id = uuid.uuid4().hex
    return g.request_id


def _meta(meta=None):
    result = dict(meta or {})
    result.setdefault("request_id", request_id())
    return result


def success(data=None, message="success", meta=None):
    return {"code": 0, "message": message, "data": data, "meta": _meta(meta)}


def fail(message="error", code=1, meta=None):
    return {"code": code, "message": message, "data": None, "meta": _meta(meta)}


def _with_elapsed(payload, elapsed_ms):
    if isinstance(payload, dict) and "code" in payload:
        payload.setdefault("meta", {})["elapsed_ms"] = elapsed_ms
    return payload


def timing():
    """为字典响应追加 meta.elapsed_ms，并保留 Flask 状态码元组。"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            if isinstance(result, tuple):
                return (_with_elapsed(result[0], elapsed), *result[1:])
            return _with_elapsed(result, elapsed)
        return wrapper
    return decorator
