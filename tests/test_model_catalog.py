"""Tests for model discovery caching and curated fallbacks."""

from __future__ import annotations

import json
import time

from src.chat import hf_client


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


def test_get_models_falls_back_to_airforce_curated_list_when_discovery_is_empty(monkeypatch):
    monkeypatch.setattr(hf_client, "_models_cache", {})
    monkeypatch.setattr(hf_client, "_models_cache_fetched_at", {})
    monkeypatch.setattr(hf_client, "_read_catalog_cache", lambda provider: None)
    monkeypatch.setattr(hf_client, "_fetch_airforce_models", list)

    models = hf_client.get_models("airforce")
    assert models == hf_client.AIRFORCE_MODELS


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
