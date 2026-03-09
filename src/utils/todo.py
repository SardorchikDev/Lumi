"""
Lumi todo system — persistent task tracker.
Saved to data/memory/todos.json
"""
import json, os
from datetime import datetime

TODO_PATH = os.path.join(os.path.dirname(__file__), "../../data/memory/todos.json")

def _load():
    try:
        return json.loads(open(TODO_PATH).read())
    except Exception:
        return []

def _save(todos):
    os.makedirs(os.path.dirname(TODO_PATH), exist_ok=True)
    with open(TODO_PATH, "w") as f:
        json.dump(todos, f, indent=2)

def todo_add(text: str) -> dict:
    todos = _load()
    item = {"id": len(todos) + 1, "text": text, "done": False,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
    todos.append(item)
    _save(todos)
    return item

def todo_list() -> list:
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
    _save(todos)
    return len(todos) < before

def todo_clear_done():
    todos = [t for t in _load() if not t["done"]]
    _save(todos)
    return todos
