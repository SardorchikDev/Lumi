"""
Lumi API client — Gemini, Groq, HuggingFace, and OpenAI-compatible gateways.

Add any/all keys to .env — Lumi will let you pick the provider at runtime:
  GEMINI_API_KEY=AIza...          https://aistudio.google.com/apikey
  GROQ_API_KEY=gsk_...            https://console.groq.com
  HF_TOKEN=hf_...                 https://huggingface.co/settings/tokens
  AIRFORCE_API_KEY=...            https://api.airforce
  POLLINATIONS_API_KEY=...        https://gen.pollinations.ai
"""

import os
import time

from openai import OpenAI

from src.chat.client_factory import make_client as _factory_make_client
from src.chat.client_factory import make_vertex_client as _factory_make_vertex_client
from src.chat.model_catalogs import (
    AIRFORCE_MODELS,
    BYTEZ_MODELS,
    CLOUDFLARE_MODELS,
    COHERE_MODELS,
    GITHUB_MODELS,
    GROQ_FALLBACK,
    HF_FALLBACKS,
    HF_MODELS,
    MISTRAL_MODELS,
    OPENROUTER_MODELS,
    POLLINATIONS_MODELS,
    VERCEL_MODELS,
    VERTEX_MODELS,
)
from src.chat.model_fetchers import fetch_airforce_models as _fetch_airforce_models
from src.chat.model_fetchers import fetch_bytez_models as _fetch_bytez_models
from src.chat.model_fetchers import fetch_gemini_models as _fetch_gemini_models
from src.chat.model_fetchers import fetch_github_models as _fetch_github_models
from src.chat.model_fetchers import fetch_groq_models as _fetch_groq_models
from src.chat.model_fetchers import fetch_openrouter_models as _fetch_openrouter_models
from src.chat.model_fetchers import fetch_pollinations_models as _fetch_pollinations_models
from src.chat.model_fetchers import fetch_vercel_models as _fetch_vercel_models
from src.chat.model_registry import ModelRegistry, ProviderCatalog
from src.chat.provider_session import resolve_active_client, set_active_provider
from src.chat.providers import (
    get_configured_providers,
    get_provider_spec,
    pick_default_provider,
    provider_supports,
)
from src.chat.streaming import SKIP_ERRORS as _STREAM_SKIP_ERRORS
from src.chat.streaming import stream_once, stream_with_fallback
from src.config import DATA_DIR

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
_active_client_provider: str | None = None
_active_client_expires_at: float | None = None
_models_cache: dict = {}       # provider → list of models
_models_cache_fetched_at: dict[str, float] = {}
MODEL_CACHE_DIR = DATA_DIR / "model_catalogs"
MODEL_CACHE_TTL_SECONDS = 900
_MODEL_REGISTRY = ModelRegistry(cache_dir=MODEL_CACHE_DIR, ttl_seconds=MODEL_CACHE_TTL_SECONDS)
_STATIC_PROVIDER_CATALOGS: dict[str, ProviderCatalog] = {
    "mistral": ProviderCatalog(tuple(MISTRAL_MODELS)),
    "cohere": ProviderCatalog(tuple(COHERE_MODELS)),
    "cloudflare": ProviderCatalog(tuple(CLOUDFLARE_MODELS)),
    "vertex": ProviderCatalog(tuple(VERTEX_MODELS)),
    "huggingface": ProviderCatalog(tuple(HF_MODELS)),
}


def _sync_registry_state() -> None:
    _MODEL_REGISTRY.cache_dir = MODEL_CACHE_DIR
    _MODEL_REGISTRY.ttl_seconds = MODEL_CACHE_TTL_SECONDS
    _MODEL_REGISTRY._models_cache = _models_cache
    _MODEL_REGISTRY._fetched_at = _models_cache_fetched_at


def _sync_registry_globals() -> None:
    global _models_cache, _models_cache_fetched_at
    _models_cache = _MODEL_REGISTRY._models_cache
    _models_cache_fetched_at = _MODEL_REGISTRY._fetched_at


