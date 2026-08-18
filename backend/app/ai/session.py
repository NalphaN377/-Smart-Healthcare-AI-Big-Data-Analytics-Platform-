from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import json
import logging
from threading import RLock
from typing import Protocol
from uuid import uuid4

from .schemas import ConversationTurn


logger = logging.getLogger(__name__)


class ConversationStore(Protocol):
    def create_session(self) -> str: ...

    def history(self, session_id: str) -> list[ConversationTurn]: ...

    def append(self, session_id: str, turn: ConversationTurn) -> int: ...


class InMemoryConversationStore:
    """Thread-safe, bounded metadata store. It never stores full dataset rows."""

    def __init__(self, max_turns: int = 10, max_sessions: int = 500):
        if max_turns < 1 or max_sessions < 1:
            raise ValueError("session limits must be positive")
        self.max_turns = max_turns
        self.max_sessions = max_sessions
        self._sessions: OrderedDict[str, list[ConversationTurn]] = OrderedDict()
        self._lock = RLock()

    def create_session(self) -> str:
        with self._lock:
            while len(self._sessions) >= self.max_sessions:
                self._sessions.popitem(last=False)
            session_id = uuid4().hex
            self._sessions[session_id] = []
            return session_id

    def history(self, session_id: str) -> list[ConversationTurn]:
        with self._lock:
            turns = self._sessions.get(session_id)
            if turns is None:
                self._sessions[session_id] = []
                turns = self._sessions[session_id]
            self._sessions.move_to_end(session_id)
            return deepcopy(turns)

    def append(self, session_id: str, turn: ConversationTurn) -> int:
        with self._lock:
            turns = self._sessions.setdefault(session_id, [])
            turns.append(deepcopy(turn))
            del turns[: max(0, len(turns) - self.max_turns)]
            self._sessions.move_to_end(session_id)
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
            return len(turns)

    def replace(self, session_id: str, turns: list[ConversationTurn]) -> None:
        with self._lock:
            self._sessions[session_id] = deepcopy(turns[-self.max_turns :])
            self._sessions.move_to_end(session_id)
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)


class RedisConversationStore:
    """Redis JSON session store with a bounded in-process failover mirror."""

    KEY_PREFIX = "medical:ai:session"

    def __init__(
        self,
        redis_client,
        *,
        max_turns: int = 10,
        max_sessions: int = 500,
        ttl_seconds: int = 86400,
        fallback: InMemoryConversationStore | None = None,
    ):
        if max_turns < 1 or ttl_seconds < 1:
            raise ValueError("session limits and TTL must be positive")
        self.redis_client = redis_client
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.fallback = fallback or InMemoryConversationStore(max_turns, max_sessions)

    def create_session(self) -> str:
        session_id = uuid4().hex
        self.fallback.replace(session_id, [])
        if self.redis_client.connected:
            try:
                self.redis_client.client.setex(
                    self._key(session_id),
                    self.ttl_seconds,
                    "[]",
                )
            except Exception as error:
                self.redis_client.mark_unavailable(error)
        return session_id

    def history(self, session_id: str) -> list[ConversationTurn]:
        if not self.redis_client.connected:
            return self.fallback.history(session_id)
        try:
            payload = self.redis_client.client.get(self._key(session_id))
            if payload is None:
                turns: list[ConversationTurn] = []
                self.redis_client.client.setex(
                    self._key(session_id),
                    self.ttl_seconds,
                    "[]",
                )
            else:
                turns = [
                    ConversationTurn.model_validate(item)
                    for item in json.loads(payload)
                ][-self.max_turns :]
                self.redis_client.client.expire(self._key(session_id), self.ttl_seconds)
            self.fallback.replace(session_id, turns)
            return deepcopy(turns)
        except Exception as error:
            self.redis_client.mark_unavailable(error)
            return self.fallback.history(session_id)

    def append(self, session_id: str, turn: ConversationTurn) -> int:
        fallback_count = self.fallback.append(session_id, turn)
        if not self.redis_client.connected:
            return fallback_count
        try:
            payload = self.redis_client.client.get(self._key(session_id))
            raw_turns = json.loads(payload) if payload else []
            turns = [ConversationTurn.model_validate(item) for item in raw_turns]
            turns.append(deepcopy(turn))
            turns = turns[-self.max_turns :]
            serialized = json.dumps(
                [item.model_dump(mode="json") for item in turns],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            self.redis_client.client.setex(
                self._key(session_id),
                self.ttl_seconds,
                serialized,
            )
            self.fallback.replace(session_id, turns)
            return len(turns)
        except Exception as error:
            self.redis_client.mark_unavailable(error)
            logger.warning("AI session persistence failed; using memory fallback")
            return fallback_count

    @classmethod
    def _key(cls, session_id: str) -> str:
        return f"{cls.KEY_PREFIX}:{session_id}"
