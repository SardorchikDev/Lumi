"""Long-term memory — persists facts and episodic summaries."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from src.config import MEMORY_DIR
from src.utils.log import get_logger

logger = get_logger(__name__)

# ── Fact Memory (JSON) ────────────────────────────────────────────────────────
MEMORY_FILE = MEMORY_DIR / "longterm.json"

def _load() -> dict[str, Any]:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to load long-term memory: %s", e, exc_info=True)
    return {"facts": [], "persona_override": {}}

def _save(data: dict[str, Any]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=MEMORY_FILE.parent, encoding="utf-8") as handle:
        handle.write(serialized)
        temp_name = handle.name
    tempfile_path = Path(temp_name)
    tempfile_path.replace(MEMORY_FILE)

def get_facts() -> list[str]:
    return _load().get("facts", [])

def add_fact(fact: str) -> int:
    data = _load()
    normalized = " ".join(fact.strip().split())
    if not normalized:
        return len(data["facts"])
    existing = {item.casefold() for item in data.get("facts", [])}
    if normalized.casefold() not in existing:
        data["facts"].append(normalized)
    _save(data)
    return len(data["facts"])


def update_fact(idx: int, fact: str) -> bool:
    data = _load()
    facts = data.get("facts", [])
    normalized = " ".join(fact.strip().split())
    if not normalized or not (0 <= idx < len(facts)):
        return False
    facts[idx] = normalized
    deduped: list[str] = []
    seen: set[str] = set()
    for item in facts:
        key = item.casefold()
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    data["facts"] = deduped
    _save(data)
    return True

def remove_fact(idx: int) -> bool:
    data = _load()
    facts = data.get("facts", [])
    if 0 <= idx < len(facts):
        facts.pop(idx)
        _save(data)
        return True
    return False

def clear_facts() -> None:
    data = _load()
    data["facts"] = []
    _save(data)

def build_memory_block() -> str:
    facts = get_facts()
    if not facts: return ""
    lines = ["The following are facts you must always remember about the user:"]
    for i, f in enumerate(facts, 1):
        lines.append(f"  {i}. {f}")
    return "\n".join(lines)

# ── Persona Override ──────────────────────────────────────────────────────────
def get_persona_override() -> dict[str, Any]:
    return _load().get("persona_override", {})

def set_persona_override(override: dict[str, Any]) -> None:
    data = _load()
    data["persona_override"] = override
    _save(data)

def clear_persona_override() -> None:
    data = _load()
    data.pop("persona_override", None)
    _save(data)

# ── Episodic Memory (Vector Search) ───────────────────────────────────────────
EPISODIC_DB_PATH = MEMORY_DIR / "episodes.sqlite3"
LEGACY_EPISODIC_DB_PATH = MEMORY_DIR / "episodes.pkl"


def _episode_conn() -> sqlite3.Connection:
    EPISODIC_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(EPISODIC_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS episodes (
            summary TEXT PRIMARY KEY,
            vector_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _migrate_legacy_episode_db() -> None:
    if not LEGACY_EPISODIC_DB_PATH.exists() or EPISODIC_DB_PATH.exists():
        return
    try:
        import pickle

        with LEGACY_EPISODIC_DB_PATH.open("rb") as handle:
            episodes = pickle.load(handle)
        if not isinstance(episodes, dict):
            return
        with _episode_conn() as conn:
            for summary, vector in episodes.items():
                if not isinstance(summary, str):
                    continue
                vec = np.asarray(vector, dtype=np.float32)
                conn.execute(
                    "INSERT OR REPLACE INTO episodes(summary, vector_json) VALUES (?, ?)",
                    (summary, json.dumps(vec.tolist(), ensure_ascii=False)),
                )
            conn.commit()
    except Exception:
        logger.exception("Failed to migrate legacy episodic memory store")


def _load_episodes() -> list[tuple[str, np.ndarray]]:
    _migrate_legacy_episode_db()
    if not EPISODIC_DB_PATH.exists():
        return []
    try:
        with _episode_conn() as conn:
            rows = conn.execute("SELECT summary, vector_json FROM episodes").fetchall()
    except sqlite3.Error:
        logger.exception("Failed to read episodic memory database")
        return []
    episodes: list[tuple[str, np.ndarray]] = []
    for summary, vector_json in rows:
        try:
            vector = np.array(json.loads(vector_json), dtype=np.float32)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        episodes.append((summary, vector))
    return episodes


def get_related_episodes(query: str, client: Any, limit: int = 3) -> list[str]:
    """Find summaries of past conversations related to the query."""
    if not client:
        return []

    episodes = _load_episodes()
    if not episodes:
        return []

    from src.tools.rag import cosine_similarity, get_embedding

    q_emb = get_embedding(query, client)
    if not q_emb:
        return []

    q_vec = np.array(q_emb, dtype=np.float32)
    scores = []
    for summary, vec in episodes:
        score = cosine_similarity(q_vec, vec)
        scores.append((score, summary))

    scores.sort(key=lambda x: x[0], reverse=True)
    return [summary for score, summary in scores[:limit]]


def save_episode(summary: str, vector: np.ndarray) -> None:
    """Save a new session summary and its vector."""
    normalized = " ".join(summary.split())
    if not normalized:
        return
    payload = np.asarray(vector, dtype=np.float32).tolist()
    with _episode_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO episodes(summary, vector_json) VALUES (?, ?)",
            (normalized, json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()

SUMMARIZE_PROMPT = """You are a summarization agent. Read the following conversation and create a concise, one-paragraph summary of what was discussed and accomplished. Focus on the key topics, decisions, and outcomes.

Conversation History:
{history}

One-paragraph summary:"""

def auto_summarize_and_save(history: list[dict[str, str]], client: Any, model: str) -> None:
    """Generate a summary, get its embedding, and save it."""
    if len(history) < 6:  # Don't summarize very short chats
        return

    from src.tools.rag import get_embedding, get_embedding_client

    # 1. Generate Summary
    try:
        history_str = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in history])
        prompt = SUMMARIZE_PROMPT.format(history=history_str)

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.2,
        )
        summary = resp.choices[0].message.content.strip()

        if not summary:
            return

        # 2. Get Embedding
        # Use a separate client for embeddings if needed, or reuse
        emb_client = get_embedding_client()
        if not emb_client:
            return

        vector = get_embedding(summary, emb_client)
        if vector:
            save_episode(summary, np.array(vector, dtype=np.float32))
            logger.info("Saved episodic session summary")

    except Exception as e:
        logger.exception("Failed to save session summary: %s", e)
