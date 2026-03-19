"""
Intelligent perception module.

Classification is tiered for performance:
  1. Regex fast-path — zero latency, handles obvious cases.
  2. LLM call        — only fires when regex is not confident.

Falls back to regex heuristics if the API call fails.
"""
from __future__ import annotations

import json
import re

# ── Regex Heuristics ──────────────────────────────────────────────────────────

FRUSTRATED = [
    "ugh", "wtf", "this is stupid", "doesn't work", "not working",
    "broken", "useless", "hate this", "so annoying", "why won't",
    "terrible", "worst", "garbage", "trash", "idiot", "dumb",
    "frustrating", "irritating", "fed up", "sick of", "i give up",
]

SAD = [
    "i'm sad", "feeling down", "depressed", "lonely", "miss",
    "upset", "crying", "heartbroken", "terrible day", "awful",
    "horrible", "can't deal", "overwhelmed", "stressed",
]

CONFUSED = [
    "i don't understand", "confused", "what do you mean",
    "can you explain", "huh?", "what?", "i'm lost",
    "not sure i get", "clarify", "could you rephrase",
    "don't get it", "makes no sense",
]

HAPPY = [
    "thanks!", "thank you!", "awesome", "amazing", "love it",
    "perfect", "great job", "nice", "cool!", "that's great",
    "exactly what i needed", "brilliant", "wonderful", "yay",
    "this is great", "that worked",
]

def _detect_emotion_regex(text: str) -> str | None:
    t = text.lower()
    if any(w in t for w in FRUSTRATED): return "frustrated"
    if any(w in t for w in SAD):        return "sad"
    if any(w in t for w in CONFUSED):   return "confused"
    if any(w in t for w in HAPPY):      return "happy"
    return None


def detect_emotion(text: str) -> str | None:
    """Return the dominant emotion string, or None if neutral."""
    return _detect_emotion_regex(text)


def emotion_hint(emotion: str) -> str:
    hints = {
        "frustrated": "[User is frustrated. Be patient, acknowledge difficulty, then help.] ",
        "sad":        "[User is sad/stressed. Be warm and supportive first.] ",
        "confused":   "[User is confused. Explain clearly and simply.] ",
        "happy":      "[User is happy. Match their positive energy.] ",
    }
    return hints.get(emotion, "")


TOPICS: dict[str, list[str]] = {
    "coding":    ["code", "python", "javascript", "bug", "error", "function", "class", "api", "git"],
    "writing":   ["write", "essay", "blog", "story", "poem", "draft", "edit"],
    "math":      ["math", "calculate", "equation", "formula", "algebra"],
    "science":   ["science", "physics", "chemistry", "biology"],
    "health":    ["health", "exercise", "diet", "sleep", "stress"],
    "tech":      ["technology", "ai", "hardware", "computer", "app", "server"],
    "life":      ["life", "work", "career", "goals", "advice"],
    "creative":  ["idea", "design", "art", "music", "imagine"],
}


def detect_topic(text: str) -> str | None:
    t      = text.lower()
    scores = {topic: sum(1 for kw in kws if kw in t) for topic, kws in TOPICS.items()}
    best   = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


# ── Fast boolean checks ───────────────────────────────────────────────────────

SEARCH_TRIGGERS = [
    "search", "look up", "google", "find out", "latest", "recent", "current",
    "today", "news", "update", "who is", "who was", "what is the", "when did",
    "where is", "price of", "weather", "stock",
]
SEARCH_BLOCKLIST = ["what is your", "who are you", "what is life"]


def should_search(text: str) -> bool:
    t = text.lower().strip()
    if any(b in t for b in SEARCH_BLOCKLIST):
        return False
    return any(tr in t for tr in SEARCH_TRIGGERS)


