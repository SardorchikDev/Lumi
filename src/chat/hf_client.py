"""
Lumi API client — Gemini, Groq, HuggingFace.

Add any/all keys to .env — Lumi will let you pick the provider at runtime:
  GEMINI_API_KEY=AIza...       https://aistudio.google.com/apikey
  GROQ_API_KEY=gsk_...         https://console.groq.com
  HF_TOKEN=hf_...              https://huggingface.co/settings/tokens
"""

import os
import time
import json
import urllib.request
from openai import OpenAI

# ── Model lists ───────────────────────────────────────────────────────────────

# Only models confirmed to work with system prompts on the free tier
GEMINI_CONFIRMED = [
    "gemini-3.1-flash-lite-preview",   # ✓ confirmed working
    "gemini-2.5-flash",                # ✓ confirmed working
    "gemini-2.0-flash",                # ✓ confirmed working
    "gemini-2.0-flash-001",            # ✓ stable release
    "gemini-2.0-flash-lite",           # ✓ lightest, fast
    "gemini-2.0-flash-lite-001",       # ✓ stable lite
    "gemini-flash-latest",             # ✓ latest flash alias
]

# Skip: image-gen, TTS, audio, embed, pay-only, no system prompt support
GEMINI_SKIP = {
    "gemini-2.5-pro", "gemini-pro-latest",
    "gemini-3-pro-preview", "gemini-3.1-pro-preview",
    "gemini-3-flash-preview", "gemini-3.1-pro-preview-customtools",
    "gemini-2.0-flash-exp-image-generation", "gemini-2.5-flash-image",
    "gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview",
    "gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts",
    "gemini-2.5-flash-native-audio-latest",
    "gemini-2.5-flash-native-audio-preview-09-2025",
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-2.5-computer-use-preview-10-2025",
    "deep-research-pro-preview-12-2025", "nano-banana-pro-preview",
    "gemini-robotics-er-1.5-preview",
    "gemini-embedding-001", "aqa",
    # Gemma doesn't support system instructions
    "gemma-3-27b-it", "gemma-3-12b-it", "gemma-3-4b-it",
    "gemma-3n-e4b-it", "gemma-3n-e2b-it", "gemma-3-1b-it",
    # Extra previews with limit: 0
    "gemini-2.5-flash-lite-preview-09-2025",
}

# Groq — all free, sorted smartest first
GROQ_FALLBACK = [
    # ── Production (stable, always available) ─────────
    "openai/gpt-oss-120b",             # 120B OpenAI open-weight, flagship
    "llama-3.3-70b-versatile",         # best all-rounder, very reliable
    "openai/gpt-oss-20b",              # fast GPT-OSS
    "llama-3.1-8b-instant",            # fastest, lightest
    # ── Preview (powerful but may have limits) ────────
    "moonshotai/kimi-k2-instruct-0905",           # Kimi K2, strong reasoning
    "meta-llama/llama-4-maverick-17b-128e-instruct", # Llama 4 Maverick
    "meta-llama/llama-4-scout-17b-16e-instruct",     # Llama 4 Scout
    "qwen/qwen-3-32b",                 # Qwen3 32B, great for coding
]

GROQ_DECOMMISSIONED = {
    "llama3-70b-8192", "llama3-8b-8192", "llama2-70b-4096",
    "mixtral-8x7b-32768", "gemma-7b-it", "gemma2-9b-it",
    "deepseek-r1-distill-llama-70b", "deepseek-r1-distill-qwen-32b",
    "llama-3.1-70b-versatile",
}

# HuggingFace — free tier (rate limited), sorted smartest first
HF_MODELS = [
    "Qwen/Qwen2.5-72B-Instruct",              # 72B, very capable
    "meta-llama/Llama-3.3-70B-Instruct",      # 70B Llama 3.3
    "meta-llama/Llama-3.1-70B-Instruct",      # 70B Llama 3.1
    "mistralai/Mistral-7B-Instruct-v0.3",     # reliable 7B
    "meta-llama/Llama-3.1-8B-Instruct",       # fast 8B fallback
]

HF_FALLBACKS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-7B-Instruct",
]

