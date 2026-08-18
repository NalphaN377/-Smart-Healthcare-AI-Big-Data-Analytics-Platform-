from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any


logger = logging.getLogger(__name__)


class RedisClient:
    """Small fault-tolerant Redis connection boundary without secret-bearing status data."""

    def __init__(self, config: Mapping[str, Any], client=None):
        self.enabled = bool(config.get("REDIS_ENABLED", False))
        self.host = str(config.get("REDIS_HOST", "127.0.0.1"))
        self.port = int(config.get("REDIS_PORT", 6379))
        self.db = int(config.get("REDIS_DB", 0))
        self._client = client
        self._connected = False
        if not self.enabled:
            return
        try:
            if self._client is None:
                from redis import Redis

                self._client = Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                    health_check_interval=30,
                )
            self._connected = bool(self._client.ping())
        except Exception as error:  # Redis is explicitly optional.
            logger.warning("Redis unavailable; continuing without it (%s)", error.__class__.__name__)
            self._connected = False

    @property
    def connected(self) -> bool:
        return self.enabled and self._connected and self._client is not None

    @property
    def client(self):
        if not self.connected:
            raise ConnectionError("Redis is unavailable")
        return self._client

    def mark_unavailable(self, error: Exception) -> None:
        self._connected = False
        logger.warning("Redis operation failed; using fallback (%s)", error.__class__.__name__)

    def status(self, ttl: int) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "backend": "redis" if self.connected else "none",
            "ttl": ttl,
        }
