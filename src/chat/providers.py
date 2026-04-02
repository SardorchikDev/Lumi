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
    context_limit: int
    helper_model_hints: tuple[str, ...] = ()
    heavy_model_hints: tuple[str, ...] = ()
    capability_model_hints: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def configured(self) -> bool:
        return all(os.getenv(var) for var in self.env_vars)


@dataclass(frozen=True)
class ProviderHealth:
    key: str
    label: str
    configured: bool
    missing_env_vars: tuple[str, ...]
    capabilities: tuple[str, ...]
    description: str


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        "gemini",
        "Gemini",
        ("GEMINI_API_KEY",),
        frozenset({"chat", "stream", "long_context", "vision", "audio_transcription", "image_generation"}),
        "Google Gemini models",
        1_000_000,
        ("lite", "flash", "mini"),
        ("pro", "reasoning"),
        (
            ("vision", ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro")),
            ("audio_transcription", ("gemini-2.5-flash", "gemini-2.0-flash")),
            ("image_generation", ("gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview")),
        ),
    ),
    "groq": ProviderSpec(
        "groq",
        "Groq",
        ("GROQ_API_KEY",),
        frozenset({"chat", "stream", "fast", "audio_transcription"}),
        "Fast hosted inference",
        128_000,
        ("instant", "mini", "8b", "20b"),
        ("70b", "120b", "large", "reasoning"),
        (
            ("audio_transcription", ("whisper-large-v3-turbo",)),
        ),
    ),
    "openrouter": ProviderSpec(
        "openrouter",
        "OpenRouter",
        ("OPENROUTER_API_KEY",),
        frozenset({"chat", "stream", "fallbacks", "vision"}),
        "Aggregated hosted models",
        128_000,
        ("mini", "free", "flash", "20b"),
        ("120b", "405b", "70b", "coder", "reasoning"),
    ),
    "mistral": ProviderSpec(
        "mistral",
        "Mistral",
        ("MISTRAL_API_KEY",),
        frozenset({"chat", "stream"}),
        "Mistral hosted models",
        128_000,
        ("small", "nemo"),
        ("large", "codestral"),
    ),
    "huggingface": ProviderSpec(
        "huggingface",
        "HuggingFace",
        ("HF_TOKEN",),
        frozenset({"chat", "stream", "audio_transcription"}),
        "HuggingFace router",
        128_000,
        ("8b", "7b", "mini"),
        ("70b", "72b", "405b"),
    ),
    "github": ProviderSpec(
        "github",
        "GitHub Models",
        ("GITHUB_API_KEY",),
        frozenset({"chat", "stream"}),
        "GitHub-hosted model gateway",
        128_000,
        ("mini", "small"),
        ("4o", "o1", "large", "reasoning"),
    ),
    "cohere": ProviderSpec(
        "cohere",
        "Cohere",
        ("COHERE_API_KEY",),
        frozenset({"chat", "stream"}),
        "Cohere compatibility endpoint",
        128_000,
        ("r7b",),
        ("command-a", "reasoning", "plus"),
    ),
    "bytez": ProviderSpec(
        "bytez",
        "Bytez",
        ("BYTEZ_API_KEY",),
        frozenset({"chat", "stream", "fallbacks"}),
        "Bytez open-source model catalog",
        128_000,
        ("7b", "8b", "mini"),
        ("32b", "72b", "70b", "235b"),
    ),
    "airforce": ProviderSpec(
        "airforce",
        "Airforce",
        ("AIRFORCE_API_KEY",),
        frozenset({"chat", "stream", "fallbacks", "vision"}),
        "Airforce unified AI gateway",
        128_000,
        ("mini", "flash"),
        ("4o", "sonnet", "70b"),
    ),
    "cloudflare": ProviderSpec(
        "cloudflare",
        "Cloudflare",
        ("CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"),
        frozenset({"chat", "stream"}),
        "Workers AI OpenAI-compatible endpoint",
        128_000,
        ("micro", "3b", "20b"),
        ("32b", "70b", "120b"),
    ),
    "vercel": ProviderSpec(
        "vercel",
        "Vercel AI",
        ("VERCEL_API_KEY",),
        frozenset({"chat", "stream", "fallbacks", "vision"}),
        "Vercel AI Gateway",
        128_000,
        ("mini", "flash"),
        ("4.1", "o3", "sonnet", "pro", "70b"),
    ),
    "pollinations": ProviderSpec(
        "pollinations",
        "Pollinations",
        ("POLLINATIONS_API_KEY",),
        frozenset({"chat", "stream", "fallbacks", "vision"}),
        "Pollinations unified generative API",
        128_000,
        ("fast",),
        ("large", "deepseek", "claude", "gemini"),
    ),
    "vertex": ProviderSpec(
        "vertex",
        "Vertex AI",
        ("GOOGLE_APPLICATION_CREDENTIALS", "VERTEX_PROJECT_ID"),
        frozenset({"chat", "stream", "long_context", "vision"}),
        "Google Cloud Vertex AI",
        1_000_000,
        ("flash", "haiku", "small"),
        ("pro", "opus", "sonnet", "70b", "405b", "large"),
        (
            ("vision", ("gemini-2.5-pro-preview-05-06", "gemini-2.5-flash-preview-04-17", "gemini-2.0-flash-001")),
        ),
    ),
}