def _provider_catalog(provider: str) -> ProviderCatalog | None:
    dynamic_catalogs: dict[str, ProviderCatalog] = {
        "gemini": ProviderCatalog(("gemini-3.1-flash-lite-preview", "gemini-2.0-flash"), _fetch_gemini_models),
        "groq": ProviderCatalog(tuple(GROQ_FALLBACK), _fetch_groq_models),
        "openrouter": ProviderCatalog(tuple(OPENROUTER_MODELS), _fetch_openrouter_models),
        "github": ProviderCatalog(tuple(GITHUB_MODELS), _fetch_github_models),
        "bytez": ProviderCatalog(tuple(BYTEZ_MODELS), _fetch_bytez_models),
        "airforce": ProviderCatalog(tuple(AIRFORCE_MODELS), _fetch_airforce_models),
        "vercel": ProviderCatalog(tuple(VERCEL_MODELS), _fetch_vercel_models),
        "pollinations": ProviderCatalog(tuple(POLLINATIONS_MODELS), _fetch_pollinations_models),
    }
    return dynamic_catalogs.get(provider) or _STATIC_PROVIDER_CATALOGS.get(provider)


def _validate_provider(provider: str) -> None:
    if provider == "ollama":
        return
    if not get_provider_spec(provider):
        raise ValueError(f"Unknown provider: {provider}")


def _catalog_cache_path(provider: str):
    _sync_registry_state()
    return _MODEL_REGISTRY.catalog_cache_path(provider)


def _read_catalog_cache(provider: str) -> list[str] | None:
    _sync_registry_state()
    return _MODEL_REGISTRY.read_catalog_cache(provider)


def _write_catalog_cache(provider: str, models: list[str]) -> None:
    _sync_registry_state()
    _MODEL_REGISTRY.write_catalog_cache(provider, models)
    _sync_registry_globals()


def _discover_models(provider: str, curated: list[str], fetcher) -> list[str]:
    cached = _read_catalog_cache(provider)
    if cached:
        return cached
    try:
        models = fetcher()
    except Exception:
        models = []
    normalized = [model for model in models if isinstance(model, str) and model.strip()]
    if normalized:
        _write_catalog_cache(provider, normalized)
        return normalized
    return curated[:]


def get_provider() -> str:
    global _active_provider
    if _active_provider:
        return _active_provider
    detected = pick_default_provider(has_ollama=_has_ollama())
    if detected:
        return detected
    raise OSError(
        "No API key found in .env\n"
        "  GEMINI_API_KEY=...      https://aistudio.google.com/apikey\n"
        "  GROQ_API_KEY=...        https://console.groq.com\n"
        "  OPENROUTER_API_KEY=...  https://openrouter.ai/keys\n"
        "  MISTRAL_API_KEY=...     https://console.mistral.ai\n"
        "  HF_TOKEN=...            https://huggingface.co/settings/tokens\n"
        "  GITHUB_API_KEY=...      https://github.com/settings/tokens\n"
        "  COHERE_API_KEY=...      https://dashboard.cohere.com/api-keys\n"
        "  BYTEZ_API_KEY=...       https://bytez.com/api\n"
        "  AIRFORCE_API_KEY=...    https://api.airforce\n"
        "  CLOUDFLARE_API_KEY=...  https://dash.cloudflare.com/profile/api-tokens\n"
        "  CLOUDFLARE_ACCOUNT_ID=... https://dash.cloudflare.com (right sidebar)\n"
        "  VERCEL_API_KEY=...      https://vercel.com/dashboard -> AI -> API Keys\n"
        "  POLLINATIONS_API_KEY=... https://gen.pollinations.ai\n"
        "  GOOGLE_APPLICATION_CREDENTIALS=... /path/to/service-account.json\n"
        "  VERTEX_PROJECT_ID=...   Your Google Cloud project ID"
    )


