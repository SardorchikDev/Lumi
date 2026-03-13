"""Short-term memory — keeps the last N turns in context."""

from __future__ import annotations


class ShortTermMemory:
    """Rolling window of recent conversation turns."""

    def __init__(self, max_turns: int = 20) -> None:
        self.max_turns: int = max_turns
        self._history: list[dict[str, str]] = []

    def add(self, role: str, content: str) -> None:
        """Append a turn and trim to *2 × max_turns* entries."""
        self._history.append({"role": role, "content": content})
        if len(self._history) > self.max_turns * 2:
            self._history = self._history[-(self.max_turns * 2):]

    def get(self) -> list[dict[str, str]]:
        """Return the full history list."""
        return self._history

    def clear(self) -> None:
        """Discard all stored turns."""
        self._history = []

    def __len__(self) -> int:
        return len(self._history)