DEFAULT_PROVIDER_ORDER = [
    "gemini",
    "huggingface",
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


def provider_context_limit(provider: str) -> int:
    if provider == "ollama":
        return 32_000
    spec = get_provider_spec(provider)
    return spec.context_limit if spec else 8_192


def provider_model_hints(provider: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if provider == "ollama":
        return (("mini", "small", "7b", "8b"), ("70b", "coder", "large", "reasoning"))
    spec = get_provider_spec(provider)
    if not spec:
        return ((), ())
    return spec.helper_model_hints, spec.heavy_model_hints


def provider_capability_model_hints(provider: str, capability: str) -> tuple[str, ...]:
    if provider == "ollama":
        return ()
    spec = get_provider_spec(provider)
    if not spec:
        return ()
    mapping = dict(spec.capability_model_hints)
    return mapping.get(capability, ())


def pick_provider_for_capability(
    configured_providers: list[str],
    capability: str,
    *,
    current_provider: str = "",
    preferred_order: tuple[str, ...] = (),
) -> str | None:
    available = [provider for provider in configured_providers if provider_supports(provider, capability)]
    if not available:
        return None
    if current_provider and current_provider in available:
        return current_provider
    for provider in preferred_order:
        if provider in available:
            return provider
    for provider in DEFAULT_PROVIDER_ORDER:
        if provider in available:
            return provider
    return available[0]


def provider_health_snapshot(has_ollama: bool = False) -> list[ProviderHealth]:
    snapshot: list[ProviderHealth] = []
    for key in DEFAULT_PROVIDER_ORDER:
        spec = PROVIDER_SPECS[key]
        missing = tuple(var for var in spec.env_vars if not os.getenv(var))
        snapshot.append(
            ProviderHealth(
                key=key,
                label=spec.label,
                configured=not missing,
                missing_env_vars=missing,
                capabilities=tuple(sorted(spec.capabilities)),
                description=spec.description,
            )
        )
    if has_ollama:
        snapshot.append(
            ProviderHealth(
                key="ollama",
                label="Ollama",
                configured=True,
                missing_env_vars=(),
                capabilities=("chat", "local", "stream"),
                description="Local model runtime",
            )
        )
    return snapshot


def render_provider_health_report(has_ollama: bool = False) -> str:
    lines = ["Provider health"]
    for item in provider_health_snapshot(has_ollama=has_ollama):
        state = "configured" if item.configured else f"missing {', '.join(item.missing_env_vars)}"
        lines.append(f"  {item.label}: {state}")
        lines.append(f"    capabilities: {', '.join(item.capabilities)}")
    return "\n".join(lines)
