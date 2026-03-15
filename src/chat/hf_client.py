"""
Lumi API client — Gemini, Groq, HuggingFace.

Add any/all keys to .env — Lumi will let you pick the provider at runtime:
  GEMINI_API_KEY=AIza...       https://aistudio.google.com/apikey
  GROQ_API_KEY=gsk_...         https://console.groq.com
  HF_TOKEN=hf_...              https://huggingface.co/settings/tokens
"""

import json
import os
import time
import urllib.request

from openai import OpenAI

# ── Model lists ───────────────────────────────────────────────────────────────

# ── Gemini models — paid API, smartest first ──────────────────────────────────
# Ordered: most capable → fastest
# Skipping: TTS, Live/Audio, Image-gen, Embedding, Veo, Lyria, Robotics, Computer-Use

GEMINI_CONFIRMED = [
    # ── Gemini 3.x — bleeding edge (preview, paid) ────────────────────────────
    "gemini-3.1-pro-preview",              # 🧠 most advanced, agentic + vibe coding
    "gemini-3-flash-preview",             # ⚡ frontier-class at fraction of cost
    "gemini-3.1-flash-lite-preview",      # 🚀 frontier-class, fast + lightweight

    # ── Gemini 2.5 Pro — most powerful stable ─────────────────────────────────
    "gemini-2.5-pro",                     # 🧠 deepest reasoning + coding, 1M ctx
    "gemini-2.5-pro-preview-06-05",       # 🧠 pro preview with adaptive thinking

    # ── Gemini 2.5 Flash — best price/performance ─────────────────────────────
    "gemini-2.5-flash",                   # ⚡ best all-rounder, thinking + speed
    "gemini-flash-latest",                # ⚡ auto-updated flash alias
    "gemini-2.5-flash-preview-05-20",     # ⚡ flash preview with adaptive thinking

    # ── Gemini 2.5 Flash-Lite — fastest + cheapest ────────────────────────────
    "gemini-2.5-flash-lite",              # 🚀 fastest in 2.5 family, high throughput
    "gemini-2.5-flash-lite-preview",      # 🚀 lite preview

    # ── Gemini 2.0 Flash — stable workhorses ──────────────────────────────────
    "gemini-2.0-flash",                   # ✓ stable, fast, reliable
    "gemini-2.0-flash-001",               # ✓ pinned stable release
    "gemini-2.0-flash-lite",              # ✓ lightest 2.0 model
    "gemini-2.0-flash-lite-001",          # ✓ pinned lite stable
    "gemini-3.1-flash-lite-preview",      # ✓ next-gen lite
]

# Skip: non-text modalities, image-gen, audio, TTS, embeddings, robotics, computer-use
GEMINI_SKIP = {
    # Image generation
    "gemini-2.0-flash-exp-image-generation",
    "gemini-2.5-flash-image", "gemini-2.5-flash-image-generation",
    "gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview",
    "nano-banana-pro-preview", "nano-banana-2-preview",
    # TTS / Audio / Live
    "gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts",
    "gemini-2.5-flash-native-audio-latest",
    "gemini-2.5-flash-native-audio-preview-09-2025",
    "gemini-2.5-flash-native-audio-preview-12-2025",
    "gemini-live-2.5-flash-preview",
    "gemini-2.0-flash-live-001",
    # Embeddings
    "gemini-embedding-001", "gemini-embedding-exp-03-07", "aqa",
    # Robotics / Computer-use / specialised
    "gemini-robotics-er-1.5-preview",
    "gemini-2.5-computer-use-preview-10-2025",
    # Deprecated / shut down
    "gemini-3-pro-preview",      # shut down March 9 2026
    "gemini-pro-latest",
    "deep-research-pro-preview-12-2025",
    # Gemma (no system instruction support)
    "gemma-3-27b-it", "gemma-3-12b-it", "gemma-3-4b-it",
    "gemma-3n-e4b-it", "gemma-3n-e2b-it", "gemma-3-1b-it",
    # Old broken previews
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
    "meta-llama/Llama-3.3-70B-Instruct",      # 70B Llama 3.3 — DEFAULT
    "Qwen/Qwen2.5-72B-Instruct",              # 72B, very capable
    "meta-llama/Llama-3.1-70B-Instruct",      # 70B Llama 3.1
    "mistralai/Mistral-7B-Instruct-v0.3",     # reliable 7B
    "meta-llama/Llama-3.1-8B-Instruct",       # fast 8B fallback
]

