"""Save and load conversations to/from disk."""

import json
import pathlib
from datetime import datetime

CONVERSATIONS_DIR = pathlib.Path("data/conversations")


def save(history: list[dict], session_id: str = "default") -> pathlib.Path:
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = CONVERSATIONS_DIR / f"{session_id}_{timestamp}.json"
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    return path


def load_latest(session_id: str = "default") -> list[dict]:
    files = sorted(CONVERSATIONS_DIR.glob(f"{session_id}_*.json"))
    if not files:
        return []
    return json.loads(files[-1].read_text())


def list_sessions() -> list[str]:
    if not CONVERSATIONS_DIR.exists():
        return []
    return [f.stem for f in sorted(CONVERSATIONS_DIR.glob("*.json"))]
