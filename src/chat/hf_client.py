"""
Lumi API client — supports Groq, DeepSeek, and HuggingFace.

Priority (first key found in .env wins):
  1. GROQ_API_KEY       → Groq          (free, very fast)
  2. DEEPSEEK_API_KEY   → DeepSeek      (cheap, smart)
  3. HF_TOKEN           → HuggingFace   (free tier, rate-limited)

Get free keys:
  Groq:        https://console.groq.com          ← recommended
  DeepSeek:    https://platform.deepseek.com     ← $2 lasts months
  HuggingFace: https://huggingface.co/settings/tokens
"""

import os
import time
from openai import OpenAI

# ── Model lists ───────────────────────────────────────────────────────────────

# Production models known to be active — but we also fetch live from the API.
# These are used as fallback if the API call fails.
GROQ_MODELS_FALLBACK = [
    "llama-3.1-8b-instant",        # fast, free, great default
    "llama-3.3-70b-versatile",     # smarter, still free
    "openai/gpt-oss-20b",          # GPT-OSS 20B via Groq
]

# Models that Groq has decommissioned — filtered out even if the API returns them
GROQ_DECOMMISSIONED = {
    # Decommissioned
    "llama3-70b-8192",
    "llama3-8b-8192",
    "llama2-70b-4096",
    "mixtral-8x7b-32768",
    "gemma-7b-it",
    "gemma2-9b-it",
    "deepseek-r1-distill-llama-70b",
    "deepseek-r1-distill-qwen-32b",
    # 404 — listed in API but not actually hosted
    "qwen/qwen-3-32b",
    # Also decommissioned
    "llama-3.1-70b-versatile",
}

_groq_models_cache: list | None = None

def _fetch_groq_models(api_key: str) -> list:
    """Fetch live model list from Groq API, filtered to working chat models."""
    global _groq_models_cache
    if _groq_models_cache is not None:
        return _groq_models_cache
    try:
        import urllib.request, json
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        # Filter out: non-chat models + known decommissioned
        skip_words = ("whisper", "tts", "guard", "vision", "embed", "safeguard", "tool-use")
        models = [
            m["id"] for m in data.get("data", [])
            if m.get("active", True)
            and m["id"] not in GROQ_DECOMMISSIONED
            and not any(s in m["id"].lower() for s in skip_words)
        ]
        if models:
            def sort_key(mid):
                if "instant" in mid:    return 0
                if "8b" in mid:         return 1
                if "versatile" in mid:  return 2
                return 9
            models.sort(key=sort_key)
            _groq_models_cache = models
            return models
    except Exception:
        pass
    _groq_models_cache = GROQ_MODELS_FALLBACK
    return GROQ_MODELS_FALLBACK

# For get_models() to call after client is init
GROQ_MODELS = GROQ_MODELS_FALLBACK

DEEPSEEK_MODELS = [
    "deepseek-chat",              # DeepSeek-V3 — fast, smart, cheap
    "deepseek-reasoner",          # DeepSeek-R1 — best for hard problems
]

HF_MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",   # most reliable free model
    "Qwen/Qwen2.5-7B-Instruct",           # lightweight alternative
    "mistralai/Mistral-7B-Instruct-v0.3", # compact, reliable
]

HF_FALLBACKS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
]

# ── Provider detection ────────────────────────────────────────────────────────

def get_provider() -> str:
    if os.getenv("GROQ_API_KEY"):        return "groq"
    if os.getenv("DEEPSEEK_API_KEY"):    return "deepseek"
    if os.getenv("HF_TOKEN"):            return "huggingface"
    raise EnvironmentError(
        "No API key found in .env\n"
        "  GROQ_API_KEY=...        ← free at console.groq.com\n"
        "  DEEPSEEK_API_KEY=...    ← cheap at platform.deepseek.com\n"
        "  HF_TOKEN=...            ← free at huggingface.co/settings/tokens"
    )


def get_client() -> OpenAI:
    p = get_provider()
    if p == "groq":
        return OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        )
    if p == "deepseek":
        return OpenAI(
            base_url="https://api.deepseek.com",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
        )
    return OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=os.getenv("HF_TOKEN"),
    )


def get_models() -> list:
    p = get_provider()
    if p == "groq":
        key = os.getenv("GROQ_API_KEY", "")
        return _fetch_groq_models(key)
    if p == "deepseek": return DEEPSEEK_MODELS
    return HF_MODELS


# ── Friendly error messages ───────────────────────────────────────────────────

def _friendly_error(msg: str, provider: str) -> str | None:
    """Return a human-readable error string, or None to re-raise as-is."""
    if "404" in msg or "model_not_found" in msg:
        return f"Model not found on Groq. Run /model to pick a working one."
    if "decommissioned" in msg.lower() or "model_decommissioned" in msg:
        return f"Model '{provider}' has been decommissioned by Groq. Run /model to pick a working one."
    if "402" in msg or "Insufficient Balance" in msg:
        if provider == "deepseek":
            return "DeepSeek account has no credits. Top up at: https://platform.deepseek.com/top_up"
        return "You've hit your monthly HF free credit limit. Try adding a GROQ_API_KEY (free) to your .env"
    if "401" in msg or "invalid_api_key" in msg.lower() or "authentication" in msg.lower():
        urls = {"groq": "console.groq.com", "deepseek": "platform.deepseek.com", "huggingface": "huggingface.co/settings/tokens"}
        return f"Invalid API key for {provider}. Check your .env — get a new one at {urls.get(provider, 'your provider dashboard')}"
    if "rate_limit" in msg.lower() or "429" in msg:
        return None  # handled separately with retry
    if "503" in msg:
        return f"The {provider} servers are overloaded right now. Try again in a moment."
    return None


# ── Streaming ─────────────────────────────────────────────────────────────────

def chat_stream(
    client: OpenAI,
    messages: list,
    model: str = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """Stream a reply. Auto-retries with fallback models on failure."""
    provider = get_provider()
    if model is None:
        model = get_models()[0]

    fallbacks = [m for m in HF_FALLBACKS if m != model] if provider == "huggingface" else []
    attempt_models = [model] + fallbacks

    for i, m in enumerate(attempt_models):
        try:
            stream = client.chat.completions.create(
                model=m,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            full = ""
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    print(delta, end="", flush=True)
                    full += delta
            print()
            return full.strip()

        except Exception as e:
            msg = str(e)

            # Friendly error translation
            friendly = _friendly_error(msg, provider)
            if friendly and "429" not in msg:
                raise RuntimeError(friendly)

            # Rate limit — wait and retry once
            if "429" in msg and i == 0:
                time.sleep(3)
                try:
                    stream = client.chat.completions.create(
                        model=m, messages=messages,
                        max_tokens=max_tokens, temperature=temperature, stream=True,
                    )
                    full = ""
                    for chunk in stream:
                        delta = chunk.choices[0].delta.content
                        if delta:
                            print(delta, end="", flush=True)
                            full += delta
                    print()
                    return full.strip()
                except Exception:
                    pass

            # Unsupported/unavailable model — try next fallback silently
            if any(code in msg for code in ("400", "503")) or "not supported" in msg.lower():
                if i < len(attempt_models) - 1:
                    continue

            raise

    raise RuntimeError("All models failed.")
