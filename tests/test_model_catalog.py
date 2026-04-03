"""Tests for model discovery caching and curated fallbacks."""

from __future__ import annotations

import json
import time

from src.chat import hf_client
from src.chat.model_catalogs import AIRFORCE_MODELS, CLAUDE_MODELS, GEMINI_ALL_MODELS, GEMINI_CONFIRMED
from src.chat.model_fetchers import fetch_airforce_models, fetch_claude_models, fetch_gemini_models


def test_discover_models_uses_fresh_disk_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(hf_client, "MODEL_CACHE_DIR", tmp_path)
    cache_path = tmp_path / "openrouter.json"
    cache_path.write_text(
        json.dumps(
            {
                "provider": "openrouter",
                "fetched_at": time.time(),
                "models": ["cached/model"],
            }
        ),
        encoding="utf-8",
    )

    models = hf_client._discover_models("openrouter", ["fallback/model"], lambda: ["live/model"])
    assert models == ["cached/model"]


def test_get_models_falls_back_to_curated_list_when_discovery_is_empty(monkeypatch):
    monkeypatch.setattr(hf_client, "_models_cache", {})
    monkeypatch.setattr(hf_client, "_models_cache_fetched_at", {})
    monkeypatch.setattr(hf_client, "_read_catalog_cache", lambda provider: None)
    monkeypatch.setattr(hf_client, "_fetch_vercel_models", list)

    models = hf_client.get_models("vercel")
    assert models == hf_client.VERCEL_MODELS


def test_get_models_falls_back_to_claude_curated_list_when_discovery_is_empty(monkeypatch):
    monkeypatch.setattr(hf_client, "_models_cache", {})
    monkeypatch.setattr(hf_client, "_models_cache_fetched_at", {})
    monkeypatch.setattr(hf_client, "_read_catalog_cache", lambda provider: None)
    monkeypatch.setattr(hf_client, "_fetch_claude_models", list)

    models = hf_client.get_models("claude")
    assert models == hf_client.CLAUDE_MODELS


def test_get_models_falls_back_to_airforce_curated_list_when_discovery_is_empty(monkeypatch):
    monkeypatch.setattr(hf_client, "_models_cache", {})
    monkeypatch.setattr(hf_client, "_models_cache_fetched_at", {})
    monkeypatch.setattr(hf_client, "_read_catalog_cache", lambda provider: None)
    monkeypatch.setattr(hf_client, "_fetch_airforce_models", list)

    models = hf_client.get_models("airforce")
    assert models == hf_client.AIRFORCE_MODELS
    assert "deepseek-chat" not in models


def test_get_models_falls_back_to_pollinations_curated_list_when_discovery_is_empty(monkeypatch):
    monkeypatch.setattr(hf_client, "_models_cache", {})
    monkeypatch.setattr(hf_client, "_models_cache_fetched_at", {})
    monkeypatch.setattr(hf_client, "_read_catalog_cache", lambda provider: None)
    monkeypatch.setattr(hf_client, "_fetch_pollinations_models", list)

    models = hf_client.get_models("pollinations")
    assert models == hf_client.POLLINATIONS_MODELS


def test_get_models_refreshes_stale_in_memory_cache(monkeypatch):
    monkeypatch.setattr(hf_client, "_models_cache", {"vercel": ["stale/model"]})
    monkeypatch.setattr(
        hf_client,
        "_models_cache_fetched_at",
        {"vercel": time.time() - (hf_client.MODEL_CACHE_TTL_SECONDS + 5)},
    )
    monkeypatch.setattr(hf_client, "_read_catalog_cache", lambda provider: None)
    monkeypatch.setattr(hf_client, "_fetch_vercel_models", lambda: ["fresh/model"])

    models = hf_client.get_models("vercel")
    assert models == ["fresh/model"]


def test_get_models_ignores_legacy_tiny_gemini_memory_cache(monkeypatch):
    monkeypatch.setattr(
        hf_client,
        "_models_cache",
        {"gemini": ["gemini-3.1-flash-lite-preview", "gemini-2.0-flash"]},
    )
    monkeypatch.setattr(
        hf_client,
        "_models_cache_fetched_at",
        {"gemini": time.time()},
    )
    monkeypatch.setattr(hf_client, "_read_catalog_cache", lambda provider: None)
    monkeypatch.setattr(
        hf_client,
        "_provider_catalog",
        lambda provider: hf_client.ProviderCatalog(tuple(GEMINI_ALL_MODELS[:8]), lambda: GEMINI_ALL_MODELS[:8]),
    )

    models = hf_client.get_models("gemini")
    assert models == GEMINI_ALL_MODELS[:8]


