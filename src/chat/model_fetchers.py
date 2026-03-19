"""Live model discovery fetchers for Lumi providers."""

from __future__ import annotations

import json
import os
import urllib.request

from src.chat.model_catalogs import (
    AIRFORCE_MODELS,
    BYTEZ_CLOSED_PREFIXES,
    BYTEZ_MODELS,
    BYTEZ_SKIP_PATTERNS,
    GEMINI_CONFIRMED,
    GEMINI_SKIP,
    GITHUB_MODELS,
    GROQ_DECOMMISSIONED,
    GROQ_FALLBACK,
    OPENROUTER_MODELS,
    OPENROUTER_SKIP,
    OPENROUTER_SKIP_PATTERNS,
    POLLINATIONS_MODELS,
    VERCEL_MODELS,
    VERCEL_SKIP,
)
from src.chat.openai_compat import fetch_openai_compatible_models


def fetch_github_models() -> list[str]:
    try:
        req = urllib.request.Request(
            "https://models.inference.ai.azure.com/models",
            headers={
                "Authorization": f"Bearer {os.getenv('GITHUB_API_KEY', '')}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read())
        live = [item.get("name") or item.get("id", "") for item in data if isinstance(item, dict)]
        live = [model for model in live if model]
        if live:
            ordered = [model for model in GITHUB_MODELS if model in live]
            extras = [model for model in live if model not in set(GITHUB_MODELS)]
            return ordered + extras
    except Exception:
        pass
    return GITHUB_MODELS[:]


def fetch_bytez_models() -> list[str]:
    try:
        key = os.getenv("BYTEZ_API_KEY", "")
        req = urllib.request.Request(
            "https://api.bytez.com/models/v2/list/models?task=chat",
            headers={"Authorization": key},
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read())
        output = data.get("output", [])
        if not output:
            return BYTEZ_MODELS[:]
        live_ids = {
            item.get("modelId", "")
            for item in output
            if item.get("modelId")
            and not any(item.get("modelId", "").startswith(prefix) for prefix in BYTEZ_CLOSED_PREFIXES)
            and not any(skip in item.get("modelId", "").lower() for skip in BYTEZ_SKIP_PATTERNS)
        }
        if not live_ids:
            return BYTEZ_MODELS[:]
        ordered = [model for model in BYTEZ_MODELS if model in live_ids]
        extras = sorted(live_ids - set(BYTEZ_MODELS))
        return ordered + extras if ordered else BYTEZ_MODELS[:]
    except Exception:
        return BYTEZ_MODELS[:]


def fetch_airforce_models() -> list[str]:
    try:
        return fetch_openai_compatible_models(
            base_url="https://api.airforce/v1",
            api_key=os.getenv("AIRFORCE_API_KEY", ""),
            curated=AIRFORCE_MODELS,
        )
    except Exception:
        return AIRFORCE_MODELS[:]


def fetch_pollinations_models() -> list[str]:
    try:
        return fetch_openai_compatible_models(
            base_url="https://gen.pollinations.ai/v1",
            api_key=os.getenv("POLLINATIONS_API_KEY", ""),
            curated=POLLINATIONS_MODELS,
        )
    except Exception:
        return POLLINATIONS_MODELS[:]


def fetch_vercel_models() -> list[str]:
    try:
        key = os.getenv("VERCEL_API_KEY", "")
        req = urllib.request.Request(
            "https://ai-gateway.vercel.sh/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read())
        live = [
            item.get("id", "")
            for item in data.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]
        live = [model for model in live if not any(skip in model.lower() for skip in VERCEL_SKIP)]
        if not live:
            return VERCEL_MODELS[:]
        curated_set = set(VERCEL_MODELS)
        ordered = [model for model in VERCEL_MODELS if model in set(live)]
        extras = [model for model in live if model not in curated_set]
        return ordered + extras
    except Exception:
        return VERCEL_MODELS[:]


def fetch_gemini_models() -> list[str]:
    try:
        key = os.getenv("GEMINI_API_KEY", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
        with urllib.request.urlopen(url, timeout=6) as response:
            data = json.loads(response.read())
        available = {
            item["name"].replace("models/", "")
            for item in data.get("models", [])
            if "generateContent" in item.get("supportedGenerationMethods", [])
        }
        models = [model for model in GEMINI_CONFIRMED if model in available and model not in GEMINI_SKIP]
        return models if models else ["gemini-3.1-flash-lite-preview", "gemini-2.0-flash"]
    except Exception:
        return ["gemini-3.1-flash-lite-preview", "gemini-2.0-flash"]


def fetch_groq_models() -> list[str]:
    try:
        key = os.getenv("GROQ_API_KEY", "")
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
        skip = ("whisper", "tts", "guard", "vision", "embed", "safeguard", "playai")
        live = {
            item["id"]
            for item in data.get("data", [])
            if item.get("active", True)
            and item["id"] not in GROQ_DECOMMISSIONED
            and not any(mark in item["id"].lower() for mark in skip)
        }
        ordered = [model for model in GROQ_FALLBACK if model in live]
        extras = sorted(live - set(GROQ_FALLBACK))
        return ordered + extras if ordered else GROQ_FALLBACK[:]
    except Exception:
        return GROQ_FALLBACK[:]


def fetch_openrouter_models() -> list[str]:
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}",
                "HTTP-Referer": "https://github.com/SardorchikDev/Lumi",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read())

        free = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            if not model_id.endswith(":free"):
                continue
            lowered = model_id.lower()
            if any(skip in lowered for skip in OPENROUTER_SKIP):
                continue
            if any(pattern in lowered for pattern in OPENROUTER_SKIP_PATTERNS):
                continue
            context_length = item.get("context_length", 0) or 0
            if context_length < 1024:
                continue
            free.append((model_id, context_length))

        if not free:
            return OPENROUTER_MODELS[:]

        free_ids = {model_id for model_id, _ in free}
        ordered = [model for model in OPENROUTER_MODELS if model in free_ids]
        curated_set = set(OPENROUTER_MODELS)
        extras = sorted(
            [(model_id, ctx) for model_id, ctx in free if model_id not in curated_set],
            key=lambda item: item[1],
            reverse=True,
        )
        extras_ids = [model_id for model_id, _ in extras]
        result = ordered + extras_ids
        return result if result else OPENROUTER_MODELS[:]
    except Exception:
        return OPENROUTER_MODELS[:]
