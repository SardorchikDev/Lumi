"""Tests for env-driven model picker filters."""

from __future__ import annotations

from src.chat.model_filters import (
    filter_models_by_allowlist,
    model_allowlist_env_keys,
    model_allowlist_from_env,
)


def test_model_allowlist_from_env_reads_provider_specific_and_global(monkeypatch):
    monkeypatch.setenv("LUMI_GEMINI_MODELS", "gemini-2.5-flash, gemini-2.5-pro")
    monkeypatch.setenv("LUMI_ALLOWED_MODELS", "gemini-2.0-flash")

    allowlist = model_allowlist_from_env("gemini")

    assert allowlist == ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]


def test_filter_models_by_allowlist_supports_short_names(monkeypatch):
    monkeypatch.setenv("LUMI_HUGGINGFACE_MODELS", "Llama-3.3-70B-Instruct, Qwen2.5-Coder-32B-Instruct")
    models = [
        "meta-llama/Llama-3.3-70B-Instruct",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
    ]

    filtered, allowlist = filter_models_by_allowlist("huggingface", models)

    assert allowlist
    assert filtered == [
        "meta-llama/Llama-3.3-70B-Instruct",
        "Qwen/Qwen2.5-Coder-32B-Instruct",
    ]


def test_filter_models_by_allowlist_no_allowlist_returns_original(monkeypatch):
    for key in model_allowlist_env_keys("gemini"):
        monkeypatch.delenv(key, raising=False)
    models = ["gemini-2.5-flash", "gemini-2.5-pro"]

    filtered, allowlist = filter_models_by_allowlist("gemini", models)

    assert allowlist == []
    assert filtered == models
