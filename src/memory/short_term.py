"""Short-term memory — keeps the last N turns in context."""


class ShortTermMemory:
    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self._history: list[dict] = []

    def add(self, role: str, content: str):
        self._history.append({"role": role, "content": content})
        if len(self._history) > self.max_turns * 2:
            self._history = self._history[-(self.max_turns * 2):]

    def get(self) -> list[dict]:
        return self._history

    def clear(self):
        self._history = []

    def __len__(self):
        return len(self._history)

