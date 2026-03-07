"""
Lightweight emotion detection and topic tracking.
No external deps — pure keyword heuristics.
"""

# ── Emotion detection ─────────────────────────────────────────────────────────

FRUSTRATED = [
    "ugh", "wtf", "this is stupid", "doesn't work", "not working",
    "broken", "useless", "hate this", "so annoying", "why won't",
    "terrible", "worst", "garbage", "trash", "idiot", "dumb",
    "frustrating", "irritating", "fed up", "sick of", "i give up",
]

HAPPY = [
    "thanks!", "thank you!", "awesome", "amazing", "love it",
    "perfect", "great job", "nice", "cool!", "that's great",
    "exactly what i needed", "brilliant", "wonderful", "yay",
    "this is great", "that worked",
]

CONFUSED = [
    "i don't understand", "confused", "what do you mean",
    "can you explain", "huh?", "what?", "i'm lost",
    "not sure i get", "clarify", "could you rephrase",
    "don't get it", "makes no sense",
]

SAD = [
    "i'm sad", "feeling down", "depressed", "lonely", "miss",
    "upset", "crying", "heartbroken", "terrible day", "awful",
    "horrible", "can't deal", "overwhelmed", "stressed",
]


def detect_emotion(text: str) -> str:
    """Returns 'frustrated' | 'happy' | 'confused' | 'sad' | None"""
    t = text.lower()
    if any(w in t for w in FRUSTRATED): return "frustrated"
    if any(w in t for w in SAD):        return "sad"
    if any(w in t for w in CONFUSED):   return "confused"
    if any(w in t for w in HAPPY):      return "happy"
    return None


def emotion_hint(emotion: str) -> str:
    """Returns a hint to inject into the message so the model adjusts tone."""
    hints = {
        "frustrated": "[Note: the user seems frustrated. Be extra patient, acknowledge their difficulty briefly, then help.] ",
        "sad":        "[Note: the user seems sad or stressed. Be warm and supportive first, then helpful.] ",
        "confused":   "[Note: the user seems confused. Explain more clearly and simply than usual.] ",
        "happy":      "[Note: the user is in a good mood. Match their positive energy.] ",
    }
    return hints.get(emotion, "")


# ── Topic tracking ────────────────────────────────────────────────────────────

TOPICS = {
    "coding":    ["code", "python", "javascript", "bug", "error", "function", "class", "api", "script", "program", "debug", "variable", "loop", "array", "git"],
    "writing":   ["write", "essay", "article", "blog", "story", "poem", "paragraph", "draft", "edit", "proofread", "sentence"],
    "math":      ["math", "calculate", "equation", "formula", "algebra", "geometry", "calculus", "number", "solve", "integral", "derivative"],
    "science":   ["science", "physics", "chemistry", "biology", "experiment", "theory", "research", "hypothesis", "data"],
    "health":    ["health", "exercise", "diet", "sleep", "stress", "mental", "fitness", "nutrition", "weight", "doctor"],
    "tech":      ["technology", "ai", "machine learning", "software", "hardware", "computer", "app", "website", "server", "database"],
    "life":      ["life", "relationship", "family", "friend", "work", "career", "money", "goals", "motivation", "advice"],
    "creative":  ["idea", "creative", "design", "art", "music", "film", "game", "imagine", "invent", "brainstorm"],
}


def detect_topic(text: str) -> str:
    """Returns the most likely topic or None."""
    t = text.lower()
    scores = {topic: sum(1 for kw in kws if kw in t) for topic, kws in TOPICS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


# ── Smarter search trigger ────────────────────────────────────────────────────

# Only search when the query genuinely needs current/factual external info.
# Much tighter than the original list — avoids triggering on casual chat.
SEARCH_TRIGGERS = [
    # Explicit
    "search for", "look up", "google", "find out",
    # Current events / time-sensitive
    "latest", "recent", "current", "today", "this week", "this year",
    "news", "update", "release", "just announced", "new version",
    # Factual lookups
    "who is", "who was", "what is the", "when did", "when was",
    "where is", "how much does", "what's the price", "price of",
    "weather", "stock price", "exchange rate",
]

# These phrases should NOT trigger search even if keywords match
SEARCH_BLOCKLIST = [
    "what is your", "what is my", "what is life", "what is love",
    "what is the meaning", "who are you", "who am i",
]


def should_search(text: str) -> bool:
    t = text.lower().strip()
    if any(b in t for b in SEARCH_BLOCKLIST):
        return False
    return any(trigger in t for trigger in SEARCH_TRIGGERS)
