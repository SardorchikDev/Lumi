"""Model catalog caching and discovery helpers for Lumi providers."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderCatalog:
    curated: tuple[str, ...]
    fetcher: Callable[[], list[str]] | None = None


class ModelRegistry:
    def __init__(self, *, cache_dir: Path, ttl_seconds: int) -> None:
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self._models_cache: dict[str, list[str]] = {}
        self._fetched_at: dict[str, float] = {}

    def catalog_cache_path(self, provider: str) -> Path:
        return self.cache_dir / f"{provider}.json"

    def read_catalog_cache(self, provider: str) -> list[str] | None:
        path = self.catalog_cache_path(provider)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        ts = float(data.get("fetched_at", 0) or 0)
        models = data.get("models", [])
        if time.time() - ts > self.ttl_seconds:
            return None
        if not isinstance(models, list):
            return None
        return [model for model in models if isinstance(model, str) and model.strip()]

    def write_catalog_cache(self, provider: str, models: list[str]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": provider,
            "fetched_at": time.time(),
            "models": models,
        }
        path = self.catalog_cache_path(provider)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def discover_models(
        self,
        provider: str,
        curated: list[str],
        fetcher: Callable[[], list[str]],
    ) -> list[str]:
        cached = self.read_catalog_cache(provider)
        if cached:
            return cached
        try:
            models = fetcher()
        except Exception:
            models = []
        normalized = [model for model in models if isinstance(model, str) and model.strip()]
        if normalized:
            self.write_catalog_cache(provider, normalized)
            return normalized
        return curated[:]

    def get_memory_cache(self, provider: str) -> list[str] | None:
        cached = self._models_cache.get(provider)
        fetched_at = self._fetched_at.get(provider, 0)
        if cached and (time.time() - fetched_at) <= self.ttl_seconds:
            return cached
        return None

    def set_memory_cache(self, provider: str, models: list[str]) -> None:
        self._models_cache[provider] = models
        self._fetched_at[provider] = time.time()

    def resolve(self, provider: str, catalog: ProviderCatalog) -> list[str]:
        cached = self.get_memory_cache(provider)
        if cached is not None:
            return cached
        if catalog.fetcher is not None:
            models = self.discover_models(provider, list(catalog.curated), catalog.fetcher)
        else:
            models = list(catalog.curated)
        self.set_memory_cache(provider, models)
        return models