HF_FALLBACKS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-7B-Instruct",
]

# OpenRouter — free models (live-fetched, this is the fallback list)
# Curated priority order — live API always fetches the full real list.
# This is used as fallback when API is unreachable AND as the sort order.
OPENROUTER_MODELS = [
    # ── Best for coding & chat (large, powerful) ─────────────
    "qwen/qwen3-coder-480b-a35b:free",                # Qwen3 Coder 480B — best coder, 262k ctx
    "openai/gpt-oss-120b:free",                       # OpenAI open-weight 120B, 131k ctx
    "nousresearch/hermes-3-llama-3.1-405b:free",      # Hermes 3 405B, 131k ctx
    "meta-llama/llama-3.3-70b-instruct:free",         # Llama 3.3 70B, 128k ctx
    "qwen/qwen3-next-80b-a3b-instruct:free",          # Qwen3 Next 80B, 262k ctx
    "zhipuai/glm-4.5-air:free",                       # GLM-4.5 Air 60B weekly tokens, 131k ctx
    "arcee-ai/trinity-mini:free",                     # Arcee Trinity Mini, 131k ctx

    # ── Mid-size solid models ────────────────────────────────
    "openai/gpt-oss-20b:free",                        # OpenAI open-weight 20B, 131k ctx
    "nvidia/nemotron-nano-12b-2-vl:free",             # NVIDIA Nemotron 12B, 128k ctx
    "nvidia/nemotron-nano-9b-v2:free",                # NVIDIA Nemotron 9B, 128k ctx
    "google/gemma-3-27b-it:free",                     # Gemma 3 27B, 131k ctx
    "mistralai/mistral-small-3.1-24b-instruct:free",  # Mistral Small 3.1 24B, 128k ctx

    # ── Fast & lightweight ───────────────────────────────────
    "google/gemma-3-12b-it:free",                     # Gemma 3 12B, 32k ctx
    "google/gemma-3-4b-it:free",                      # Gemma 3 4B, 32k ctx
    "qwen/qwen3-4b:free",                             # Qwen3 4B, 40k ctx
    "meta-llama/llama-3.2-3b-instruct:free",          # Llama 3.2 3B, 131k ctx
    "google/gemma-3n-4b-it:free",                     # Gemma 3n 4B, 8k ctx
    "google/gemma-3n-2b-it:free",                     # Gemma 3n 2B, 8k ctx
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

# GitHub Models — free tier via GitHub API key
GITHUB_MODELS = [
    "gpt-4o",                                  # GPT-4o — flagship
    "gpt-4o-mini",                             # GPT-4o Mini — fast
    "o1-mini",                                 # o1 mini — reasoning
    "DeepSeek-R1",                             # DeepSeek R1 — strong reasoning
    "DeepSeek-V3-0324",                        # DeepSeek V3 — general
    "Meta-Llama-3.1-70B-Instruct",             # Llama 3.1 70B
    "Meta-Llama-3.1-8B-Instruct",              # Llama 3.1 8B — fast
    "Phi-4",                                   # Phi-4 — efficient
    "Phi-3.5-MoE-instruct",                    # Phi-3.5 MoE
    "Mistral-large",                           # Mistral Large
    "Mistral-small",                           # Mistral Small
    "Cohere-command-r-plus-08-2024",           # Command R+
    "AI21-Jamba-1.5-Large",                    # Jamba 1.5 Large
    "xai/grok-3-mini",                         # Grok 3 Mini
]

def _fetch_github_models() -> list:
    """Fetch available models from GitHub Models API."""
    try:
        req = urllib.request.Request(
            "https://models.inference.ai.azure.com/models",
            headers={
                "Authorization": f"Bearer {os.getenv('GITHUB_API_KEY', '')}",
                "Content-Type": "application/json",
            }
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        live = [m.get("name") or m.get("id", "") for m in data if isinstance(m, dict)]
        live = [m for m in live if m]
        if live:
            # Keep our curated order, add any new ones at the end
            ordered = [m for m in GITHUB_MODELS if m in live]
            extras  = [m for m in live if m not in set(GITHUB_MODELS)]
            return ordered + extras
    except Exception:
        pass
    return GITHUB_MODELS[:]


# Cohere — free tier: 20 req/min, 1000 req/month (OpenAI-compatible endpoint)
COHERE_MODELS = [
    "command-a-03-2025",              # flagship, most capable
    "command-a-reasoning-08-2025",    # reasoning variant
    "command-r-plus-08-2024",         # strong general model
    "command-r-08-2024",              # balanced
    "c4ai-aya-expanse-32b",           # multilingual 32B
    "command-r7b-12-2024",            # fast 7B
]

# Cloudflare Workers AI — free 10k neurons/day
# Requires: CLOUDFLARE_API_KEY + CLOUDFLARE_ACCOUNT_ID in .env
# Base URL: https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1
CLOUDFLARE_MODELS = [
    "@cf/openai/gpt-oss-120b",               # 120B GPT-OSS — best on CF
    "@cf/openai/gpt-oss-20b",                # 20B GPT-OSS — fast
    "@cf/qwen/qwen3-30b-a3b-fp8",            # Qwen3 30B MoE — coding + reasoning
    "@cf/zai-org/glm-4.7-flash",             # GLM 4.7 Flash
    "@cf/ibm-granite/granite-4.0-h-micro",   # Granite 4.0 — enterprise
    "@cf/aisingapore/gemma-sea-lion-v4-27b-it", # Gemma Sea Lion 27B
    "@hf/nousresearch/hermes-2-pro-mistral-7b", # Hermes 2 Pro Mistral 7B
    "qwen/qwq-32b",                          # QwQ 32B — deep reasoning
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b", # DeepSeek R1 Distill
    "@cf/meta/llama-3.3-70b-instruct-fp8",   # Llama 3.3 70B
    "@cf/meta/llama-3.2-3b-instruct",        # Llama 3.2 3B — fastest
]

def _cloudflare_base_url() -> str:
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"


# Vercel AI Gateway — $5 free credits/month, 100+ models, no markup fee
# Base: https://ai-gateway.vercel.sh/v1
# Models use provider/model-name format: "openai/gpt-4o", "anthropic/claude-sonnet-4.6"
# Env var: VERCEL_API_KEY
VERCEL_MODELS = [
    # ── OpenAI ───────────────────────────────────────────────────────────────
    "openai/gpt-4.1",                         # GPT-4.1 — flagship reasoning + code
    "openai/gpt-4.1-mini",                    # GPT-4.1 Mini — fast, cheap
    "openai/gpt-4o",                          # GPT-4o — multimodal
    "openai/gpt-4o-mini",                     # GPT-4o Mini — fastest OpenAI
    "openai/o3",                              # o3 — deep reasoning
    "openai/o4-mini",                         # o4-mini — fast reasoning
    "openai/gpt-5",                           # GPT-5 — latest
    # ── Anthropic ────────────────────────────────────────────────────────────
    "anthropic/claude-sonnet-4-5",            # Claude Sonnet 4.5 — best balance
    "anthropic/claude-opus-4",                # Claude Opus 4 — most capable
    "anthropic/claude-haiku-3-5",             # Claude Haiku 3.5 — fastest
    # ── Google ───────────────────────────────────────────────────────────────
    "google/gemini-2.5-pro",                  # Gemini 2.5 Pro — 1M context
    "google/gemini-2.5-flash",                # Gemini 2.5 Flash — fast + smart
    "google/gemini-2.0-flash",                # Gemini 2.0 Flash — stable
    # ── Meta ─────────────────────────────────────────────────────────────────
    "meta/llama-3.3-70b-instruct",            # Llama 3.3 70B — best open
    "meta/llama-3.1-8b-instruct",             # Llama 3.1 8B — lightweight
    # ── xAI ──────────────────────────────────────────────────────────────────
    "xai/grok-3",                             # Grok 3 — strong reasoning
    "xai/grok-3-mini",                        # Grok 3 Mini — fast
    # ── Mistral ──────────────────────────────────────────────────────────────
    "mistral/mistral-large-latest",           # Mistral Large
    "mistral/codestral-latest",               # Codestral — coding specialist
    # ── DeepSeek ─────────────────────────────────────────────────────────────
    "deepseek/deepseek-r1",                   # DeepSeek R1 — open-source reasoning
    "deepseek/deepseek-v3",                   # DeepSeek V3 — strong general
]

# Patterns to skip when live-fetching Vercel model list (non-text modalities)
_VERCEL_SKIP = (
    "embed", "embedding", "tts", "whisper", "dall-e", "image",
    "flux", "stable-diffusion", "audio", "rerank", "moderation",
)

def _fetch_vercel_models() -> list:
    """Fetch available models from Vercel AI Gateway live API."""
    try:
        key = os.getenv("VERCEL_API_KEY", "")
        req = urllib.request.Request(
            "https://ai-gateway.vercel.sh/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        live = [
            m.get("id", "")
            for m in data.get("data", [])
            if isinstance(m, dict) and m.get("id")
        ]
        # Filter out non-text models
        live = [
            m for m in live
            if not any(s in m.lower() for s in _VERCEL_SKIP)
        ]
        if not live:
            return VERCEL_MODELS[:]
        # Keep curated order first, then any new models from live API
        curated_set = set(VERCEL_MODELS)
        ordered = [m for m in VERCEL_MODELS if m in set(live)]
        extras  = [m for m in live if m not in curated_set]
        return ordered + extras
    except Exception:
        return VERCEL_MODELS[:]


# Vertex AI — Google Cloud AI Platform (pay-as-you-go, no free tier)
# Requires: GOOGLE_APPLICATION_CREDENTIALS + VERTEX_PROJECT_ID in .env
# Optional: VERTEX_LOCATION (defaults to us-central1)
# Models: Gemini, Claude, Llama, Mistral via Vertex Model Garden
VERTEX_MODELS = [
    # ── Gemini (via Vertex) ───────────────────────────────────────────────────
    "gemini-2.5-pro-preview-05-06",            # Gemini 2.5 Pro — deepest reasoning
    "gemini-2.5-flash-preview-04-17",          # Gemini 2.5 Flash — best speed/quality
    "gemini-2.0-flash-001",                    # Gemini 2.0 Flash — stable workhorse
    # ── Claude (via Vertex Model Garden) ─────────────────────────────────────
    "claude-sonnet-4-5@20250514",              # Claude Sonnet 4.5 — best balance
    "claude-opus-4@20250514",                  # Claude Opus 4 — most capable
    "claude-haiku-3-5@20241022",               # Claude Haiku 3.5 — fastest
    "claude-sonnet-3-7@20250219",              # Claude Sonnet 3.7 — extended thinking
    # ── Llama (via Vertex Model Garden) ──────────────────────────────────────
    "llama-3.3-70b-instruct-maas",             # Llama 3.3 70B — best open
    "llama-3.1-405b-instruct-maas",            # Llama 3.1 405B — largest open
    "llama-3.1-8b-instruct-maas",              # Llama 3.1 8B — fastest
    # ── Mistral (via Vertex Model Garden) ────────────────────────────────────
    "mistral-large@2407",                      # Mistral Large — flagship
    "mistral-nemo@2407",                       # Mistral Nemo — fast
    "codestral@2405",                          # Codestral — coding specialist
]

def _vertex_base_url() -> str:
    location   = os.getenv("VERTEX_LOCATION", "us-central1")
    project_id = os.getenv("VERTEX_PROJECT_ID", "")
    return (
        f"https://{location}-aiplatform.googleapis.com/v1beta1"
        f"/projects/{project_id}/locations/{location}/endpoints/openapi"
    )


OLLAMA_BASE = os.getenv("OLLAMA_HOST", "http://localhost:11434")

def _fetch_ollama_models() -> list:
    """Fetch models from local Ollama instance."""
    try:
        import json
        import urllib.request
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=2) as r:
            data = json.loads(r.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []

def _has_ollama() -> bool:
    return bool(_fetch_ollama_models())


# ── Provider state (set by user at runtime) ───────────────────────────────────

_active_provider: str = None   # "gemini" | "groq" | "huggingface"
_active_client: OpenAI = None
_models_cache: dict = {}       # provider → list of models


def get_provider() -> str:
    global _active_provider
    if _active_provider:
        return _active_provider
    # Auto-detect from available keys
    if os.getenv("HF_TOKEN"):            return "huggingface"
    if os.getenv("GEMINI_API_KEY"):      return "gemini"
    if os.getenv("GROQ_API_KEY"):        return "groq"
    if os.getenv("OPENROUTER_API_KEY"):  return "openrouter"
    if os.getenv("MISTRAL_API_KEY"):     return "mistral"
    if os.getenv("GITHUB_API_KEY"):      return "github"
    if os.getenv("COHERE_API_KEY"):      return "cohere"
    if os.getenv("VERCEL_API_KEY"):         return "vercel"
    if os.getenv("CLOUDFLARE_API_KEY") and os.getenv("CLOUDFLARE_ACCOUNT_ID"): return "cloudflare"
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and os.getenv("VERTEX_PROJECT_ID"): return "vertex"
    if _has_ollama():                    return "ollama"
    raise OSError(
        "No API key found in .env\n"
        "  GEMINI_API_KEY=...      https://aistudio.google.com/apikey\n"
        "  GROQ_API_KEY=...        https://console.groq.com\n"
        "  OPENROUTER_API_KEY=...  https://openrouter.ai/keys\n"
        "  MISTRAL_API_KEY=...     https://console.mistral.ai\n"
        "  HF_TOKEN=...            https://huggingface.co/settings/tokens\n"
        "  GITHUB_API_KEY=...      https://github.com/settings/tokens\n"
        "  COHERE_API_KEY=...      https://dashboard.cohere.com/api-keys\n"
        "  CLOUDFLARE_API_KEY=...  https://dash.cloudflare.com/profile/api-tokens\n"
        "  CLOUDFLARE_ACCOUNT_ID=... https://dash.cloudflare.com (right sidebar)\n"
        "  VERCEL_API_KEY=...      https://vercel.com/dashboard -> AI -> API Keys\n"
        "  GOOGLE_APPLICATION_CREDENTIALS=... /path/to/service-account.json\n"
        "  VERTEX_PROJECT_ID=...   Your Google Cloud project ID"
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
    if os.getenv("GITHUB_API_KEY"):      providers.append("github")
    if os.getenv("COHERE_API_KEY"):      providers.append("cohere")
    if os.getenv("VERCEL_API_KEY"):         providers.append("vercel")
    if os.getenv("CLOUDFLARE_API_KEY") and os.getenv("CLOUDFLARE_ACCOUNT_ID"): providers.append("cloudflare")
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and os.getenv("VERTEX_PROJECT_ID"): providers.append("vertex")
    if _has_ollama():                    providers.append("ollama")
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
    if provider == "github":
        return OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=os.getenv("GITHUB_API_KEY"),
        )
    if provider == "cohere":
        return OpenAI(
            base_url="https://api.cohere.com/compatibility/v1",
            api_key=os.getenv("COHERE_API_KEY"),
        )
    if provider == "cloudflare":
        return OpenAI(
            base_url=_cloudflare_base_url(),
            api_key=os.getenv("CLOUDFLARE_API_KEY"),
        )
    if provider == "vercel":
        return OpenAI(
            base_url="https://ai-gateway.vercel.sh/v1",
            api_key=os.getenv("VERCEL_API_KEY"),
        )
    if provider == "vertex":
        import google.auth
        from google.auth.transport.requests import Request as _GRequest
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(_GRequest())
        return OpenAI(
            base_url=_vertex_base_url(),
            api_key=creds.token,  # short-lived OAuth2 bearer token
        )
    if provider == "ollama":
        return OpenAI(
            base_url=f"{OLLAMA_BASE}/v1",
            api_key="ollama",
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
    elif p == "github":
        models = _fetch_github_models()
    elif p == "cohere":
        models = COHERE_MODELS[:]
    elif p == "cloudflare":
        models = CLOUDFLARE_MODELS[:]
    elif p == "vercel":
        models = _fetch_vercel_models()
    elif p == "vertex":
        models = VERTEX_MODELS[:]
    elif p == "ollama":
        models = _fetch_ollama_models()
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


# Models to always skip — image-only, audio, embed, or known bad for text chat
OPENROUTER_SKIP = {
    "embed", "audio", "tts", "whisper",
    "dall-e", "stable-diffusion", "midjourney", "flux",
    "rerank", "moderation", "classify",
    "sourceful",   # tiny 8k ctx experimental models
    "venice/uncensored",  # unreliable
}

# Vision/multimodal models — skip unless user explicitly picks them
OPENROUTER_SKIP_PATTERNS = (
    "flux", "dall-e", "stable-diffusion", "sourceful",
)

def _fetch_openrouter_models() -> list:
    """
    Fetch ALL free models from OpenRouter live API.
    - Filters out image/embed/audio/broken models
    - Sorts: curated priority list first, then remaining by context size desc
    - Falls back to OPENROUTER_MODELS if API unreachable
    """
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}",
                "HTTP-Referer": "https://github.com/SardorchikDev/Lumi",
            }
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())

        all_models = data.get("data", [])

        # Filter to only free text models
        free = []
        for m in all_models:
            mid = m.get("id", "")
            if not mid.endswith(":free"):
                continue
            # Skip non-text modalities
            mid_lower = mid.lower()
            if any(skip in mid_lower for skip in OPENROUTER_SKIP):
                continue
            if any(p in mid_lower for p in OPENROUTER_SKIP_PATTERNS):
                continue
            # Skip models with no context window (usually broken)
            ctx = m.get("context_length", 0) or 0
            if ctx < 1024:
                continue
            free.append((mid, ctx))

        if not free:
            return OPENROUTER_MODELS

        free_ids = {mid for mid, _ in free}

        # Priority: curated list first (preserves our smart ordering)
        ordered = [m for m in OPENROUTER_MODELS if m in free_ids]

        # Then anything new not in our curated list, sorted by context size desc
        curated_set = set(OPENROUTER_MODELS)
        extras = sorted(
            [(mid, ctx) for mid, ctx in free if mid not in curated_set],
            key=lambda x: x[1], reverse=True
        )
        extras_ids = [mid for mid, _ in extras]

        result = ordered + extras_ids
        return result if result else OPENROUTER_MODELS

    except Exception:
        return OPENROUTER_MODELS