def test_pick_startup_model_prefers_gemini_flash_over_catalog_order(monkeypatch):
    for key in ("LUMI_GEMINI_MODELS", "GEMINI_MODELS", "GEMINI_MODEL", "LUMI_ALLOWED_MODELS", "LUMI_MODELS"):
        monkeypatch.delenv(key, raising=False)

    model = hf_client.pick_startup_model(
        "gemini",
        ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    )

    assert model == "gemini-2.5-flash"


def test_pick_startup_model_honors_gemini_allowlist(monkeypatch):
    monkeypatch.setenv("LUMI_GEMINI_MODELS", "gemini-2.5-pro")

    model = hf_client.pick_startup_model(
        "gemini",
        ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    )

    assert model == "gemini-2.5-pro"


def test_discover_models_ignores_legacy_tiny_gemini_disk_cache(monkeypatch):
    monkeypatch.setattr(
        hf_client,
        "_read_catalog_cache",
        lambda provider: ["gemini-3.1-flash-lite-preview", "gemini-2.0-flash"],
    )

    models = hf_client._discover_models("gemini", GEMINI_ALL_MODELS[:8], lambda: GEMINI_ALL_MODELS[:8])
    assert models == GEMINI_ALL_MODELS[:8]


def test_discover_models_ignores_airforce_cache_with_removed_model(monkeypatch):
    monkeypatch.setattr(
        hf_client,
        "_read_catalog_cache",
        lambda provider: ["deepseek-chat", "gpt-4o-mini"],
    )

    models = hf_client._discover_models("airforce", AIRFORCE_MODELS[:], lambda: AIRFORCE_MODELS[:])
    assert models == AIRFORCE_MODELS


def test_make_client_rejects_unknown_provider():
    try:
        hf_client._make_client("nope")
    except ValueError as exc:
        assert "Unknown provider" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_make_client_supports_airforce_and_pollinations(monkeypatch):
    monkeypatch.setenv("AIRFORCE_API_KEY", "airforce-key")
    monkeypatch.setenv("POLLINATIONS_API_KEY", "pollinations-key")

    airforce = hf_client._make_client("airforce")
    pollinations = hf_client._make_client("pollinations")

    assert str(airforce.base_url) == "https://api.airforce/v1/"
    assert str(pollinations.base_url) == "https://gen.pollinations.ai/v1/"


def test_make_client_supports_claude(monkeypatch):
    monkeypatch.setenv("CLAUDE_API_KEY", "claude-key")

    client = hf_client._make_client("claude")

    assert client.base_url == "https://api.anthropic.com/v1"
    assert hasattr(client.chat, "completions")


def test_set_provider_does_not_eagerly_build_vertex_client(monkeypatch):
    monkeypatch.setattr(hf_client, "_active_provider", None)
    monkeypatch.setattr(hf_client, "_active_client", "stale")
    monkeypatch.setattr(hf_client, "_active_client_provider", None)
    monkeypatch.setattr(hf_client, "_active_client_expires_at", None)

    hf_client.set_provider("vertex")

    assert hf_client._active_provider == "vertex"
    assert hf_client._active_client is None
    assert hf_client._active_client_provider == "vertex"
    assert hf_client._active_client_expires_at == 0


def test_get_client_refreshes_expired_vertex_client(monkeypatch):
    monkeypatch.setattr(hf_client, "_active_provider", "vertex")
    monkeypatch.setattr(hf_client, "_active_client", "old-client")
    monkeypatch.setattr(hf_client, "_active_client_provider", "vertex")
    monkeypatch.setattr(hf_client, "_active_client_expires_at", time.time() - 1)
    monkeypatch.setattr(hf_client, "get_provider", lambda: "vertex")
    monkeypatch.setattr(hf_client, "_make_vertex_client", lambda: ("fresh-client", time.time() + 600))

    client = hf_client.get_client()
    assert client == "fresh-client"


def test_chat_stream_uses_fallback_model_without_name_error(monkeypatch):
    monkeypatch.setattr(hf_client, "get_provider", lambda: "huggingface")
    monkeypatch.setattr(hf_client, "HF_FALLBACKS", ["fallback/model"])
    monkeypatch.setattr(hf_client, "get_models", lambda provider=None: ["broken/model", "fallback/model"])
    calls: list[str] = []

    def fake_stream(client, model, messages, max_tokens, temperature):
        calls.append(model)
        if model == "broken/model":
            raise RuntimeError("503 unavailable")
        return "ok"

    monkeypatch.setattr(hf_client, "_do_stream", fake_stream)

    result = hf_client.chat_stream(object(), [{"role": "user", "content": "hi"}], model="broken/model")
    assert result == "ok"
    assert calls == ["broken/model", "fallback/model"]


