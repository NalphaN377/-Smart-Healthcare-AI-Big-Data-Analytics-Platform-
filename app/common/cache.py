"""Redis 查询缓存。

Redis 只保存可重建的分析结果；SQL Server 始终是数据事实来源。
缓存键包含角色、查询参数和数据版本，避免权限串读与增量入库后的旧数据残留。
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Callable, TypeVar

from config import FEATURES, REDIS_CONFIG

logger = logging.getLogger(__name__)
T = TypeVar("T")

_client = None
_connection_attempted = False
_connection_lock = threading.Lock()


def _redis_client():
    global _client, _connection_attempted
    if not FEATURES.get("redis_cache"):
        return None
    if _client is not None:
        return _client
    # 并发请求和预热任务只允许一个线程完成首次握手，避免其他线程误降级到数据库。
    with _connection_lock:
        if _connection_attempted:
            return _client
        _connection_attempted = True
        try:
            import redis
            candidate = redis.Redis(
                host=REDIS_CONFIG["host"], port=REDIS_CONFIG["port"], db=REDIS_CONFIG["db"],
                password=REDIS_CONFIG["password"], decode_responses=True,
                socket_connect_timeout=REDIS_CONFIG["socket_timeout"],
                socket_timeout=REDIS_CONFIG["socket_timeout"],
            )
            candidate.ping()
            _client = candidate
        except Exception as exc:  # 缓存不可用时必须降级到数据库
            logger.warning("Redis 不可用，跳过缓存: %s", exc.__class__.__name__)
            _client = None
    return _client


def reset_client() -> None:
    """重置延迟连接状态，供配置切换和测试使用。"""
    global _client, _connection_attempted
    _client = None
    _connection_attempted = False


def _prefix() -> str:
    return REDIS_CONFIG["key_prefix"].rstrip(":")


def data_version() -> int:
    client = _redis_client()
    version_key = f"{_prefix()}:system:data_version"
    if client:
        try:
            cached = client.get(version_key)
            if cached is not None:
                return int(cached)
        except Exception:
            logger.exception("读取 Redis 数据版本失败")
    try:
        from app.data_layer import storage
        version = storage.get_data_version()
    except Exception:
        # 数据库不可用时不让缓存层掩盖原始业务错误；版本 0 只用于构造键。
        version = 0
    if client:
        try:
            client.set(version_key, version)
        except Exception:
            logger.exception("写入 Redis 数据版本失败")
    return version


def _cache_key(namespace: str, payload: dict, version: int) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_prefix()}:cache:v{version}:{namespace}:{digest}"


def remember(
    namespace: str,
    payload: dict,
    producer: Callable[[], T],
    *,
    ttl: int | None = None,
) -> tuple[T, bool]:
    """读取Cache-Aside缓存；返回 ``(结果, 是否命中)``。"""
    client = _redis_client()
    if not client:
        return producer(), False
    key = _cache_key(namespace, payload, data_version())
    try:
        cached = client.get(key)
        if cached is not None:
            return json.loads(cached), True
    except Exception:
        logger.exception("读取 Redis 查询缓存失败")
        return producer(), False

    value = producer()
    try:
        client.setex(
            key,
            int(ttl or REDIS_CONFIG["default_ttl"]),
            json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str),
        )
    except Exception:
        logger.exception("写入 Redis 查询缓存失败")
    return value, False


def publish_data_version(version: int) -> None:
    """增量导入完成后发布新版本；旧键依靠TTL自动淘汰。"""
    client = _redis_client()
    if not client:
        return
    try:
        client.set(f"{_prefix()}:system:data_version", int(version))
    except Exception:
        logger.exception("发布 Redis 数据版本失败")


def health() -> dict:
    client = _redis_client()
    if not FEATURES.get("redis_cache"):
        return {"enabled": False, "connected": False, "db": REDIS_CONFIG["db"], "key_prefix": _prefix()}
    if not client:
        return {"enabled": True, "connected": False, "db": REDIS_CONFIG["db"], "key_prefix": _prefix()}
    try:
        return {
            "enabled": True, "connected": bool(client.ping()), "db": REDIS_CONFIG["db"],
            "key_prefix": _prefix(), "data_version": data_version(),
        }
    except Exception:
        return {"enabled": True, "connected": False, "db": REDIS_CONFIG["db"], "key_prefix": _prefix()}
