"""Provider metadata and capability helpers for Lumi."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    env_vars: tuple[str, ...]
    capabilities: frozenset[str]
    description: str

    def configured(self) -> bool:
        return all(os.getenv(var) for var in self.env_vars)


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        "gemini",
        "Gemini",
        ("GEMINI_API_KEY",),
        frozenset({"chat", "stream", "long_context"}),
        "Google Gemini models",
    ),
    "groq": ProviderSpec(
        "groq",
        "Groq",
        ("GROQ_API_KEY",),
        frozenset({"chat", "stream", "fast"}),
        "Fast hosted inference",
    ),
    "openrouter": ProviderSpec(
        "openrouter",
        "OpenRouter",
        ("OPENROUTER_API_KEY",),
        frozenset({"chat", "stream", "fallbacks"}),
        "Aggregated hosted models",
    ),
    "mistral": ProviderSpec(
        "mistral",
        "Mistral",
        ("MISTRAL_API_KEY",),
        frozenset({"chat", "stream"}),
        "Mistral hosted models",
    ),
    "huggingface": ProviderSpec(
        "huggingface",
        "HuggingFace",
        ("HF_TOKEN",),
        frozenset({"chat", "stream"}),
        "HuggingFace router",
    ),
    "github": ProviderSpec(
        "github",
        "GitHub Models",
        ("GITHUB_API_KEY",),
        frozenset({"chat", "stream"}),
        "GitHub-hosted model gateway",
    ),
    "cohere": ProviderSpec(
        "cohere",
        "Cohere",
        ("COHERE_API_KEY",),
        frozenset({"chat", "stream"}),
        "Cohere compatibility endpoint",
    ),
    "bytez": ProviderSpec(
        "bytez",
        "Bytez",
        ("BYTEZ_API_KEY",),
        frozenset({"chat", "stream", "fallbacks"}),
        "Bytez open-source model catalog",
    ),
    "airforce": ProviderSpec(
        "airforce",
        "Airforce",
        ("AIRFORCE_API_KEY",),
        frozenset({"chat", "stream", "fallbacks"}),
        "Airforce unified AI gateway",
    ),
    "cloudflare": ProviderSpec(
        "cloudflare",
        "Cloudflare",
        ("CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"),
        frozenset({"chat", "stream"}),
        "Workers AI OpenAI-compatible endpoint",
    ),
    "vercel": ProviderSpec(
        "vercel",
        "Vercel AI",
        ("VERCEL_API_KEY",),
        frozenset({"chat", "stream", "fallbacks"}),
        "Vercel AI Gateway",
    ),
    "pollinations": ProviderSpec(
        "pollinations",
        "Pollinations",
        ("POLLINATIONS_API_KEY",),
        frozenset({"chat", "stream", "fallbacks"}),
        "Pollinations unified generative API",
    ),
    "vertex": ProviderSpec(
        "vertex",
        "Vertex AI",
        ("GOOGLE_APPLICATION_CREDENTIALS", "VERTEX_PROJECT_ID"),
        frozenset({"chat", "stream", "long_context"}),
        "Google Cloud Vertex AI",
    ),
}

DEFAULT_PROVIDER_ORDER = [
    "huggingface",
    "gemini",
    "groq",
    "openrouter",
    "mistral",
    "github",
    "cohere",
    "bytez",
    "airforce",
    "vercel",
    "pollinations",
    "cloudflare",
    "vertex",
]


def get_provider_spec(provider: str) -> ProviderSpec | None:
    return PROVIDER_SPECS.get(provider)


def get_configured_providers(has_ollama: bool = False) -> list[str]:
    providers = [name for name, spec in PROVIDER_SPECS.items() if spec.configured()]
    if has_ollama:
        providers.append("ollama")
    return providers


def pick_default_provider(has_ollama: bool = False) -> str | None:
    configured = set(get_configured_providers(has_ollama=has_ollama))
    for provider in DEFAULT_PROVIDER_ORDER:
        if provider in configured:
            return provider
    if has_ollama:
        return "ollama"
    return None


def provider_supports(provider: str, capability: str) -> bool:
    if provider == "ollama":
        return capability in {"chat", "stream", "local"}
    spec = get_provider_spec(provider)
    return bool(spec and capability in spec.capabilities)


def provider_label(provider: str) -> str:
    if provider == "ollama":
        return "Ollama"
    spec = get_provider_spec(provider)
    return spec.label if spec else provider
