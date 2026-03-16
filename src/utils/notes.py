"""
Lumi notes system — timestamped notes with search.
Saved to data/memory/notes.json
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from src.config import MEMORY_DIR

NOTES_PATH = MEMORY_DIR / "notes.json"


def _load() -> list[dict[str, Any]]:
    try:
        return json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(notes: list[dict[str, Any]]) -> None:
    NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTES_PATH.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")


def note_add(text: str, tag: str = "") -> dict[str, Any]:
    notes = _load()
    item: dict[str, Any] = {
        "id":      len(notes) + 1,
        "text":    text.strip(),
        "tag":     tag.strip(),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    notes.append(item)
    _save(notes)
    return item


def note_list(tag: str = "") -> list[dict[str, Any]]:
    notes = _load()
    if tag:
        tag_lower = tag.lower()
        return [n for n in notes if n.get("tag", "").lower() == tag_lower]
    return notes


def note_search(query: str) -> list[dict[str, Any]]:
    q = query.lower()
    return [
        n for n in _load()
        if q in n["text"].lower() or q in n.get("tag", "").lower()
    ]


def note_remove(idx: int) -> bool:
    notes = _load()
    before = len(notes)
    notes = [n for n in notes if n["id"] != idx]
    if len(notes) < before:
        _save(notes)
        return True
    return False


def notes_to_markdown() -> str:
    notes = _load()
    if not notes:
        return "# Notes\n\n(empty)"
    lines = ["# Lumi Notes\n"]
    for n in notes:
        tag = f" `#{n['tag']}`" if n.get("tag") else ""
        lines.append(f"- **{n['created']}**{tag}  \n  {n['text']}\n")
    return "\n".join(lines)