# OpenRouter — free models (append :free), sorted smartest first
OPENROUTER_MODELS = [
    "deepseek/deepseek-r1:free",                      # DeepSeek R1 671B reasoning
    "deepseek/deepseek-r1-0528:free",                 # DeepSeek R1 latest
    "qwen/qwen3-235b-a22b:free",                      # Qwen3 235B MoE
    "qwen/qwen3-32b:free",                            # Qwen3 32B
    "meta-llama/llama-4-maverick:free",               # Llama 4 Maverick
    "meta-llama/llama-4-scout:free",                  # Llama 4 Scout
    "mistralai/devstral-small:free",                  # Mistral coding model
    "mistralai/mistral-small-3.1-24b-instruct:free",  # Mistral Small 3.1 24B
    "google/gemma-3-27b-it:free",                     # Gemma 3 27B
    "microsoft/mai-ds-r1:free",                       # Microsoft MAI DS R1
    "openrouter/free",                                # auto-router (picks best available)
]

# Mistral free tier (Experiment plan — needs phone verify, no card)
MISTRAL_MODELS = [
    "mistral-small-latest",      # Mistral Small — free tier
    "open-mistral-nemo",         # Mistral NeMo 12B — free
    "open-codestral-mamba",      # Codestral Mamba — free, great for code
]

# OpenRouter — free models (append :free suffix)
OPENROUTER_MODELS = [
    "deepseek/deepseek-r1:free",               # best reasoning, 671B
    "deepseek/deepseek-r1-0528:free",          # latest DeepSeek R1
    "deepseek/deepseek-v3-0324:free",          # DeepSeek V3, great coding
    "qwen/qwen3-235b-a22b:free",               # Qwen3 235B, massive
    "qwen/qwen3-30b-a3b:free",                 # Qwen3 30B fast
    "mistralai/devstral-small-2505:free",      # 123B coding specialist
    "meta-llama/llama-4-maverick:free",        # Llama 4 Maverick
    "meta-llama/llama-4-scout:free",           # Llama 4 Scout
    "microsoft/mai-ds-r1:free",                # Microsoft MAI reasoning
    "google/gemma-3-27b-it:free",              # Gemma 3 27B via OpenRouter
    "mistralai/mistral-7b-instruct:free",      # reliable Mistral 7B
    "nvidia/llama-3.1-nemotron-ultra-253b:free", # NVIDIA 253B
]

# Mistral — free tier (1B tokens/month)
MISTRAL_MODELS = [
    "mistral-large-latest",      # most capable
    "mistral-medium-latest",     # balanced
    "mistral-small-latest",      # fast, free tier friendly
    "open-mistral-nemo",         # 12B open model
    "codestral-latest",          # coding specialist, free
    "open-codestral-mamba",      # fast coding model
]

# ── Provider state (set by user at runtime) ───────────────────────────────────

_active_provider: str = None   # "gemini" | "groq" | "huggingface"
_active_client: OpenAI = None
_models_cache: dict = {}       # provider → list of models


def get_provider() -> str:
    global _active_provider
    if _active_provider:
        return _active_provider
    # Auto-detect from available keys
    if os.getenv("GEMINI_API_KEY"):      return "gemini"
    if os.getenv("GROQ_API_KEY"):        return "groq"
    if os.getenv("OPENROUTER_API_KEY"):  return "openrouter"
    if os.getenv("MISTRAL_API_KEY"):     return "mistral"
    if os.getenv("HF_TOKEN"):            return "huggingface"
    raise EnvironmentError(
        "No API key found in .env\n"
        "  GEMINI_API_KEY=...      https://aistudio.google.com/apikey\n"
        "  GROQ_API_KEY=...        https://console.groq.com\n"
        "  OPENROUTER_API_KEY=...  https://openrouter.ai/keys\n"
        "  MISTRAL_API_KEY=...     https://console.mistral.ai\n"
        "  HF_TOKEN=...            https://huggingface.co/settings/tokens"
    )


def set_provider(provider: str):
    global _active_provider, _active_client
    _active_provider = provider
    _active_client   = _make_client(provider)


def get_available_providers() -> list:
    """Return list of providers that have a key configured."""
    providers = []
    if os.getenv("GEMINI_API_KEY"):      providers.append("gemini")
    if os.getenv("GROQ_API_KEY"):        providers.append("groq")
    if os.getenv("OPENROUTER_API_KEY"):  providers.append("openrouter")
    if os.getenv("MISTRAL_API_KEY"):     providers.append("mistral")
    if os.getenv("HF_TOKEN"):            providers.append("huggingface")
    return providers


def _make_client(provider: str) -> OpenAI:
    if provider == "gemini":
        return OpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=os.getenv("GEMINI_API_KEY"),
        )
    if provider == "groq":
        return OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        )
    if provider == "openrouter":
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    if provider == "mistral":
        return OpenAI(
            base_url="https://api.mistral.ai/v1",
            api_key=os.getenv("MISTRAL_API_KEY"),
        )
    return OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=os.getenv("HF_TOKEN"),
    )


