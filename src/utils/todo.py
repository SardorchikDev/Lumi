"""
Lumi todo system — persistent task tracker.
Saved to data/memory/todos.json
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.config import MEMORY_DIR

TODO_PATH = MEMORY_DIR / "todos.json"


def _load() -> list[dict[str, Any]]:
    try:
        return json.loads(TODO_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(todos: list[dict[str, Any]]) -> None:
    TODO_PATH.parent.mkdir(parents=True, exist_ok=True)
    TODO_PATH.write_text(json.dumps(todos, indent=2, ensure_ascii=False), encoding="utf-8")


def todo_add(text: str) -> dict[str, Any]:
    todos = _load()
    item: dict[str, Any] = {
        "id":      len(todos) + 1,
        "text":    text.strip(),
        "done":    False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    todos.append(item)
    _save(todos)
    return item


def todo_list() -> list[dict[str, Any]]:
    return _load()


def todo_done(idx: int) -> bool:
    todos = _load()
    for t in todos:
        if t["id"] == idx:
            t["done"] = True
            _save(todos)
            return True
    return False


def todo_remove(idx: int) -> bool:
    todos = _load()
    before = len(todos)
    todos = [t for t in todos if t["id"] != idx]
    if len(todos) < before:
        _save(todos)
        return True
    return False


def todo_clear_done() -> list[dict[str, Any]]:
    todos = [t for t in _load() if not t["done"]]
    _save(todos)
    return todos
