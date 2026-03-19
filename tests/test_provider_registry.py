"""Tests for provider metadata helpers."""

from src.chat.providers import (
    get_configured_providers,
    pick_default_provider,
    provider_label,
    provider_supports,
)


def test_pick_default_provider_prefers_documented_order(monkeypatch):
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
    assert provider_supports("ollama", "local") is True
    assert provider_label("github") == "GitHub Models"