def get_client() -> OpenAI:
    global _active_client
    if _active_client is None:
        _active_client = _make_client(get_provider())
    return _active_client


# ── Model fetching ────────────────────────────────────────────────────────────

def get_models(provider: str = None) -> list:
    global _models_cache
    p = provider or get_provider()
    if p in _models_cache:
        return _models_cache[p]
    if p == "gemini":
        models = _fetch_gemini_models()
    elif p == "groq":
        models = _fetch_groq_models()
    elif p == "openrouter":
        models = _fetch_openrouter_models()
    elif p == "mistral":
        models = MISTRAL_MODELS[:]
    else:
        models = HF_MODELS
    _models_cache[p] = models
    return models


def _fetch_gemini_models() -> list:
    try:
        key = os.getenv("GEMINI_API_KEY", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read())
        available = {
            m["name"].replace("models/", "")
            for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        }
        # Keep confirmed models that exist for this key, in order, skip junk
        models = [m for m in GEMINI_CONFIRMED if m in available and m not in GEMINI_SKIP]
        return models if models else ["gemini-3.1-flash-lite-preview", "gemini-2.0-flash"]
    except Exception:
        return ["gemini-3.1-flash-lite-preview", "gemini-2.0-flash"]


def _fetch_groq_models() -> list:
    try:
        key = os.getenv("GROQ_API_KEY", "")
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        skip = ("whisper", "tts", "guard", "vision", "embed", "safeguard", "playai")
        live = {
            m["id"] for m in data.get("data", [])
            if m.get("active", True)
            and m["id"] not in GROQ_DECOMMISSIONED
            and not any(s in m["id"].lower() for s in skip)
        }
        # Return GROQ_FALLBACK order but only include ones live API confirms
        ordered = [m for m in GROQ_FALLBACK if m in live]
        # Add any new models from live API not in our list
        extras = sorted(live - set(GROQ_FALLBACK))
        return ordered + extras if ordered else GROQ_FALLBACK
    except Exception:
        pass
    return GROQ_FALLBACK


def _fetch_openrouter_models() -> list:
    """Fetch free models from OpenRouter live API."""
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}"}
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        # Only keep :free models
        free = [
            m["id"] for m in data.get("data", [])
            if m["id"].endswith(":free")
            and "embed" not in m["id"].lower()
            and "vision" not in m["id"].lower()
        ]
        # Sort: our curated order first, then rest alphabetically
        ordered = [m for m in OPENROUTER_MODELS if m in free or m == "openrouter/free"]
        extras  = sorted(set(free) - set(ordered))
        return ordered + extras if ordered else OPENROUTER_MODELS
    except Exception:
        return OPENROUTER_MODELS


# ── Friendly errors ───────────────────────────────────────────────────────────

def _friendly_error(msg: str, provider: str):
    if "API_KEY_INVALID" in msg or "API key not valid" in msg:
        return f"Invalid {provider} API key. Check your .env file."
    if "404" in msg or "model_not_found" in msg:
        return "Model not found. Run /model to pick a working one."
    if "decommissioned" in msg.lower() or "model_decommissioned" in msg:
        return "That model was decommissioned. Run /model to pick another."
    if "402" in msg or "Insufficient Balance" in msg:
        return "No credits. Top up at platform.deepseek.com/top_up"
    if "401" in msg or "authentication" in msg.lower():
        return f"Auth failed for {provider}. Check your API key in .env"
    if "limit: 0" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "Quota hit for this model. Run /model and pick another."
    if "503" in msg:
        return f"{provider} servers overloaded. Try again in a moment."
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

    fallbacks     = [m for m in HF_FALLBACKS if m != model] if provider == "huggingface" else []
    attempt_models = [model] + fallbacks

    for i, m in enumerate(attempt_models):
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

        except Exception as e:
            msg     = str(e)
            friendly = _friendly_error(msg, provider)

            if friendly and "429" not in msg:
                raise RuntimeError(friendly)

            if "429" in msg and i == 0:
                import re as _re
                delay = int(m2.group(1)) + 1 if (m2 := _re.search(r"retry[^0-9]*(\d+)s", msg, _re.I)) else 15
                import sys as _sys
                _sys.stdout.write(f"  ⏳  rate limited — waiting {delay}s...\r")
                _sys.stdout.flush()
                time.sleep(delay)
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

            if "limit: 0" in msg or any(c in msg for c in ("400","503")) or "not supported" in msg.lower():
                if i < len(attempt_models) - 1:
                    continue
            raise

    raise RuntimeError("All models failed.")
