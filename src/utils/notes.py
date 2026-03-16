"""
Lumi notes system — timestamped notes with search.
Saved to data/memory/notes.json
"""
import json
from datetime import datetime
from pathlib import Path

from src.config import MEMORY_DIR

NOTES_PATH = MEMORY_DIR / "notes.json"

def _load():
    try:
        return json.loads(open(NOTES_PATH).read())
    except Exception:
        return []

def _save(notes):
    os.makedirs(os.path.dirname(NOTES_PATH), exist_ok=True)
    with open(NOTES_PATH, "w") as f:
        json.dump(notes, f, indent=2)

def note_add(text: str, tag: str = "") -> dict:
    notes = _load()
    item = {
        "id":      len(notes) + 1,
        "text":    text,
        "tag":     tag,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    notes.append(item)
    _save(notes)
    return item

def note_list(tag: str = "") -> list:
    notes = _load()
    if tag:
        return [n for n in notes if n.get("tag", "").lower() == tag.lower()]
    return notes

def note_search(query: str) -> list:
    q = query.lower()
    return [n for n in _load() if q in n["text"].lower() or q in n.get("tag", "").lower()]

def note_remove(idx: int) -> bool:
    notes = _load()
    before = len(notes)
    notes = [n for n in notes if n["id"] != idx]
    _save(notes)
    return len(notes) < before

def notes_to_markdown() -> str:
    notes = _load()
    if not notes:
        return "# Notes\n\n(empty)"
    lines = ["# Lumi Notes\n"]
    for n in notes:
        tag = f" `#{n['tag']}`" if n.get("tag") else ""
        lines.append(f"- **{n['created']}**{tag}  \n  {n['text']}\n")
    return "\n".join(lines)
