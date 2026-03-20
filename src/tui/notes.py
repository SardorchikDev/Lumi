"""Persistent "little notes" state for the TUI starter panel."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import UI_STATE_DIR

DEFAULT_NOTES_PATH = UI_STATE_DIR / "little_notes.json"


def _default_payload() -> dict[str, Any]:
    return {
        "recent_commands": [],
        "recent_actions": [],
        "last_provider": "",
        "last_model": "",
        "recent_models": [],
        "favorite_models": [],
        "last_agent_task": "",
        "updated_at": "",
    }


class LittleNotesStore:
    """Persist a small amount of recent UI context between sessions."""

    def __init__(self, path: Path | None = None, command_limit: int = 8) -> None:
        self.path = path or DEFAULT_NOTES_PATH
        self.command_limit = command_limit
        self._data = self._load()
        self._start_session()

    def _start_session(self) -> None:
        """Reset session-scoped UI hints when a new TUI session starts."""
        if not self._data.get("recent_commands"):
            return
        self._data["recent_commands"] = []
        self._save()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _default_payload()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_payload()
        if not isinstance(data, dict):
            return _default_payload()
        merged = _default_payload()
        merged.update({key: value for key, value in data.items() if key in merged})
        recent = merged.get("recent_commands", [])
        merged["recent_commands"] = [item for item in recent if isinstance(item, str) and item.strip()]
        actions = merged.get("recent_actions", [])
        merged["recent_actions"] = [item for item in actions if isinstance(item, str) and item.strip()]
        recent_models = merged.get("recent_models", [])
        merged["recent_models"] = [item for item in recent_models if isinstance(item, str) and item.strip()]
        favorite_models = merged.get("favorite_models", [])
        merged["favorite_models"] = [item for item in favorite_models if isinstance(item, str) and item.strip()]
        return merged

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self._data)
        payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
        with tempfile.NamedTemporaryFile("w", delete=False, dir=self.path.parent, encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            temp_name = handle.name
        Path(temp_name).replace(self.path)

    @property
    def recent_commands(self) -> list[str]:
        return list(self._data.get("recent_commands", []))

    @property
    def recent_actions(self) -> list[str]:
        return list(self._data.get("recent_actions", []))

    @property
    def last_provider(self) -> str:
        return str(self._data.get("last_provider", ""))

    @property
    def last_model(self) -> str:
        return str(self._data.get("last_model", ""))

    @property
    def recent_models(self) -> list[str]:
        return list(self._data.get("recent_models", []))

    @property
    def favorite_models(self) -> list[str]:
        return list(self._data.get("favorite_models", []))

    @property
    def last_agent_task(self) -> str:
        return str(self._data.get("last_agent_task", ""))

    def record_command(self, command: str) -> list[str]:
        normalized = command.strip()
        if not normalized:
            return self.recent_commands
        recent = [normalized] + [item for item in self.recent_commands if item != normalized]
        self._data["recent_commands"] = recent[: self.command_limit]
        self._save()
        return self.recent_commands

    def record_action(self, action: str, limit: int = 6) -> list[str]:
        normalized = " ".join(action.split())
        if not normalized:
            return self.recent_actions
        recent = [normalized] + [item for item in self.recent_actions if item != normalized]
        self._data["recent_actions"] = recent[:limit]
        self._save()
        return self.recent_actions

    def record_model(self, provider: str, model: str) -> None:
        normalized_provider = provider.strip()
        normalized_model = model.strip()
        self._data["last_provider"] = normalized_provider
        self._data["last_model"] = normalized_model
        if normalized_provider and normalized_model:
            key = f"{normalized_provider}::{normalized_model}"
            recent = [key] + [item for item in self.recent_models if item != key]
            self._data["recent_models"] = recent[:12]
        self._save()

    def recent_models_for_provider(self, provider: str, limit: int = 5) -> list[str]:
        prefix = f"{provider.strip()}::"
        models = [item[len(prefix) :] for item in self.recent_models if item.startswith(prefix)]
        return models[:limit]

    def favorite_models_for_provider(self, provider: str) -> list[str]:
        prefix = f"{provider.strip()}::"
        return [item[len(prefix) :] for item in self.favorite_models if item.startswith(prefix)]

    def toggle_favorite_model(self, provider: str, model: str) -> bool:
        normalized_provider = provider.strip()
        normalized_model = model.strip()
        if not normalized_provider or not normalized_model:
            return False
        key = f"{normalized_provider}::{normalized_model}"
        favorites = self.favorite_models
        if key in favorites:
            self._data["favorite_models"] = [item for item in favorites if item != key]
            self._save()
            return False
        favorites = [key] + favorites
        self._data["favorite_models"] = favorites[:24]
        self._save()
        return True

    def record_agent_task(self, task: str) -> None:
        normalized = " ".join(task.split())
        if not normalized:
            return
        self._data["last_agent_task"] = normalized[:160]
        self._save()

    def display_lines(self, limit: int = 3) -> list[str]:
        lines = self.recent_commands[:limit]
        if lines:
            return lines
        return ["no commands this session"]

    def display_action_lines(self, limit: int = 2) -> list[str]:
        return self.recent_actions[:limit]
