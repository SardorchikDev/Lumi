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


def save(history: list[dict[str, str]], name: str = "") -> Path:
    """Persist conversation history to a timestamped JSON file.

    Returns the path to the written file.
    """
    _ensure()
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{_slug(name)}-{ts}" if name else f"session-{ts}"
    path = SESSIONS_DIR / f"{stem}.json"
    path.write_text(
        json.dumps(
            {
                "name":     name or stem,
                "date":     datetime.now().strftime("%Y-%m-%d %H:%M"),
                "messages": history,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _read_session(path: Path) -> list[dict[str, str]]:
    """Read messages from a session file, handling both old and new formats."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        return data.get("messages", [])
    if isinstance(data, list):
        return data
    return []


def load_latest(name: str = "") -> list[dict[str, str]]:
    """Load the most recent session, optionally filtered by slug prefix."""
    _ensure()
    pattern = f"{_slug(name)}-*.json" if name else "*.json"
    files   = sorted(SESSIONS_DIR.glob(pattern))
    return _read_session(files[-1]) if files else []


def load_by_name(name: str) -> list[dict[str, str]]:
    """Load session by exact name or partial slug match."""
    _ensure()
    slug  = _slug(name)
    files = sorted(SESSIONS_DIR.glob(f"{slug}-*.json"))
    if not files:
        # Partial match fallback
        files = sorted(
            f for f in SESSIONS_DIR.glob("*.json") if slug in f.stem
        )
    return _read_session(files[-1]) if files else []


def list_sessions() -> list[dict[str, Any]]:
    """Return a list of ``{id, name, date, msgs}`` dicts, newest first."""
    _ensure()
    results: list[dict[str, Any]] = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if isinstance(data, dict):
            results.append(
                {
                    "id":   f.stem,
                    "name": data.get("name", f.stem),
                    "date": data.get("date", "?"),
                    "msgs": len(data.get("messages", [])),
                }
            )
        elif isinstance(data, list):
            results.append(
                {"id": f.stem, "name": f.stem, "date": "?", "msgs": len(data)}
            )
    return results


def delete_session(name_or_id: str) -> bool:
    """Delete all session files matching *name_or_id*. Returns True if any deleted."""
    _ensure()
    slug  = _slug(name_or_id)
    found = False
    for f in SESSIONS_DIR.glob("*.json"):
        if f.stem == name_or_id or f.stem.startswith(slug + "-"):
            f.unlink(missing_ok=True)
            found = True
    return found