# ── Friendly errors ───────────────────────────────────────────────────────────

def _friendly_error(msg: str, provider: str):
    if "API_KEY_INVALID" in msg or "API key not valid" in msg:
        return f"Invalid {provider} API key. Check your .env file."
    if "data policy" in msg.lower() or "publication" in msg.lower() or "privacy" in msg.lower():
        return (
            "OpenRouter free models require a privacy setting.\n"
            "  → Go to https://openrouter.ai/settings/privacy\n"
            "  → Enable 'Allow AI training on my data'\n"
            "  → Free models will work after that."
        )
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

# Errors that mean "this model is broken/unavailable, try next one"
_SKIP_ERRORS = (
    "404", "model_not_found", "decommissioned", "not found",
    "limit: 0", "RESOURCE_EXHAUSTED", "503", "502", "not supported",
    "no endpoints", "unavailable", "context length", "rate_limit",
    "moderation", "content policy",
)

def _do_stream(client, model, messages, max_tokens, temperature) -> str:
    """Single streaming attempt — returns full text."""
    stream = client.chat.completions.create(
        model=model, messages=messages,
        max_tokens=max_tokens, temperature=temperature, stream=True,
    )
    full = ""
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
            full += delta
    print()
    if not full.strip():
        raise RuntimeError("Empty response from model.")
    return full.strip()