COMPLEX_CODE_PATTERNS = [
    re.compile(r"\bcreate\b.{0,50}\b(website|app|server|api|tool)\b"),
    re.compile(r"\bbuild\b.{0,50}\b(website|app|server|api|tool)\b"),
    re.compile(r"\bwrite\b.{0,50}\b(function|class|script|module)\b"),
    re.compile(r"\bimplement\b"),
    re.compile(r"\brefactor\b"),
    re.compile(r"\boptimize\b"),
    re.compile(r"\b(index\.html|main\.py|app\.py)\b"),
    re.compile(r"\bfull.{0,10}stack\b"),
]


def is_complex_coding_task(text: str) -> bool:
    t = text.lower()
    return any(p.search(t) for p in COMPLEX_CODE_PATTERNS)


PLAN_TRIGGERS = [
    re.compile(r"\bcreate\b.{0,60}\b(folder|project|app|website)\b"),
    re.compile(r"\bbuild\b.{0,40}\b(full|complete|entire)\b"),
    re.compile(r"\bfrom scratch\b"),
    re.compile(r"\bscaffold\b"),
]


def needs_plan_first(text: str) -> bool:
    t = text.lower()
    return any(p.search(t) for p in PLAN_TRIGGERS)


# ── LLM Classification ────────────────────────────────────────────────────────

CLASSIFY_PROMPT = """Analyze the user's request and output a JSON object with these fields:
1. "intent": One of ["coding", "chat", "search", "creative", "analysis", "debug", "general"].
2. "emotion": One of ["neutral", "frustrated", "happy", "confused", "sad"].
3. "urgency": "high" or "low".
4. "needs_clarification": Boolean. True only if the request is genuinely ambiguous.
5. "tools": List of relevant tools from ["search", "fs", "shell", "git", "mcp"].
6. "routing": List of ideal agent roles from ["reasoning", "code", "creative", "analysis", "precision"].

User request: "{text}"

JSON Output:"""


def _fallback_classification(text: str) -> dict:
    """Pure-regex classification — zero latency, no API cost."""
    intent = "general"
    if is_complex_coding_task(text):     intent = "coding"
    elif _is_debug_query(text):          intent = "debug"
    elif should_search(text):            intent = "search"
    elif detect_topic(text) == "creative": intent = "creative"

    return {
        "intent":             intent,
        "emotion":            _detect_emotion_regex(text) or "neutral",
        "urgency":            "low",
        "needs_clarification": False,
        "tools":              ["search"] if should_search(text) else [],
        "routing":            ["general"],
    }


_DEBUG_WORDS = (
    "traceback",
    "error",
    "exception",
    "debug",
    "bug",
    "attributeerror",
    "typeerror",
    "syntaxerror",
    "valueerror",
    "keyerror",
    "indexerror",
)


def _is_debug_query(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in _DEBUG_WORDS)


# Regex signals that are strong enough to skip the LLM entirely.
def _is_high_confidence(text: str, fallback: dict) -> bool:
    intent = fallback["intent"]
    if intent == "coding" and is_complex_coding_task(text):
        return True
    if intent == "debug" and _is_debug_query(text):
        return True
    if intent == "search" and should_search(text):
        return True
    return bool(intent == "chat" and len(text.split()) <= 5)


def classify_request(text: str, client, model: str) -> dict:
    """Classify a user request.

    Tiered approach:
      1. For short / obviously-typed queries → regex only (zero cost).
      2. For high-confidence regex signals  → regex only (zero cost).
      3. Otherwise                          → LLM classification.
      4. LLM failure                        → regex fallback.
    """
    # Tier 1: very short queries — regex is always sufficient
    if len(text.split()) < 4:
        return _fallback_classification(text)

    fallback = _fallback_classification(text)

    # Tier 2: strong regex signal — skip the LLM call
    if _is_high_confidence(text, fallback):
        return fallback

    # Tier 3: LLM for genuinely ambiguous cases
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(text=text)}],
            max_tokens=150,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip potential markdown fences
        if raw.startswith("```"):
            raw = re.sub(r"^```json\n?|^```\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        # Ensure required keys exist (LLM may omit some)
        for key, default in fallback.items():
            data.setdefault(key, default)
        return data
    except Exception:
        # Tier 4: graceful degradation — return regex result
        return fallback
