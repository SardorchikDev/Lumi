"""Short-term memory — keeps the last N turns in context.

Thread-safe: all public methods acquire the lock.
Use the helper methods (replace_last, pop_last, trim_last_n, set_history)
instead of accessing _history directly from other modules.
"""
from __future__ import annotations

import threading


class ShortTermMemory:
    """Rolling window of recent conversation turns — thread-safe."""

    def __init__(self, max_turns: int = 20) -> None:
        self.max_turns: int = max_turns
        self._history: list[dict[str, str]] = []
        self._lock = threading.Lock()

    # ── Core API ──────────────────────────────────────────────────────────────

    def add(self, role: str, content: str) -> None:
        """Append a turn and trim to *2 × max_turns* entries."""
        with self._lock:
            self._history.append({"role": role, "content": content})
            if len(self._history) > self.max_turns * 2:
                self._history = self._history[-(self.max_turns * 2):]

    def get(self) -> list[dict[str, str]]:
        """Return a thread-safe snapshot copy of history.

        Returns a new list each call so callers cannot accidentally mutate
        the internal state without going through the public API.
        """
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        """Discard all stored turns."""
        with self._lock:
            self._history = []

    # ── Mutation helpers (replaces direct _history access) ───────────────────

    def pop_last(self) -> dict[str, str] | None:
        """Remove and return the last message. Returns None if empty."""
        with self._lock:
            return self._history.pop() if self._history else None

    def replace_last(self, role: str, content: str) -> bool:
        """Replace the last message in place.

        Returns True if a message existed and was replaced.
        """
        with self._lock:
            if self._history:
                self._history[-1] = {"role": role, "content": content}
                return True
            return False

    def trim_last_n(self, n: int) -> None:
        """Remove the last *n* messages (no-op if history is shorter)."""
        with self._lock:
            if n > 0 and self._history:
                self._history = self._history[:-n] if len(self._history) >= n else []

    def set_history(self, history: list[dict[str, str]]) -> None:
        """Replace the entire history (e.g. when loading a saved session)."""
        with self._lock:
            self._history = list(history)

    def append_to_last(self, chunk: str) -> None:
        """Append *chunk* to the content of the last message (streaming helper)."""
        with self._lock:
            if self._history:
                self._history[-1]["content"] += chunk

    # ── Convenience ───────────────────────────────────────────────────────────

    def last_role(self) -> str | None:
        """Return the role of the last message, or None if empty."""
        with self._lock:
            return self._history[-1]["role"] if self._history else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._history)
