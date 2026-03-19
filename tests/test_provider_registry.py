"""Tests for provider metadata helpers."""

from src.chat.providers import (
    get_configured_providers,
    pick_default_provider,
    provider_health_snapshot,
    provider_label,
    provider_supports,
)


def test_pick_default_provider_prefers_documented_order(monkeypatch):
    for env_var in (
        "HF_TOKEN",
        "OPENROUTER_API_KEY",
        "MISTRAL_API_KEY",
        "GITHUB_API_KEY",
        "COHERE_API_KEY",
        "BYTEZ_API_KEY",
        "AIRFORCE_API_KEY",
        "VERCEL_API_KEY",
        "POLLINATIONS_API_KEY",
        "CLOUDFLARE_API_KEY",
        "CLOUDFLARE_ACCOUNT_ID",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "VERTEX_PROJECT_ID",
    ):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "y")
    assert pick_default_provider() == "gemini"


def test_get_configured_providers_includes_ollama_flag(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    providers = get_configured_providers(has_ollama=True)
    assert "huggingface" in providers
    assert "ollama" in providers


def test_provider_capabilities_and_labels():
    assert provider_supports("openrouter", "fallbacks") is True
    assert provider_supports("airforce", "fallbacks") is True
    assert provider_supports("pollinations", "fallbacks") is True
    assert provider_supports("ollama", "local") is True
    assert provider_label("github") == "GitHub Models"
    assert provider_label("airforce") == "Airforce"
    assert provider_label("pollinations") == "Pollinations"


def test_provider_health_snapshot_reports_missing_env(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    snapshot = provider_health_snapshot()
    huggingface = next(item for item in snapshot if item.key == "huggingface")
    assert huggingface.configured is False
    assert "HF_TOKEN" in huggingface.missing_env_vars
