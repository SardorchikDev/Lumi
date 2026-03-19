"""Shared runtime helpers for Lumi chat surfaces."""

from __future__ import annotations

from collections.abc import Callable

from src.chat.optimizer import optimize_messages, route_model
from src.prompts.builder import build_messages as _base_build_messages
from src.prompts.builder import is_coding_task, is_file_generation_task


def infer_message_mode(
    history: list[dict[str, str]],
    *,
    search_markers: tuple[str, ...] = (),
    file_markers: tuple[str, ...] = (),
    include_coding_detector: bool = False,
) -> str:
    text = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    lowered = str(text).lower()
    if any(token in lowered for token in ("/review", "review", "security review")):
        return "review"
    if any(token in lowered for token in ("traceback", "stack trace", "assert", "test failed", "/fix", "mypy", "ruff")):
        return "debug"
    if any(token in lowered for token in ("/search", "/web", *search_markers)):
        return "search"
    if any(token in lowered for token in ("/tl;dr", "summarize", "summary")):
        return "summary"
    if any(token in lowered for token in ("/file", "/project", "loaded file", "project loaded", "create a folder", "<file path=", *file_markers)):
        return "files"
    if is_file_generation_task(lowered) or "```" in lowered:
        return "code"
    if include_coding_detector and is_coding_task(lowered):
        return "code"
    return "chat"


def resolve_active_model(
    model: str,
    *,
    get_provider_fn: Callable[[], str],
    get_models_fn: Callable[[str], list[str]],
) -> str:
    active_model = model or "unknown"
    if active_model != "unknown":
        return active_model
    try:
        models = get_models_fn(get_provider_fn())
    except Exception:
        return "unknown"
    return models[0] if models else "unknown"


def build_runtime_messages(
    system_prompt: str,
    history: list[dict[str, str]],
    *,
    model: str = "",
    get_provider_fn: Callable[[], str],
    get_models_fn: Callable[[str], list[str]],
    context_cache,
    telemetry,
    search_markers: tuple[str, ...] = (),
    file_markers: tuple[str, ...] = (),
    include_coding_detector: bool = False,
) -> list[dict[str, str]]:
    active_model = resolve_active_model(
        model,
        get_provider_fn=get_provider_fn,
        get_models_fn=get_models_fn,
    )
    try:
        active_provider = get_provider_fn()
    except Exception:
        active_provider = ""
    mode = infer_message_mode(
        history,
        search_markers=search_markers,
        file_markers=file_markers,
        include_coding_detector=include_coding_detector,
    )
    return optimize_messages(
        _base_build_messages(system_prompt, history),
        active_model,
        mode=mode,
        provider=active_provider,
        context_cache=context_cache,
        telemetry=telemetry,
    )


def route_helper_model(
    current_model: str,
    mode: str,
    *,
    get_provider_fn: Callable[[], str],
    get_models_fn: Callable[[str], list[str]],
) -> str:
    try:
        provider = get_provider_fn()
    except Exception:
        provider = ""
    if current_model == "council":
        try:
            available = get_models_fn(provider or None)
        except Exception:
            return current_model
        return route_model(current_model, available, mode, provider=provider)
    try:
        available = get_models_fn(provider or None)
    except Exception:
        return current_model
    return route_model(current_model, available, mode, provider=provider)
