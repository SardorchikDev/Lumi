"""Model allowlist filters sourced from `.env` variables."""

from __future__ import annotations

import os
import re


def _provider_token(provider: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", (provider or "").upper())


def _parse_model_list(raw: str) -> list[str]:
    normalized = re.sub(r"[\n;]", ",", raw)
    parts = [chunk.strip() for chunk in normalized.split(",")]
    return [chunk for chunk in parts if chunk]


def model_allowlist_env_keys(provider: str) -> list[str]:
    token = _provider_token(provider)
    return [
        f"LUMI_{token}_MODELS",
        f"{token}_MODELS",
        f"{token}_MODEL",
        "LUMI_ALLOWED_MODELS",
        "LUMI_MODELS",
    ]


def model_allowlist_from_env(provider: str) -> list[str]:
    entries: list[str] = []
    seen: set[str] = set()
    for key in model_allowlist_env_keys(provider):
        raw = os.getenv(key, "")
        if not raw:
            continue
        for item in _parse_model_list(raw):
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            entries.append(item)
    return entries


def _resolve_allowlist_entry(entry: str, models: list[str]) -> str | None:
    lowered = entry.lower()
    for model in models:
        if model.lower() == lowered:
            return model
    suffix_matches = [model for model in models if model.split("/")[-1].lower() == lowered]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    contains_matches = [model for model in models if lowered in model.lower()]
    if len(contains_matches) == 1:
        return contains_matches[0]
    return None


def filter_models_by_allowlist(provider: str, models: list[str]) -> tuple[list[str], list[str]]:
    """Return models filtered by env allowlist plus raw allowlist entries.

    If no allowlist entries are configured for this provider, the original model
    list is returned unchanged and the second tuple value is an empty list.
    """
    allowlist = model_allowlist_from_env(provider)
    if not allowlist:
        return models, []
    filtered: list[str] = []
    seen: set[str] = set()
    for entry in allowlist:
        resolved = _resolve_allowlist_entry(entry, models)
        if not resolved:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        filtered.append(resolved)
    return filtered, allowlist