def test_fetch_gemini_models_falls_back_to_full_curated_list(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)

    models = fetch_gemini_models()
    assert models == GEMINI_ALL_MODELS


def test_fetch_airforce_models_filters_removed_model(monkeypatch):
    monkeypatch.setattr(
        "src.chat.model_fetchers.fetch_openai_compatible_models",
        lambda **kwargs: ["deepseek-chat", "gpt-4o-mini", "gpt-4o"],
    )

    models = fetch_airforce_models()
    assert models == ["gpt-4o-mini", "gpt-4o"]


def test_fetch_claude_models_falls_back_to_curated_list(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)

    models = fetch_claude_models()
    assert models == CLAUDE_MODELS


def test_fetch_gemini_models_keeps_curated_models_even_when_api_returns_small_subset(monkeypatch):
    payload = {
        "models": [
            {"name": "models/gemini-3.1-pro-preview"},
            {"name": "models/gemini-3-flash-preview"},
        ]
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())

    models = fetch_gemini_models()
    assert models[:2] == ["gemini-3.1-pro-preview", "gemini-3-flash-preview"]
    assert "gemini-2.5-flash" in models
    assert "gemini-2.5-flash-image" in models


def test_chat_stream_uses_fallback_gateway_model_chain(monkeypatch):
    monkeypatch.setattr(hf_client, "get_provider", lambda: "pollinations")
    monkeypatch.setattr(hf_client, "get_models", lambda provider=None: ["kimi", "deepseek"])
    calls: list[str] = []

    def fake_stream(client, model, messages, max_tokens, temperature):
        calls.append(model)
        if model == "kimi":
            raise RuntimeError("503 unavailable")
        return "ok"

    monkeypatch.setattr(hf_client, "_do_stream", fake_stream)

    result = hf_client.chat_stream(object(), [{"role": "user", "content": "hi"}], model="kimi")
    assert result == "ok"
    assert calls == ["kimi", "deepseek"]


def test_chat_stream_retries_when_airforce_reports_model_does_not_exist(monkeypatch):
    monkeypatch.setattr(hf_client, "get_provider", lambda: "airforce")
    monkeypatch.setattr(hf_client, "get_models", lambda provider=None: ["stale/model", "gpt-4o-mini"])
    calls: list[str] = []

    def fake_stream(client, model, messages, max_tokens, temperature):
        calls.append(model)
        if model == "stale/model":
            raise RuntimeError("The model does not exist in https://api.airforce\ndiscord.gg/airforce")
        return "ok"

    monkeypatch.setattr(hf_client, "_do_stream", fake_stream)

    result = hf_client.chat_stream(object(), [{"role": "user", "content": "hi"}], model="stale/model")
    assert result == "ok"
    assert calls == ["stale/model", "gpt-4o-mini"]


def test_chat_stream_routes_stale_gateway_model_to_available_model(monkeypatch):
    monkeypatch.setattr(hf_client, "get_provider", lambda: "airforce")
    monkeypatch.setattr(hf_client, "get_models", lambda provider=None: ["gpt-4o-mini", "gpt-4o"])
    calls: list[str] = []
    statuses: list[str] = []

    def fake_stream(client, model, messages, max_tokens, temperature):
        calls.append(model)
        return "ok"

    monkeypatch.setattr(hf_client, "_do_stream", fake_stream)

    result = hf_client.chat_stream(
        object(),
        [{"role": "user", "content": "hi"}],
        model="deepseek-chat",
        on_status=statuses.append,
    )
    assert result == "ok"
    assert calls == ["gpt-4o-mini"]
    assert any("using gpt-4o-mini" in status for status in statuses)


def test_chat_stream_emits_chunks_via_callback(monkeypatch):
    monkeypatch.setattr(hf_client, "get_provider", lambda: "huggingface")
    received: list[str] = []

    def fake_stream(client, model, messages, max_tokens, temperature, on_delta=None):
        if on_delta is not None:
            on_delta("hel")
            on_delta("lo")
        return "hello"

    monkeypatch.setattr(hf_client, "_do_stream", fake_stream)

    result = hf_client.chat_stream(
        object(),
        [{"role": "user", "content": "hi"}],
        model="meta-llama/Llama-3.3-70B-Instruct",
        on_delta=received.append,
    )

    assert result == "hello"
    assert received == ["hel", "lo"]
