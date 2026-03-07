"""Long-term memory — persists facts about the user across sessions."""

import json
import pathlib

MEMORY_FILE = pathlib.Path("data/memory/longterm.json")


def _load() -> dict:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
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
        data["facts"] = facts
        _save(data)
        return True
    return False


def clear_facts():
    data = _load()
    data["facts"] = []
    _save(data)


def build_memory_block() -> str:
    """Return a block to inject into the system prompt."""
    facts = get_facts()
    if not facts:
        return ""
    lines = ["The following are facts you must always remember about the user:"]
    for i, f in enumerate(facts, 1):
        lines.append(f"  {i}. {f}")
    return "\n".join(lines)


# ── Persona override ──────────────────────────────────────────
def get_persona_override() -> dict:
    return _load().get("persona_override", {})


def set_persona_override(override: dict):
    data = _load()
    data["persona_override"] = override
    _save(data)


def clear_persona_override():
    data = _load()
    data["persona_override"] = {}
    _save(data)
