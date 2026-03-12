"""Long-term memory — persists facts and episodic summaries."""

import json
import pathlib
import pickle
import numpy as np

# ── Fact Memory (JSON) ────────────────────────────────────────────────────────
MEMORY_FILE = pathlib.Path("data/memory/longterm.json")

def _load() -> dict:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if MEMORY_FILE.exists():
        try: return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception: pass
    return {"facts": [], "persona_override": {}}

def _save(data: dict):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def get_facts() -> list:
    return _load().get("facts", [])

def add_fact(fact: str) -> int:
    data = _load()
    data["facts"].append(fact.strip())
    _save(data)
    return len(data["facts"])

def remove_fact(idx: int) -> bool:
    data = _load()
    facts = data.get("facts", [])
    if 0 <= idx < len(facts):
        facts.pop(idx)
        _save(data)
        return True
    return False

def clear_facts():
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
def get_persona_override() -> dict:
    return _load().get("persona_override", {})

def set_persona_override(override: dict):
    data = _load()
    data["persona_override"] = override
    _save(data)

def clear_persona_override():
    data = _load()
    data.pop("persona_override", None)
    _save(data)

# ── Episodic Memory (Vector Search) ───────────────────────────────────────────
EPISODIC_DB_PATH = pathlib.Path.home() / "Lumi" / "data" / "memory" / "episodes.pkl"

def get_related_episodes(query: str, client, limit=3) -> list[str]:
    """Find summaries of past conversations related to the query."""
    if not EPISODIC_DB_PATH.exists() or not client:
        return []
    
    from src.tools.rag import get_embedding, cosine_similarity
    
    q_emb = get_embedding(query, client)
    if not q_emb:
        return []
    
    q_vec = np.array(q_emb, dtype=np.float32)
    
    try:
        with open(EPISODIC_DB_PATH, "rb") as f:
            episodes = pickle.load(f)  # format: {summary_text: vector}
    except Exception:
        return []

    scores = []
    for summary, vec in episodes.items():
        score = cosine_similarity(q_vec, vec)
        scores.append((score, summary))
        
    scores.sort(key=lambda x: x[0], reverse=True)
    return [summary for score, summary in scores[:limit]]

def save_episode(summary: str, vector: np.ndarray):
    """Save a new session summary and its vector."""
    EPISODIC_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(EPISODIC_DB_PATH, "rb") as f:
            episodes = pickle.load(f)
    except (IOError, EOFError):
        episodes = {}
        
    episodes[summary] = vector
    
    with open(EPISODIC_DB_PATH, "wb") as f:
        pickle.dump(episodes, f)

SUMMARIZE_PROMPT = """You are a summarization agent. Read the following conversation and create a concise, one-paragraph summary of what was discussed and accomplished. Focus on the key topics, decisions, and outcomes.

Conversation History:
{history}

One-paragraph summary:"""

def auto_summarize_and_save(history: list, client, model: str):
    """Generate a summary, get its embedding, and save it."""
    if len(history) < 6: # Don't summarize very short chats
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
            # 3. Save
            save_episode(summary, np.array(vector, dtype=np.float32))
            print(f"\n  [memory] Saved session summary.")
            
    except Exception as e:
        print(f"\n  [memory] Failed to save session summary: {e}")

