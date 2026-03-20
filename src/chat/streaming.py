"""Streaming helpers for Lumi model clients."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

SkipErrorMapper = Callable[[str, str], str | None]
DeltaCallback = Callable[[str], None]
StatusCallback = Callable[[str], None]

SKIP_ERRORS = (
    "404",
    "model_not_found",
    "model does not exist",
    "does not exist",
    "doesn't exist",
    "decommissioned",
    "not found",
    "limit: 0",
    "resource_exhausted",
    "503",
    "502",
    "not supported",
    "no endpoints",
    "unavailable",
    "context length",
    "rate_limit",
    "moderation",
    "content policy",
)


def stream_once(
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    *,
    on_delta: DeltaCallback | None = None,
) -> str:
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    full = ""
    for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta.content
        if not delta:
            continue
        full += delta
        if on_delta is not None:
            on_delta(delta)
    if not full.strip():
        raise RuntimeError("Empty response from model.")
    return full.strip()


def stream_with_fallback(
    *,
    client: Any,
    provider: str,
    messages: list[dict[str, str]],
    model: str,
    max_tokens: int,
    temperature: float,
    attempt_models: list[str],
    supports_fallbacks: bool,
    hf_fallbacks: list[str],
    friendly_error,
    on_delta: DeltaCallback | None = None,
    on_status: StatusCallback | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    stream_fn: Callable[[Any, str, list[dict[str, str]], int, float], str] | None = None,
) -> str:
    if not attempt_models:
        attempt_models = [model]
    stream_fn = stream_fn or (
        lambda active_client, active_model, active_messages, active_max_tokens, active_temperature: stream_once(
            active_client,
            active_model,
            active_messages,
            active_max_tokens,
            active_temperature,
            on_delta=on_delta,
        )
    )
    last_err = "All models failed."
    for index, attempt_model in enumerate(attempt_models):
        try:
            return stream_fn(client, attempt_model, messages, max_tokens, temperature)
        except Exception as exc:
            message = str(exc)
            friendly = friendly_error(message, provider)

            if any(token in message for token in ("API_KEY_INVALID", "API key not valid", "401", "402", "Insufficient Balance")) or "data policy" in message.lower() or "privacy" in message.lower():
                raise RuntimeError(friendly or message) from exc

            if "429" in message and index == 0:
                wait = 15
                match = re.search(r"retry[^0-9]*(\d+)s", message, re.I)
                if match:
                    wait = int(match.group(1)) + 1
                if on_status is not None:
                    on_status(f"rate limited; retrying {attempt_model} in {wait}s")
                sleep_fn(wait)
                try:
                    return stream_fn(client, attempt_model, messages, max_tokens, temperature)
                except Exception:
                    pass

            lowered = message.lower()
            if any(token in lowered for token in SKIP_ERRORS):
                last_err = friendly or f"Model {attempt_model} unavailable, trying next..."
                should_continue = (
                    supports_fallbacks or provider == "huggingface" or bool(hf_fallbacks)
                ) and index < len(attempt_models) - 1
                if should_continue:
                    if on_status is not None:
                        on_status(f"{attempt_model.split('/')[-1]} unavailable; trying next")
                    continue

            raise RuntimeError(friendly or message) from exc

    raise RuntimeError(last_err)
