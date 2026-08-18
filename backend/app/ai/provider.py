from __future__ import annotations

from typing import Protocol


class AIQueryProvider(Protocol):
    """Future LangChain/LLM tool-calling providers implement this interface."""

    def query(self, question: str) -> dict:
        ...

