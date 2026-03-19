"""Short-term memory — keeps the last N turns in context.

Thread-safe: all public methods acquire the lock.
Use the helper methods (replace_last, pop_last, trim_last_n, set_history)
instead of accessing _history directly from other modules.
"""
from __future__ import annotations

import re
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
        """Return a snapshot of the current history."""
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        """Discard all stored turns."""
        with self._lock:
            self._history = []

    def snapshot(self) -> list[dict[str, str]]:
        """Return a copy for callers that need an isolated snapshot."""
        with self._lock:
            return list(self._history)

    def stats(self) -> dict[str, int]:
        """Return a small structured summary of the current session memory."""
        with self._lock:
            roles = [item.get("role", "") for item in self._history]
            return {
                "total_messages": len(self._history),
                "max_messages": self.max_turns * 2,
                "user_messages": sum(1 for role in roles if role == "user"),
                "assistant_messages": sum(1 for role in roles if role == "assistant"),
                "system_messages": sum(1 for role in roles if role == "system"),
            }

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

    def remove_last_exchange(self) -> bool:
        """Remove the most recent user/assistant pair if present."""
        with self._lock:
            if len(self._history) < 2:
                return False
            self._history = self._history[:-2]
            return True

    def set_history(self, history: list[dict[str, str]]) -> None:
        """Replace the entire history (e.g. when loading a saved session)."""
        with self._lock:
            self._history = list(history)

    def replace_with_summary(self, summary: str, tail_messages: int = 4) -> bool:
        """Compress history into a summary plus the most recent messages."""
        if not summary.strip():
            return False
        with self._lock:
            tail = self._history[-tail_messages:] if tail_messages > 0 else []
            self._history = [{"role": "system", "content": f"[Summary]: {summary.strip()}"}] + tail
            return True

    def relevant_slice(self, query: str, limit: int = 6) -> list[dict[str, str]]:
        """Return the most relevant recent messages for *query*."""
        tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", query or "")
        }
        with self._lock:
            history = list(self._history)
        if not tokens:
            return history[-limit:]
        scored: list[tuple[int, int, dict[str, str]]] = []
        for index, message in enumerate(history):
            content = str(message.get("content", "")).lower()
            score = sum(1 for token in tokens if token in content)
            if score:
                scored.append((score, index, message))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        picked = sorted(scored[:limit], key=lambda item: item[1])
        return [message for _, _, message in picked] or history[-limit:]

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