def chat_stream(
    client: OpenAI,
    messages: list,
    model: str = None,
    max_tokens: int = 8192,
    temperature: float = 0.7,
) -> str:
    import re as _re
    provider = get_provider()
    if model is None:
        model = get_models()[0]

    # Build fallback chain
    if provider == "openrouter":
        all_models  = get_models("openrouter")           # full live list
        # put chosen model first, then rest in order
        rest        = [m for m in all_models if m != model]
        attempt_models = [model] + rest[:12]             # try up to 13 before giving up
    elif provider == "huggingface":
        fallbacks      = [m for m in HF_FALLBACKS if m != model]
        attempt_models = [model] + fallbacks
    else:
        attempt_models = [model]

    last_err = "All models failed."

    for i, m in enumerate(attempt_models):
        try:
            return _do_stream(client, m, messages, max_tokens, temperature)

        except Exception as e:
            msg = str(e)
            friendly = _friendly_error(msg, provider)

            # Hard errors (bad key, no credits, privacy policy) — stop immediately
            if any(x in msg for x in ("API_KEY_INVALID", "API key not valid", "401", "402", "Insufficient Balance")) or "data policy" in msg.lower() or "privacy" in msg.lower():
                raise RuntimeError(friendly or msg)

            # Rate-limited on first model — wait then retry same model once
            if "429" in msg and i == 0:
                wait = 15
                m2 = _re.search(r"retry[^0-9]*(\d+)s", msg, _re.I)
                if m2:
                    wait = int(m2.group(1)) + 1
                sys.stdout.write(f"\r  ⏳  rate limited — retrying in {wait}s...  \r")
                sys.stdout.flush()
                time.sleep(wait)
                try:
                    return _do_stream(client, m, messages, max_tokens, temperature)
                except Exception:
                    pass

            # Broken/unavailable model — skip to next silently
            msg_lower = msg.lower()
            if any(e in msg_lower for e in _SKIP_ERRORS):
                last_err = friendly or f"Model {m} unavailable, trying next..."
                if provider in ("openrouter", "huggingface") and i < len(attempt_models) - 1:
                    sys.stdout.write(f"\r  {m.split('/')[-1]} unavailable — trying next...  \r")
                    sys.stdout.flush()
                    continue

            raise RuntimeError(friendly or msg)

    raise RuntimeError(last_err)
