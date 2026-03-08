"""
Lumi API client — supports Gemini, Groq, DeepSeek, and HuggingFace.

Priority (first key found in .env wins):
  1. GEMINI_API_KEY     → Google Gemini   (free, 1M context, best for coding)
  2. GROQ_API_KEY       → Groq            (free, very fast)
  3. DEEPSEEK_API_KEY   → DeepSeek        (cheap, very smart)
  4. HF_TOKEN           → HuggingFace     (free tier, rate-limited)

Get free keys:
  Gemini:      https://aistudio.google.com/apikey      ← best for coding
  Groq:        https://console.groq.com                ← fastest free option
  DeepSeek:    https://platform.deepseek.com           ← $2 lasts months
  HuggingFace: https://huggingface.co/settings/tokens
"""

import os
import time
from openai import OpenAI

# ── Model lists ───────────────────────────────────────────────────────────────

GEMINI_MODELS_FALLBACK = [
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
]

_gemini_models_cache = None

def _fetch_gemini_models(api_key: str) -> list:
    """Fetch live model list from Gemini API — gets correct IDs for current region."""
    global _gemini_models_cache
    if _gemini_models_cache is not None:
        return _gemini_models_cache
    try:
        import urllib.request, json
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
        models = [
            m["name"].replace("models/", "")
            for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
            and "flash" in m["name"] or "pro" in m["name"]
        ]
        # Sort: flash-lite first, then flash, then pro
        def sort_key(mid):
            if "flash-8b" in mid or "flash-lite" in mid: return 0
            if "flash" in mid and "2.0" in mid:           return 1
            if "flash" in mid and "1.5" in mid:           return 2
            if "flash" in mid:                            return 3
            if "pro" in mid and "1.5" in mid:             return 4
            if "pro" in mid:                              return 5
            return 9
        models = sorted(set(models), key=sort_key)
        if models:
            _gemini_models_cache = models
            return models
    except Exception:
        pass
    _gemini_models_cache = GEMINI_MODELS_FALLBACK
    return GEMINI_MODELS_FALLBACK

GROQ_MODELS_FALLBACK = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-20b",
]

GROQ_DECOMMISSIONED = {
    "llama3-70b-8192", "llama3-8b-8192", "llama2-70b-4096",
    "mixtral-8x7b-32768", "gemma-7b-it", "gemma2-9b-it",
    "deepseek-r1-distill-llama-70b", "deepseek-r1-distill-qwen-32b",
    "qwen/qwen-3-32b", "llama-3.1-70b-versatile",
}

DEEPSEEK_MODELS = [
    "deepseek-chat",      # DeepSeek-V3 — fast, smart, cheap
    "deepseek-reasoner",  # DeepSeek-R1 — best for hard problems
]

HF_MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
]

HF_FALLBACKS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
]

# ── Groq live model fetch ─────────────────────────────────────────────────────

_groq_models_cache = None

def _fetch_groq_models(api_key: str) -> list:
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
        skip = ("whisper", "tts", "guard", "vision", "embed", "safeguard", "tool-use")
        models = [
            m["id"] for m in data.get("data", [])
            if m.get("active", True)
            and m["id"] not in GROQ_DECOMMISSIONED
            and not any(s in m["id"].lower() for s in skip)
        ]
        if models:
            def sort_key(mid):
                if "instant" in mid:   return 0
                if "8b" in mid:        return 1
                if "versatile" in mid: return 2
                return 9
            models.sort(key=sort_key)
            _groq_models_cache = models
            return models
    except Exception:
        pass
    _groq_models_cache = GROQ_MODELS_FALLBACK
    return GROQ_MODELS_FALLBACK

# ── Provider detection ────────────────────────────────────────────────────────

def get_provider() -> str:
    if os.getenv("GEMINI_API_KEY"):      return "gemini"
    if os.getenv("GROQ_API_KEY"):        return "groq"
    if os.getenv("DEEPSEEK_API_KEY"):    return "deepseek"
    if os.getenv("HF_TOKEN"):            return "huggingface"
    raise EnvironmentError(
        "No API key found in .env\n"
        "  GEMINI_API_KEY=...      ← free at aistudio.google.com/apikey\n"
        "  GROQ_API_KEY=...        ← free at console.groq.com\n"
        "  DEEPSEEK_API_KEY=...    ← cheap at platform.deepseek.com\n"
        "  HF_TOKEN=...            ← free at huggingface.co/settings/tokens"
    )


def get_client() -> OpenAI:
    p = get_provider()
    if p == "gemini":
        return OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("GEMINI_API_KEY"),
        )
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
    if p == "gemini":   return _fetch_gemini_models(os.getenv("GEMINI_API_KEY", ""))
    if p == "groq":     return _fetch_groq_models(os.getenv("GROQ_API_KEY", ""))
    if p == "deepseek": return DEEPSEEK_MODELS
    return HF_MODELS

# ── Friendly error messages ───────────────────────────────────────────────────

def _friendly_error(msg: str, provider: str):
    if "404" in msg or "model_not_found" in msg:
        return "Model not found. Run /model to pick a working one."
    if "decommissioned" in msg.lower() or "model_decommissioned" in msg:
        return "That model was decommissioned. Run /model to pick a working one."
    if "402" in msg or "Insufficient Balance" in msg:
        if provider == "deepseek":
            return "DeepSeek account has no credits. Top up at: https://platform.deepseek.com/top_up"
        return "Hit free credit limit. Add a GEMINI_API_KEY or GROQ_API_KEY (both free) to your .env"
    if "401" in msg or "invalid_api_key" in msg.lower() or "authentication" in msg.lower():
        urls = {
            "gemini": "aistudio.google.com/apikey",
            "groq": "console.groq.com",
            "deepseek": "platform.deepseek.com",
            "huggingface": "huggingface.co/settings/tokens",
        }
        return f"Invalid API key for {provider}. Get a new one at {urls.get(provider, 'your provider dashboard')}"
    if "503" in msg:
        return f"{provider} servers are overloaded. Try again in a moment."
    if "RESOURCE_EXHAUSTED" in msg or "limit: 0" in msg:
        return (
            "Gemini free tier quota exhausted for this model.\n"
            "  → Run /model and switch to gemini-1.5-flash\n"
            "  → Or add a GROQ_API_KEY=... to .env as free fallback"
        )
    return None

# ── Streaming ─────────────────────────────────────────────────────────────────

def chat_stream(
    client: OpenAI,
    messages: list,
    model: str = None,
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
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
            friendly = _friendly_error(msg, provider)
            if friendly and "429" not in msg:
                raise RuntimeError(friendly)

            if "429" in msg and i == 0:
                # Try to extract retryDelay from Gemini errors, else default 15s
                import re as _re
                delay_match = _re.search(r"retry[^0-9]*(\d+)s", msg, _re.IGNORECASE)
                wait = int(delay_match.group(1)) + 1 if delay_match else 15
                import sys as _sys
                _sys.stdout.write(f"  ⏳  rate limited — waiting {wait}s...\r")
                _sys.stdout.flush()
                time.sleep(wait)
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

            if any(code in msg for code in ("400", "503")) or "not supported" in msg.lower():
                if i < len(attempt_models) - 1:
                    continue
            raise

    raise RuntimeError("All models failed.")
