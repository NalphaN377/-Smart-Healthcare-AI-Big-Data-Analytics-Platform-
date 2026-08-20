"""统一 API 响应与耗时统计。"""
from __future__ import annotations

import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)


def success(data=None, message="success", meta=None):
    return {"code": 0, "message": message, "data": data, "meta": meta or {}}


def fail(message="error", code=1, meta=None):
    return {"code": code, "message": message, "data": None, "meta": meta or {}}


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
            try:
                result = func(*args, **kwargs)
            except ValueError as exc:
                return fail(str(exc), code=400, meta={"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}), 400
            except Exception as exc:  # noqa: BLE001
                logger.exception("API %s 执行失败", func.__name__)
                return fail("服务暂时不可用，请稍后重试", code=500, meta={"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}), 500
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            if isinstance(result, tuple):
                return (_with_elapsed(result[0], elapsed), *result[1:])
            return _with_elapsed(result, elapsed)
        return wrapper
    return decorator
