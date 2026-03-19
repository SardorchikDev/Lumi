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
    monkeypatch.setattr(hf_client, "_read_catalog_cache", lambda provider: None)
    monkeypatch.setattr(hf_client, "_fetch_vercel_models", list)

    models = hf_client.get_models("vercel")
    assert models == hf_client.VERCEL_MODELS
