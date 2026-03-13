"""
Intelligent perception module.
Uses a lightweight LLM call to classify intent, emotion, and routing needs.
Falls back to regex heuristics if the API is unavailable or for simple checks.
"""

import json
import re

# ── Regex Heuristics (Fallback & Fast Checks) ─────────────────────────────────

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
    """Legacy wrapper for regex emotion detection."""
    return _detect_emotion_regex(text)

def emotion_hint(emotion: str) -> str:
    hints = {
        "frustrated": "[User is frustrated. Be patient, acknowledge difficulty, then help.] ",
        "sad":        "[User is sad/stressed. Be warm and supportive first.] ",
        "confused":   "[User is confused. Explain clearly and simply.] ",
        "happy":      "[User is happy. Match their positive energy.] ",
    }
    return hints.get(emotion, "")

TOPICS = {
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
    """Legacy wrapper for topic detection."""
    t = text.lower()
    scores = {topic: sum(1 for kw in kws if kw in t) for topic, kws in TOPICS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None

# ── Fast Checks (Keep these for speed) ────────────────────────────────────────

SEARCH_TRIGGERS = [
    "search", "look up", "google", "find out", "latest", "recent", "current",
    "today", "news", "update", "who is", "who was", "what is the", "when did",
    "where is", "price of", "weather", "stock",
]
SEARCH_BLOCKLIST = ["what is your", "who are you", "what is life"]

def should_search(text: str) -> bool:
    t = text.lower().strip()
    if any(b in t for b in SEARCH_BLOCKLIST): return False
    return any(tr in t for tr in SEARCH_TRIGGERS)

COMPLEX_CODE_PATTERNS = [
    r"\bcreate\b.{0,50}\b(website|app|server|api|tool)\b",
    r"\bbuild\b.{0,50}\b(website|app|server|api|tool)\b",
    r"\bwrite\b.{0,50}\b(function|class|script|module)\b",
    r"\bimplement\b", r"\brefactor\b", r"\boptimize\b",
    r"\b(index\.html|main\.py|app\.py)\b",
    r"\bfull.{0,10}stack\b",
]

def is_complex_coding_task(text: str) -> bool:
    return any(re.search(p, text.lower()) for p in COMPLEX_CODE_PATTERNS)

def needs_plan_first(text: str) -> bool:
    t = text.lower()
    PLAN_TRIGGERS = [
        r"\bcreate\b.{0,60}\b(folder|project|app|website)\b",
        r"\bbuild\b.{0,40}\b(full|complete|entire)\b",
        r"\bfrom scratch\b",
        r"\bscaffold\b",
    ]
    return any(re.search(p, t) for p in PLAN_TRIGGERS)

# ── LLM Classification (The New Brain) ────────────────────────────────────────

CLASSIFY_PROMPT = """Analyze the user's request and output a JSON object with these fields:
1. "intent": One of ["coding", "chat", "search", "creative", "analysis", "debug", "general"].
2. "emotion": One of ["neutral", "frustrated", "happy", "confused", "sad"].
3. "urgency": "high" or "low".
4. "needs_clarification": Boolean. True only if the request is ambiguous (e.g., "deploy it" without saying where).
5. "tools": List of relevant tools from ["search", "fs", "shell", "git", "mcp"].
6. "routing": List of ideal agent roles for a council from ["reasoning", "code", "creative", "analysis", "precision"].

User request: "{text}"

JSON Output:"""

def classify_request(text: str, client, model: str) -> dict:
    """
    Uses a fast LLM to classify the user's request.
    Returns a dict with intent, emotion, urgency, etc.
    Falls back to regex if LLM fails.
    """
    # Fast path for very short queries
    if len(text.split()) < 3 and not is_complex_coding_task(text):
        return _fallback_classification(text)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(text=text)}],
            max_tokens=150,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        # Clean potential markdown fences
        if raw.startswith("```"):
            raw = re.sub(r"^```json\n?|^```\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        data = json.loads(raw)
        return data
    except Exception:
        return _fallback_classification(text)

def _fallback_classification(text: str) -> dict:
    """Regex-based fallback."""
    intent = "general"
    if is_complex_coding_task(text): intent = "coding"
    elif should_search(text): intent = "search"
    elif detect_topic(text) == "creative": intent = "creative"
    elif "debug" in text.lower() or "fix" in text.lower(): intent = "debug"

    return {
        "intent": intent,
        "emotion": _detect_emotion_regex(text) or "neutral",
        "urgency": "low",
        "needs_clarification": False,
        "tools": ["search"] if should_search(text) else [],
        "routing": ["general"]
    }
