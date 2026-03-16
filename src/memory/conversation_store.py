"""Save and load conversations — with named session support."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import SESSIONS_DIR


def _ensure() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _slug(name: str) -> str:
    """Convert session name to safe filename slug."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip().lower())[:40]


def save(history: list[dict[str, str]], name: str = "") -> pathlib.Path:
    """Save conversation. Returns path."""
    _ensure()
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{_slug(name)}-{ts}" if name else f"session-{ts}"
    path = SESSIONS_DIR / f"{stem}.json"
    path.write_text(json.dumps({
        "name":    name or stem,
        "date":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "messages": history,
    }, indent=2, ensure_ascii=False))
    return path


def load_latest(name: str = "") -> list[dict[str, str]]:
    """Load most recent session, optionally filtered by name."""
    _ensure()
    pattern = f"{_slug(name)}-*.json" if name else "*.json"
    files   = sorted(SESSIONS_DIR.glob(pattern))
    if not files:
        return []
    data = json.loads(files[-1].read_text())
    return data.get("messages", data) if isinstance(data, dict) else data


def load_by_name(name: str) -> list[dict[str, str]]:
    """Load session by exact name or partial slug match."""
    _ensure()
    slug = _slug(name)
    # Exact slug match first
    files = sorted(SESSIONS_DIR.glob(f"{slug}-*.json"))
    if not files:
        # Partial match
        files = sorted(f for f in SESSIONS_DIR.glob("*.json") if slug in f.stem)
    if not files:
        return []
    data = json.loads(files[-1].read_text())
    return data.get("messages", data) if isinstance(data, dict) else data


def list_sessions() -> list[dict[str, Any]]:
    """Return list of {id, name, date, messages} dicts."""
    _ensure()
    results = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
            if isinstance(data, dict):
                results.append({
                    "id":   f.stem,
                    "name": data.get("name", f.stem),
                    "date": data.get("date", "?"),
                    "msgs": len(data.get("messages", [])),
                })
            else:
                results.append({"id": f.stem, "name": f.stem, "date": "?", "msgs": len(data)})
        except Exception:
            pass
    return results


def delete_session(name_or_id: str) -> bool:
    """Delete session by name or id. Returns True if deleted."""
    _ensure()
    slug  = _slug(name_or_id)
    found = False
    for f in SESSIONS_DIR.glob("*.json"):
        if f.stem == name_or_id or f.stem.startswith(slug + "-"):
            f.unlink()
            found = True
    return found
