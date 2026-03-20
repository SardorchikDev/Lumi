"""Provider model catalog definitions and resolution helpers."""

from __future__ import annotations

from collections.abc import Callable

from src.chat.model_catalogs import (
    AIRFORCE_MODELS,
    BYTEZ_MODELS,
    CLOUDFLARE_MODELS,
    COHERE_MODELS,
    GITHUB_MODELS,
    GROQ_FALLBACK,
    HF_MODELS,
    MISTRAL_MODELS,
    OPENROUTER_MODELS,
    POLLINATIONS_MODELS,
    VERCEL_MODELS,
    VERTEX_MODELS,
)
from src.chat.model_fetchers import (
    fetch_airforce_models,
    fetch_bytez_models,
    fetch_gemini_models,
    fetch_github_models,
    fetch_groq_models,
    fetch_openrouter_models,
    fetch_pollinations_models,
    fetch_vercel_models,
)
from src.chat.model_registry import ModelRegistry, ProviderCatalog

STATIC_PROVIDER_CATALOGS: dict[str, ProviderCatalog] = {
    "mistral": ProviderCatalog(tuple(MISTRAL_MODELS)),
    "cohere": ProviderCatalog(tuple(COHERE_MODELS)),
    "cloudflare": ProviderCatalog(tuple(CLOUDFLARE_MODELS)),
    "vertex": ProviderCatalog(tuple(VERTEX_MODELS)),
    "huggingface": ProviderCatalog(tuple(HF_MODELS)),
}


def provider_catalog(provider: str) -> ProviderCatalog | None:
    dynamic_catalogs: dict[str, ProviderCatalog] = {
        "gemini": ProviderCatalog(("gemini-3.1-flash-lite-preview", "gemini-2.0-flash"), fetch_gemini_models),
        "groq": ProviderCatalog(tuple(GROQ_FALLBACK), fetch_groq_models),
        "openrouter": ProviderCatalog(tuple(OPENROUTER_MODELS), fetch_openrouter_models),
        "github": ProviderCatalog(tuple(GITHUB_MODELS), fetch_github_models),
        "bytez": ProviderCatalog(tuple(BYTEZ_MODELS), fetch_bytez_models),
        "airforce": ProviderCatalog(tuple(AIRFORCE_MODELS), fetch_airforce_models),
        "vercel": ProviderCatalog(tuple(VERCEL_MODELS), fetch_vercel_models),
        "pollinations": ProviderCatalog(tuple(POLLINATIONS_MODELS), fetch_pollinations_models),
    }
    return dynamic_catalogs.get(provider) or STATIC_PROVIDER_CATALOGS.get(provider)


def discover_models(
    registry: ModelRegistry,
    provider: str,
    curated: list[str],
    fetcher: Callable[[], list[str]],
) -> list[str]:
    cached = registry.read_catalog_cache(provider)
    if cached:
        return cached
    try:
        models = fetcher()
    except Exception:
        models = []
    normalized = [model for model in models if isinstance(model, str) and model.strip()]
    if normalized:
        registry.write_catalog_cache(provider, normalized)
        return normalized
    return curated[:]


def resolve_provider_models(
    registry: ModelRegistry,
    provider: str,
    *,
    ollama_fetcher: Callable[[], list[str]],
) -> list[str]:
    if provider == "ollama":
        return ollama_fetcher()
    catalog = provider_catalog(provider)
    if catalog is None:
        raise ValueError(f"Unsupported provider: {provider}")
    if catalog.fetcher is None:
        return list(catalog.curated)
    return discover_models(registry, provider, list(catalog.curated), catalog.fetcher)
