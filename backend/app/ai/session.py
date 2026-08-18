from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from typing import Protocol
from uuid import uuid4

from .schemas import ConversationTurn


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