def set_provider(provider: str):
    global _active_provider, _active_client, _active_client_provider, _active_client_expires_at
    _validate_provider(provider)
    _active_provider = provider
    _active_client, _active_client_provider, _active_client_expires_at = set_active_provider(
        provider,
        make_client=_make_client,
    )


def get_available_providers() -> list:
    """Return list of providers that have a key configured."""
    return get_configured_providers(has_ollama=_has_ollama())


def _make_client(provider: str) -> OpenAI:
    _validate_provider(provider)
    return _factory_make_client(provider, ollama_base=OLLAMA_BASE)


def _make_vertex_client() -> tuple[OpenAI, float]:
    return _factory_make_vertex_client()


def get_client() -> OpenAI:
    global _active_client, _active_client_provider, _active_client_expires_at
    provider = get_provider()
    _active_client, _active_client_provider, _active_client_expires_at = resolve_active_client(
        provider=provider,
        active_client=_active_client,
        active_client_provider=_active_client_provider,
        active_client_expires_at=_active_client_expires_at,
        make_client=_make_client,
        make_vertex_client=_make_vertex_client,
    )
    return _active_client


# ── Model fetching ────────────────────────────────────────────────────────────

def get_models(provider: str = None) -> list:
    p = provider or get_provider()
    _validate_provider(p)
    _sync_registry_state()
    cached = _models_cache.get(p)
    fetched_at = _models_cache_fetched_at.get(p, 0)
    if cached and (time.time() - fetched_at) <= MODEL_CACHE_TTL_SECONDS:
        return cached
    if p == "ollama":
        models = _fetch_ollama_models()
    else:
        catalog = _provider_catalog(p)
        if catalog is None:
            raise ValueError(f"Unsupported provider: {p}")
        if catalog.fetcher is not None:
            models = _discover_models(p, list(catalog.curated), catalog.fetcher)
        else:
            models = list(catalog.curated)
    _models_cache[p] = models
    _models_cache_fetched_at[p] = time.time()
    _sync_registry_globals()
    return models


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

_SKIP_ERRORS = _STREAM_SKIP_ERRORS

def _do_stream(client, model, messages, max_tokens, temperature, on_delta=None) -> str:
    """Single streaming attempt — returns full text."""
    return stream_once(
        client,
        model,
        messages,
        max_tokens,
        temperature,
        on_delta=on_delta,
    )


def _call_stream_attempt(client, model, messages, max_tokens, temperature, on_delta=None) -> str:
    try:
        return _do_stream(
            client,
            model,
            messages,
            max_tokens,
            temperature,
            on_delta=on_delta,
        )
    except TypeError as exc:
        if "on_delta" not in str(exc):
            raise
        return _do_stream(client, model, messages, max_tokens, temperature)


def chat_stream(
    client: OpenAI,
    messages: list,
    model: str = None,
    max_tokens: int = 8192,
    temperature: float = 0.7,
    *,
    on_delta=None,
    on_status=None,
    sleep_fn=time.sleep,
) -> str:
    provider = get_provider()
    if model is None:
        model = get_models()[0]

    # Build fallback chain
    if provider_supports(provider, "fallbacks"):
        all_models = get_models(provider)
        rest = [m for m in all_models if m != model]
        attempt_models = [model] + rest[:12]
    elif provider == "huggingface":
        fallbacks = [m for m in HF_FALLBACKS if m != model]
        attempt_models = [model] + fallbacks
    else:
        attempt_models = [model]
    return stream_with_fallback(
        client=client,
        provider=provider,
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        attempt_models=attempt_models,
        supports_fallbacks=provider_supports(provider, "fallbacks"),
        hf_fallbacks=HF_FALLBACKS,
        friendly_error=_friendly_error,
        on_delta=on_delta,
        on_status=on_status,
        sleep_fn=sleep_fn,
        stream_fn=lambda active_client, active_model, active_messages, active_max_tokens, active_temperature: _call_stream_attempt(
            active_client,
            active_model,
            active_messages,
            active_max_tokens,
            active_temperature,
            on_delta=on_delta,
        ),
    )
