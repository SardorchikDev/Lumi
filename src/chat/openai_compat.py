"""Generic helpers for OpenAI-compatible provider discovery."""

from __future__ import annotations

import json
import urllib.request

OPENAI_COMPAT_SKIP = (
    "embed", "embedding", "rerank", "whisper", "tts", "speech",
    "image", "vision", "audio", "video", "transcription",
    "moderation", "dall-e", "flux", "stable-diffusion",
)


def fetch_openai_compatible_models(
    *,
    base_url: str,
    api_key: str,
    curated: list[str],
    headers: dict[str, str] | None = None,
    skip_patterns: tuple[str, ...] = OPENAI_COMPAT_SKIP,
) -> list[str]:
    """Fetch models from a generic OpenAI-compatible /models endpoint."""
    request_headers = dict(headers or {})
    if api_key:
        request_headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(f"{base_url.rstrip('/')}/models", headers=request_headers)
    with urllib.request.urlopen(req, timeout=6) as response:
        data = json.loads(response.read())

    raw_models = []
    if isinstance(data, dict):
        raw_models = data.get("data") or data.get("models") or []
    elif isinstance(data, list):
        raw_models = data

    live = []
    for item in raw_models:
        if isinstance(item, str):
            model_id = item
            active = True
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or ""
            active = item.get("active", True)
        else:
            continue
        if not model_id or not active:
            continue
        if any(skip in model_id.lower() for skip in skip_patterns):
            continue
        live.append(model_id)

    if not live:
        return curated[:]

    curated_set = set(curated)
    ordered = [model for model in curated if model in set(live)]
    extras = [model for model in live if model not in curated_set]
    return ordered + extras if ordered or extras else curated[:]
