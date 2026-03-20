"""Controller-side helpers extracted from the Lumi TUI app module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.chat.providers import (
    get_provider_spec,
    provider_capability_model_hints,
    provider_context_limit,
    provider_health_snapshot,
    provider_supports,
)
from src.tui.state import Msg


def filesystem_prompt_hint(tui: Any) -> tuple[str, str]:
    pending = tui._pending_file_plan
    if not pending:
        return "", ""
    if isinstance(pending, tuple):
        plan = pending[0]
    else:
        plan = pending.get("plan", {})
    operation = plan.get("operation", "create")
    if operation == "delete":
        return "confirm removal", "y apply · Enter cancel"
    return "confirm filesystem plan", "y apply · Enter cancel"


def cancel_pending_file_plan(tui: Any) -> bool:
    pending = tui._pending_file_plan
    if pending is None:
        return False
    tui._pending_file_plan = None
    if isinstance(pending, tuple):
        plan = pending[0]
    else:
        plan = pending.get("plan", {})
    operation = plan.get("operation", "create")
    label = "Removal" if operation == "delete" else "Filesystem plan"
    tui._sys(f"{label} cancelled.")
    return True


def cancel_transient_state(tui: Any) -> bool:
    changed = False
    if getattr(tui, "browser_visible", False):
        tui.browser_visible = False
        changed = True
    if tui.slash_visible:
        tui.slash_visible = False
        changed = True
    if tui.path_visible or tui.path_hits:
        tui.path_visible = False
        tui.path_hits = []
        tui.path_sel = 0
        changed = True
    if tui.picker_visible:
        tui.picker_visible = False
        tui.picker_query = ""
        tui.picker_preview_lines = []
        tui.picker_stage = "providers"
        tui.picker_provider_key = ""
        changed = True
    pane = getattr(tui, "pane", None)
    if getattr(tui, "pane_active", False) and getattr(pane, "close_on_escape", False):
        tui.clear_pane()
        changed = True
    if tui._cancel_pending_file_plan():
        changed = True
    if tui.buf:
        tui.buf = ""
        tui.cur_pos = 0
        tui.history.reset_navigation()
        changed = True
    return changed


def record_filesystem_action(tui: Any, summary: str, undo_record: dict | None = None) -> None:
    tui._last_filesystem_undo = undo_record
    tui.recent_actions = tui.little_notes.record_action(summary)[:4]


def undo_last_filesystem_action(tui: Any, undo_operation) -> bool:
    if not tui._last_filesystem_undo:
        return False
    restored = undo_operation(tui._last_filesystem_undo)
    tui._last_filesystem_undo = None
    summary = f"Undid filesystem action ({len(restored)} path(s) restored)."
    tui.recent_actions = tui.little_notes.record_action(summary)[:4]
    tui._sys(summary)
    return True


def refresh_browser(tui: Any) -> None:
    try:
        entries = list(os.scandir(tui.browser_cwd))
        dirs = sorted([e for e in entries if e.is_dir()], key=lambda e: e.name.lower())
        files = sorted([e for e in entries if e.is_file()], key=lambda e: e.name.lower())

        tui.browser_items = []
        if tui.browser_cwd != "/":
            tui.browser_items.append(("dir", "..", os.path.dirname(tui.browser_cwd)))

        for directory in dirs:
            tui.browser_items.append(("dir", directory.name, directory.path))
        for file_entry in files:
            tui.browser_items.append(("file", file_entry.name, file_entry.path))
        tui.browser_sel = max(0, min(tui.browser_sel, len(tui.browser_items) - 1))
    except Exception as exc:
        tui._err(f"Browser error: {exc}")
        tui.browser_items = []


def browser_select(tui: Any) -> None:
    if not tui.browser_items:
        return
    sel = tui.browser_sel
    if sel < 0 or sel >= len(tui.browser_items):
        return
    item_type, item_name, item_path = tui.browser_items[sel]

    if item_type == "dir":
        tui.browser_cwd = item_path
        tui.browser_sel = 0
        tui._refresh_browser()
        tui.redraw()
        return

    tui.browser_visible = False
    tui._notify(f"󰈔 Loaded: {item_name}")
    tui._task_executor.submit(tui._execute_command, "/file", item_path)


def update_slash(tui: Any, *, registry, suggest_paths_fn) -> None:
    if tui.buf.startswith("/"):
        query = tui.buf.lower()
        tui.slash_hits = registry.get_hits(query)
        tui.slash_sel = 0
        tui.slash_visible = bool(tui.slash_hits)
        tui.path_visible = False
        tui.path_hits = []
        return
    tui.slash_visible = False
    suggestion = suggest_paths_fn(tui.buf[: tui.cur_pos], Path.cwd())
    if suggestion:
        tui.path_hits = suggestion["items"]
        tui.path_sel = 0
        tui.path_visible = bool(tui.path_hits)
        tui._path_span = (suggestion["start"], suggestion["end"])
    else:
        tui.path_visible = False
        tui.path_hits = []


def hist_nav(tui: Any, direction: int, *, registry, suggest_paths_fn) -> None:
    new_text = tui.history.navigate(tui.buf, direction)
    if new_text is None:
        return
    tui.buf = new_text
    tui.cur_pos = len(tui.buf)
    update_slash(tui, registry=registry, suggest_paths_fn=suggest_paths_fn)


def apply_path_suggestion(tui: Any, suggestion: str, *, registry, suggest_paths_fn) -> None:
    start, end = tui._path_span
    replacement = suggestion[:-1] if suggestion.endswith("/") else suggestion
    tui.buf = tui.buf[:start] + replacement + tui.buf[end:]
    tui.cur_pos = start + len(replacement)
    tui.path_visible = False
    tui.path_hits = []
    update_slash(tui, registry=registry, suggest_paths_fn=suggest_paths_fn)


def run_file_agent(
    tui: Any,
    user_input: str,
    *,
    generate_delete_plan_fn,
    generate_transfer_plan_fn,
    generate_file_plan_fn,
    is_delete_request_fn,
    is_move_request_fn,
    is_copy_request_fn,
    is_rename_request_fn,
    is_create_request_fn,
    get_provider_fn,
    get_models_fn,
) -> None:
    tui._sys("◆  generating file plan…")
    tui.redraw()
    workspace = Path.cwd().resolve()
    plan = None
    label = "File plan"
    if is_delete_request_fn(user_input):
        plan = generate_delete_plan_fn(user_input)
        label = "Removal plan"
    elif (
        is_move_request_fn(user_input)
        or is_copy_request_fn(user_input)
        or is_rename_request_fn(user_input)
    ):
        plan = generate_transfer_plan_fn(user_input)
        label = "Transfer plan"
    elif is_create_request_fn(user_input):
        label = "File plan"

    if plan is None and is_create_request_fn(user_input):
        try:
            model = tui.current_model
            if model == "council":
                model = get_models_fn(get_provider_fn())[0]
            plan = generate_file_plan_fn(user_input, tui.client, model)
        except Exception as exc:
            tui._err(f"File plan failed: {exc}")
            tui.set_busy(False)
            return
        if plan:
            plan["operation"] = "create"
    if not plan:
        tui._err(f"Couldn't generate a {label.lower()}.")
        tui.set_busy(False)
        return
    tui._queue_filesystem_plan(plan, base_dir=workspace, label=label)


def run_message(
    tui: Any,
    user_input: str,
    *,
    is_complex_coding_task_fn,
    is_coding_task_fn,
    is_file_generation_task_fn,
    needs_plan_first_fn,
    is_filesystem_request_fn,
    detect_emotion_fn,
    emotion_hint_fn,
    should_search_fn,
    search_fn,
    plugin_dispatch_fn,
    get_provider_fn,
    get_models_fn,
    session_save_fn,
    auto_extract_facts_fn,
    build_messages_fn,
    log,
) -> None:
    tui.set_busy(True)
    tui.scroll_offset = 0

    is_code = is_complex_coding_task_fn(user_input) or is_coding_task_fn(user_input)
    is_files = is_file_generation_task_fn(user_input)
    system_prompt = tui._make_system_prompt(coding_mode=is_code, file_mode=is_files)

    if needs_plan_first_fn(user_input) and is_files:
        system_prompt += "\n\n[INSTRUCTION: Output a brief one-paragraph plan. Then write each file completely.]"
    if is_filesystem_request_fn(user_input):
        tui._run_file_agent(user_input, system_prompt)
        return

    emotion = detect_emotion_fn(user_input)
    augmented = user_input
    if emotion:
        hint = emotion_hint_fn(emotion)
        if hint:
            augmented = hint + augmented

    if tui.response_mode == "short":
        augmented += "\n\n[Reply concisely — 2-3 sentences max.]"
    elif tui.response_mode == "detailed":
        augmented += "\n\n[Reply in detail — be thorough and comprehensive.]"
    elif tui.response_mode == "bullets":
        augmented += "\n\n[Reply using bullet points only.]"
    tui.response_mode = None

    if should_search_fn(user_input):
        tui._sys("◆  searching the web…")
        tui.redraw()
        try:
            results_text = search_fn(user_input, fetch_top=True)
            if results_text and not results_text.startswith("[No"):
                augmented = f"{augmented}\n\n[Web search results:]\n{results_text}\n[Use the above to inform your answer. Cite sources.]"
                tui._sys("◆  found web results")
        except Exception:
            log.exception("Web search failed")

    cmd = user_input.split()[0] if user_input.startswith("/") else None
    if cmd:
        plugin_args = user_input.split(None, 1)[1] if len(user_input.split(None, 1)) > 1 else ""
        try:
            provider = get_provider_fn()
        except Exception:
            provider = ""
        handled, plug_result = plugin_dispatch_fn(
            cmd,
            plugin_args,
            provider=provider,
            model=tui.current_model,
            name=tui.name,
            workspace=Path.cwd(),
        )
        if handled:
            if plug_result:
                tui._sys(plug_result)
            tui.set_busy(False)
            return

    if len(tui.memory.get()) > 15 and tui.turns % 10 == 0 and tui.turns > 0:
        def _compress() -> None:
            try:
                snapshot = tui.memory.get()[:-4]
                if not snapshot:
                    return
                model = tui.current_model if tui.current_model != "council" else get_models_fn(get_provider_fn())[0]
                summary = tui._silent_call(
                    "Summarize this conversation briefly:\n\n"
                    + "\n".join(f"{item['role']}: {item['content'][:200]}" for item in snapshot),
                    model,
                    200,
                )
                if summary:
                    with tui._state_lock:
                        tui.memory.replace_with_summary(summary, tail_messages=4)
                        tui._cached_tok_len = -1
                    log.debug("Memory compressed to summary + last 4 messages")
            except Exception:
                log.exception("Memory compression failed")

        tui._task_executor.submit(_compress)

    tui.last_msg = user_input
    tui.store.add(Msg("user", user_input))
    tui.memory.add("user", augmented)
    messages = build_messages_fn(system_prompt, tui.memory.get())
    tui.redraw()

    raw_reply = tui._tui_stream(messages, tui.current_model)
    tui.memory.replace_last("user", user_input)
    tui.memory.add("assistant", raw_reply)

    tui.prev_reply = tui.last_reply
    tui.last_reply = raw_reply
    tui.turns += 1
    tui.set_busy(False)

    if tui.turns % 5 == 0:
        tui._task_executor.submit(lambda: session_save_fn(tui.memory.get()))
    if tui.turns % 8 == 0:
        def _bg_remember() -> None:
            try:
                if auto_extract_facts_fn(tui.client, tui.current_model, tui.memory.get()):
                    with tui._state_lock:
                        tui.system_prompt = tui._make_system_prompt()
                    log.debug("Auto-remember: system prompt updated")
            except Exception:
                log.exception("Auto-remember failed")

        tui._task_executor.submit(_bg_remember)


def queue_filesystem_plan(
    tui: Any,
    plan: dict,
    *,
    base_dir: str | Path,
    label: str,
    inspect_operation_plan_fn,
) -> bool:
    base_path = Path(base_dir).expanduser().resolve()
    try:
        inspection = inspect_operation_plan_fn(plan, base_path)
    except Exception as exc:
        tui._err(f"{label} failed: {exc}")
        tui.set_busy(False)
        return False

    lines = [f"{label} → {base_path}"]
    lines.extend(f"  {line}" for line in inspection["summary_lines"])
    lines.extend(f"  {line}" for line in inspection["detail_lines"])
    if inspection["preview_lines"]:
        lines.append("")
        lines.append("  preview")
        lines.extend(inspection["preview_lines"][:32])
    lines.append("")
    lines.append("Type 'y' or 'yes' to apply. Press Enter or type 'n' to cancel.")

    tui._sys("\n".join(lines))
    tui.set_busy(False)
    tui._pending_file_plan = {"plan": plan, "base_dir": str(base_path), "inspection": inspection}
    return True


def consume_pending_file_plan(
    tui: Any,
    text: str,
    *,
    execute_operation_plan_fn,
) -> bool:
    if tui._pending_file_plan is None:
        return False

    payload = tui._pending_file_plan
    tui._pending_file_plan = None
    return _consume_pending_payload(tui, payload, text, execute_operation_plan_fn)


def _consume_pending_payload(tui: Any, payload, text: str, execute_operation_plan_fn) -> bool:
    tui.store.add(Msg("user", text))
    if isinstance(payload, tuple):
        plan, base_dir = payload
        inspection = None
    else:
        plan = payload.get("plan", {})
        base_dir = payload.get("base_dir", str(Path.cwd().resolve()))
        inspection = payload.get("inspection")

    accepted = {"y", "yes", "confirm", "apply"}
    cancelled = {"", "n", "no", "cancel"}
    normalized = text.strip().lower()
    if normalized in cancelled:
        action = "Removal" if plan.get("operation") == "delete" else "File plan"
        tui._sys(f"{action} cancelled.")
        return True
    if normalized not in accepted:
        tui._sys("Filesystem action cancelled.")
        return True

    try:
        result = execute_operation_plan_fn(plan, base_dir)
    except Exception as exc:
        action = {
            "delete": "Removal",
            "move": "Move",
            "copy": "Copy",
            "rename": "Rename",
        }.get(plan.get("operation"), "File creation")
        tui._err(f"{action} failed: {exc}")
        return True
    detail_lines = result.get("details") or (inspection or {}).get("detail_lines") or []
    rendered = [result["summary"]]
    if detail_lines:
        rendered.append("")
        rendered.extend(detail_lines[:3])
    tui._sys("\n".join(rendered))
    tui._record_filesystem_action(result["summary"], result.get("undo"))
    return True


def do_retry(tui: Any, *, build_messages_fn) -> None:
    if tui.busy:
        return
    for message in reversed(tui.memory.get()):
        if message["role"] != "user":
            continue
        text = message["content"]
        tui.memory.remove_last_exchange()
        tui.turns = max(0, tui.turns - 1)
        tui.set_busy(True)
        tui.store.add(Msg("user", text))
        tui.memory.add("user", text)
        messages = build_messages_fn(tui.system_prompt, tui.memory.get())
        raw = tui._tui_stream(messages, tui.current_model)
        tui.memory.replace_last("user", text)
        tui.memory.add("assistant", raw)
        tui.prev_reply = tui.last_reply
        tui.last_reply = raw
        tui.turns += 1
        tui.set_busy(False)
        return
    tui._err("Nothing to retry.")


def _picker_selectable_indexes(items: list[dict[str, Any]]) -> list[int]:
    return [index for index, item in enumerate(items) if item.get("kind") not in {"header", "hint"}]


def _picker_first_selectable(items: list[dict[str, Any]]) -> int:
    selectable = _picker_selectable_indexes(items)
    return selectable[0] if selectable else 0


def _picker_move_selection(tui: Any, delta: int) -> None:
    selectable = _picker_selectable_indexes(tui.picker_items)
    if not selectable:
        tui.picker_sel = 0
        return
    if tui.picker_sel not in selectable:
        tui.picker_sel = selectable[0]
        return
    current = selectable.index(tui.picker_sel)
    next_index = max(0, min(len(selectable) - 1, current + delta))
    tui.picker_sel = selectable[next_index]
    _update_picker_preview(tui)


def _model_traits(provider: str, model: str) -> list[str]:
    lowered = model.lower()
    traits: list[str] = []
    if any(token in lowered for token in ("flash", "lite", "mini", "small", "instant", "fast", "8b", "7b", "3b")):
        traits.append("fast")
    if any(token in lowered for token in ("code", "coder", "codestral", "devstral")):
        traits.append("coding")
    if any(token in lowered for token in ("reason", "r1", "o1", "o3", "deepthink", "thinking")):
        traits.append("reasoning")
    if provider_supports(provider, "long_context") or any(token in lowered for token in ("128k", "200k", "1m", "32k")):
        traits.append("long")
    if any(token in lowered for token in ("vision", "vl", "image")):
        traits.append("vision")
    if provider == "ollama":
        traits.append("local")
    return traits or ["general"]


def _unique_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            ordered.append(tag)
    return ordered


def _model_tags(provider: str, model: str) -> list[str]:
    lowered = model.lower()
    tags: list[str] = []
    traits = _model_traits(provider, model)
    vision_hints = set(provider_capability_model_hints(provider, "vision"))
    audio_hints = set(provider_capability_model_hints(provider, "audio_transcription"))
    image_hints = set(provider_capability_model_hints(provider, "image_generation"))

    if model in image_hints or any(token in lowered for token in ("image", "imagen", "nano-banana")):
        tags.append("image")
    if model in vision_hints or any(token in lowered for token in ("vision", "vl", "multimodal", "omni")):
        tags.append("vision")
    if model in audio_hints or any(token in lowered for token in ("audio", "speech", "transcribe", "whisper")):
        tags.append("audio")
    if "fast" in traits:
        tags.append("fast")
    if "reasoning" in traits:
        tags.append("reasoning")
    if "coding" in traits:
        tags.append("best coding")
    if "long" in traits:
        tags.append("long")
    if "local" in traits:
        tags.append("local")
    return _unique_tags(tags or ["general"])


def _model_meta(provider: str, model: str) -> str:
    context_limit = provider_context_limit(provider)
    if context_limit >= 1_000_000:
        context_label = "1M ctx"
    elif context_limit >= 128_000:
        context_label = "128k ctx"
    elif context_limit >= 32_000:
        context_label = "32k ctx"
    else:
        context_label = f"{context_limit // 1000}k ctx"
    tags = _model_tags(provider, model)
    return " · ".join([context_label, *tags[:3]])


def _model_group(provider: str, model: str, *, recent: set[str], favorites: set[str], current_model: str, helper_hints: tuple[str, ...], heavy_hints: tuple[str, ...]) -> str:
    lowered = model.lower()
    if model == current_model:
        return "Current"
    if model in favorites:
        return "Favorites"
    if model in recent:
        return "Recent"
    if any(hint in lowered for hint in helper_hints + heavy_hints):
        return "Recommended"
    tags = _model_tags(provider, model)
    if "image" in tags:
        return "Image"
    if "vision" in tags:
        return "Vision"
    if "audio" in tags:
        return "Audio"
    if "fast" in tags:
        return "Fast"
    if "best coding" in tags:
        return "Coding"
    if "reasoning" in tags:
        return "Reasoning"
    if "long" in tags:
        return "Long context"
    return "All models"


def _provider_preview_lines(provider: str, *, provider_names: dict[str, str], health_by_key: dict[str, Any]) -> list[str]:
    health = health_by_key.get(provider)
    if provider == "council":
        return [
            "Provider: Council",
            "Capabilities: multi-agent orchestration",
            "Use when you want several models to debate a task.",
        ]
    if health is None:
        return [f"Provider: {provider_names.get(provider, provider)}"]
    context_limit = provider_context_limit(provider)
    context_label = "1M" if context_limit >= 1_000_000 else f"{context_limit // 1000}k"
    status = "configured" if health.configured else f"missing: {', '.join(health.missing_env_vars)}"
    return [
        f"Provider: {health.label}",
        f"Context: {context_label} tokens",
        f"Capabilities: {', '.join(health.capabilities)}",
        f"Status: {status}",
    ]


def _model_preview_lines(provider: str, model: str, *, provider_names: dict[str, str], recommended: bool, current: bool) -> list[str]:
    spec = get_provider_spec(provider)
    reason = "recommended for this provider" if recommended else "available model"
    if current:
        reason = "currently active"
    env_hint = ", ".join(spec.env_vars) if spec is not None else "runtime configured"
    tags = ", ".join(_model_tags(provider, model))
    return [
        f"Model: {model}",
        f"Provider: {provider_names.get(provider, provider)}",
        f"Profile: {_model_meta(provider, model)}",
        f"Tags: {tags}",
        f"Why: {reason}",
        f"Setup: {env_hint}",
    ]


def _rebuild_picker(
    tui: Any,
    *,
    get_available_providers_fn,
    get_provider_fn,
    get_models_fn,
    provider_names: dict[str, str],
) -> None:
    available = get_available_providers_fn()
    health_snapshot = provider_health_snapshot(has_ollama="ollama" in available)
    health_by_key = {item.key: item for item in health_snapshot}
    tui.picker_health_by_key = health_by_key
    query = tui.picker_query.strip().lower()

    if tui.picker_stage == "providers":
        items: list[dict[str, Any]] = []
        current_provider = "council" if tui.current_model == "council" else get_provider_fn()
        configured = [item for item in health_snapshot if item.configured and item.key in available]
        unavailable = [item for item in health_snapshot if not item.configured]
        if configured:
            items.append({"kind": "header", "label": "Configured providers"})
            providers = configured
            if query:
                providers = [
                    item for item in providers
                    if query in item.label.lower()
                    or query in item.key.lower()
                    or query in item.description.lower()
                    or any(query in capability for capability in item.capabilities)
                ]
            for item in providers:
                meta = f"{item.description} · {provider_context_limit(item.key) // 1000}k ctx"
                if item.key == current_provider:
                    meta = "current · " + meta
                items.append(
                    {
                        "kind": "provider",
                        "value": item.key,
                        "label": provider_names.get(item.key, item.label),
                        "meta": meta,
                        "current": item.key == current_provider,
                        "disabled": False,
                    }
                )
        if len(configured) >= 2 and (not query or "council".startswith(query) or "multi-agent".find(query) != -1):
            if items:
                items.append({"kind": "header", "label": "Recommended"})
            items.append(
                {
                    "kind": "provider",
                    "value": "council",
                    "label": "⚡ Council",
                    "meta": "multi-agent debate · strongest routing",
                    "current": tui.current_model == "council",
                    "disabled": False,
                }
            )
        if unavailable and not query:
            items.append({"kind": "header", "label": "Requires setup"})
            for item in unavailable[:6]:
                items.append(
                    {
                        "kind": "provider",
                        "value": item.key,
                        "label": provider_names.get(item.key, item.label),
                        "meta": f"missing {', '.join(item.missing_env_vars)}",
                        "current": False,
                        "disabled": True,
                    }
                )
        if not items:
            items = [{"kind": "hint", "label": "No providers match this filter."}]
        tui.picker_items = items
        tui.picker_sel = _picker_first_selectable(items)
        tui.picker_empty_message = "Type to filter providers"
        _update_picker_preview(tui, provider_names=provider_names, health_by_key=health_by_key)
        return

    provider = tui.picker_provider_key or get_provider_fn()
    items = [{"kind": "action", "value": "__back__", "label": "← back to providers", "meta": provider_names.get(provider, provider)}]
    try:
        models = get_models_fn(provider)
    except Exception as exc:
        tui.picker_items = items + [{"kind": "hint", "label": f"Could not load models: {exc}"}]
        tui.picker_sel = 0
        tui.picker_empty_message = "Model loading failed"
        _update_picker_preview(tui, provider_names=provider_names, health_by_key=health_by_key)
        return

    recent = set(tui.little_notes.recent_models_for_provider(provider, limit=8))
    favorites = set(tui.little_notes.favorite_models_for_provider(provider))
    helper_hints, heavy_hints = ((), ())
    spec = get_provider_spec(provider)
    if spec is not None:
        helper_hints = spec.helper_model_hints
        heavy_hints = spec.heavy_model_hints

    filtered = []
    for model in models:
        searchable = " ".join([model.lower(), _model_meta(provider, model), " ".join(_model_tags(provider, model))])
        if query and query not in searchable:
            continue
        filtered.append(model)

    grouped: dict[str, list[str]] = {}
    for model in filtered:
        group = _model_group(
            provider,
            model,
            recent=recent,
            favorites=favorites,
            current_model=tui.current_model if provider == get_provider_fn() else "",
            helper_hints=helper_hints,
            heavy_hints=heavy_hints,
        )
        grouped.setdefault(group, []).append(model)

    order = (
        "Current",
        "Favorites",
        "Recent",
        "Recommended",
        "Image",
        "Vision",
        "Audio",
        "Fast",
        "Coding",
        "Reasoning",
        "Long context",
        "All models",
    )
    for group in order:
        group_models = grouped.get(group)
        if not group_models:
            continue
        items.append({"kind": "header", "label": group})
        for model in group_models:
            current = provider == get_provider_fn() and model == tui.current_model
            recommended = group == "Recommended"
            label = model.split("/")[-1]
            if model in favorites:
                label = "★ " + label
            meta = _model_meta(provider, model)
            if current:
                meta = "current · " + meta
            elif recommended:
                meta = "recommended · " + meta
            items.append(
                {
                    "kind": "model",
                    "value": model,
                    "label": label,
                    "meta": meta,
                    "tags": _model_tags(provider, model),
                    "provider": provider,
                    "recommended": recommended,
                    "current": current,
                }
            )

    if len(items) == 1:
        items.append({"kind": "hint", "label": "No models match this filter."})
    tui.picker_items = items
    tui.picker_sel = _picker_first_selectable(items)
    tui.picker_empty_message = "Type to filter models"
    _update_picker_preview(tui, provider_names=provider_names, health_by_key=health_by_key)


def _update_picker_preview(tui: Any, *, provider_names: dict[str, str] | None = None, health_by_key: dict[str, Any] | None = None) -> None:
    provider_names = provider_names or getattr(tui, "picker_provider_names", {}) or {}
    health_by_key = health_by_key or getattr(tui, "picker_health_by_key", {}) or {}
    if not tui.picker_items:
        tui.picker_preview_lines = []
        return
    try:
        item = tui.picker_items[tui.picker_sel]
    except IndexError:
        tui.picker_preview_lines = []
        return
    kind = item.get("kind")
    if kind == "provider":
        tui.picker_preview_lines = _provider_preview_lines(item["value"], provider_names=provider_names, health_by_key=health_by_key)
    elif kind == "model":
        tui.picker_preview_lines = _model_preview_lines(
            item.get("provider", tui.picker_provider_key),
            item["value"],
            provider_names=provider_names,
            recommended=bool(item.get("recommended")),
            current=bool(item.get("current")),
        )
    elif kind == "action":
        tui.picker_preview_lines = ["Back to providers", "Use this to choose a different gateway."]
    else:
        tui.picker_preview_lines = [item.get("label", "")]


def open_picker(
    tui: Any,
    *,
    get_available_providers_fn,
    get_provider_fn,
    get_models_fn,
    provider_names: dict[str, str],
    log,
) -> None:
    try:
        tui.picker_provider_names = dict(provider_names)
        tui.picker_query = ""
        tui.picker_stage = "providers"
        tui.picker_provider_key = ""
        _rebuild_picker(
            tui,
            get_available_providers_fn=get_available_providers_fn,
            get_provider_fn=get_provider_fn,
            get_models_fn=get_models_fn,
            provider_names=provider_names,
        )
    except Exception:
        log.exception("Picker open failed")
        tui.picker_items = [{"kind": "hint", "label": "Picker failed to load."}]
        tui.picker_sel = 0
        tui.picker_preview_lines = []
    tui.picker_visible = True


def refresh_picker(
    tui: Any,
    *,
    get_available_providers_fn,
    get_provider_fn,
    get_models_fn,
    provider_names: dict[str, str],
    log,
) -> None:
    try:
        tui.picker_provider_names = dict(provider_names)
        _rebuild_picker(
            tui,
            get_available_providers_fn=get_available_providers_fn,
            get_provider_fn=get_provider_fn,
            get_models_fn=get_models_fn,
            provider_names=provider_names,
        )
    except Exception:
        log.exception("Picker refresh failed")
        tui.picker_items = [{"kind": "hint", "label": "Picker failed to refresh."}]
        tui.picker_sel = 0
        tui.picker_preview_lines = []


def confirm_picker(
    tui: Any,
    *,
    get_available_providers_fn,
    set_provider_fn,
    get_client_fn,
    get_models_fn,
    get_provider_fn,
    provider_names: dict[str, str],
    log,
) -> None:
    if not tui.picker_items:
        tui.picker_visible = False
        return
    item = tui.picker_items[tui.picker_sel]
    kind = item.get("kind")
    value = item.get("value")
    if kind == "header":
        return
    if kind == "hint":
        return
    if kind == "action" and value == "__back__":
        tui.picker_stage = "providers"
        tui.picker_provider_key = ""
        _rebuild_picker(
            tui,
            get_available_providers_fn=get_available_providers_fn,
            get_provider_fn=get_provider_fn,
            get_models_fn=get_models_fn,
            provider_names=provider_names,
        )
        return
    if kind == "provider":
        if item.get("disabled"):
            tui._notify(f"Missing setup for {item.get('label')}", duration=2.0)
            return
        if value == "council":
            tui.current_model = "council"
            tui.little_notes.record_model("council", "council")
            tui._notify("Model → Council")
            tui.picker_visible = False
        else:
            try:
                tui.picker_stage = "models"
                tui.picker_provider_key = value
                _rebuild_picker(
                    tui,
                    get_available_providers_fn=get_available_providers_fn,
                    get_provider_fn=get_provider_fn,
                    get_models_fn=get_models_fn,
                    provider_names=provider_names,
                )
                return
            except Exception:
                log.exception("Provider switch failed")
                tui._err(f"Provider failed: {value}")
                return
    elif kind == "model":
        provider = item.get("provider", tui.picker_provider_key)
        try:
            set_provider_fn(provider)
            tui.client = get_client_fn()
        except Exception:
            log.exception("Provider activation failed")
            tui._err(f"Could not activate provider: {provider_names.get(provider, provider)}")
            return
        tui.current_model = value
        tui.little_notes.record_model(provider, tui.current_model)
        tui._notify(f"Model → {value.split('/')[-1]}")
    try:
        provider_key = "council" if tui.current_model == "council" else get_provider_fn()
    except Exception:
        provider_key = "huggingface"
    if tui.current_model != "council":
        tui.little_notes.record_model(provider_key, tui.current_model)
    tui.picker_visible = False
    tui.picker_query = ""


def execute_command(tui: Any, cmd, arg, *, registry, plugin_dispatch_fn) -> None:
    if cmd in registry.commands:
        if cmd not in {"/help"}:
            tui.recent_commands = tui.little_notes.record_command(cmd)[:3]
        registry.commands[cmd]["func"](tui, arg)
        return
    handled, plugin_result = plugin_dispatch_fn(
        cmd,
        arg,
        client=tui.client,
        model=tui.current_model,
        memory=tui.memory,
        system_prompt=tui.system_prompt,
        name=tui.name,
    )
    if handled:
        tui.recent_commands = tui.little_notes.record_command(cmd)[:3]
        if plugin_result:
            tui._sys(plugin_result)
        return
    tui._err(f"Unknown command: {cmd}  (try /help)")


def handle_key(
    tui: Any,
    key,
    *,
    term_size_fn,
    registry,
    suggest_paths_fn,
) -> None:
    if not key:
        return
    if key == "ESC":
        tui._cancel_transient_state()
        return
    if key in ("CTRL_Q", "CTRL_C"):
        with tui._state_lock:
            tui._running = False
        return
    if key == "CTRL_G":
        tui.show_starter_panel = not tui.show_starter_panel
        tui.redraw()
        return
    if key == "CTRL_N":
        if not tui.slash_visible:
            tui._open_picker()
        return
    if tui.picker_visible and key == "CTRL_U":
        tui.picker_query = ""
        tui._refresh_picker()
        return
    if key == "CTRL_L":
        tui.memory.clear()
        tui.store.clear()
        tui.agents.clear()
        tui.last_msg = tui.last_reply = tui.prev_reply = None
        tui.turns = 0
        tui.set_busy(False)
        tui.buf = ""
        tui.cur_pos = tui.scroll_offset = 0
        tui.slash_visible = tui.picker_visible = False
        tui._sys("Chat cleared.")
        return
    if key == "CTRL_R":
        if not (tui._active_task and not tui._active_task.done()):
            tui._active_task = tui._task_executor.submit(tui._do_retry)
        return
    if key == "CTRL_U":
        tui.buf = ""
        tui.cur_pos = 0
        tui.slash_visible = False
        return
    if key in ("SHIFT_UP", "CTRL_UP"):
        tui.scroll_offset += 3
        return
    if key in ("SHIFT_DOWN", "CTRL_DOWN"):
        tui.scroll_offset = max(0, tui.scroll_offset - 3)
        return

    if key == "UP":
        if getattr(tui, "browser_visible", False):
            tui.browser_sel = max(0, tui.browser_sel - 1)
            tui.redraw()
            return
        if tui.slash_visible:
            tui.slash_sel = max(0, tui.slash_sel - 1)
        elif tui.path_visible:
            tui.path_sel = max(0, tui.path_sel - 1)
        elif tui.picker_visible:
            _picker_move_selection(tui, -1)
        else:
            tui._hist_nav(-1)
        return
    if key == "DOWN":
        if getattr(tui, "browser_visible", False):
            tui.browser_sel = min(len(tui.browser_items) - 1, tui.browser_sel + 1)
            tui.redraw()
            return
        if tui.slash_visible:
            tui.slash_sel = min(len(tui.slash_hits) - 1, tui.slash_sel + 1)
        elif tui.path_visible:
            tui.path_sel = min(len(tui.path_hits) - 1, tui.path_sel + 1)
        elif tui.picker_visible:
            _picker_move_selection(tui, 1)
        else:
            tui._hist_nav(1)
        return
    if key == "LEFT" and tui.picker_visible:
        if tui.picker_stage == "models":
            tui.picker_stage = "providers"
            tui.picker_provider_key = ""
            tui.picker_query = ""
            tui._refresh_picker()
        return
    if key == "RIGHT" and tui.picker_visible:
        tui._confirm_picker()
        return

    if key == "PGUP":
        rows, _ = term_size_fn()
        tui.scroll_offset += max(1, rows - 6)
        return
    if key == "PGDN":
        rows, _ = term_size_fn()
        tui.scroll_offset = max(0, tui.scroll_offset - max(1, rows - 6))
        return
    if key == "TAB":
        if tui.slash_visible and tui.slash_hits:
            cmd = tui.slash_hits[tui.slash_sel][0]
            tui.buf = cmd + " "
            tui.cur_pos = len(tui.buf)
            tui.slash_visible = False
            tui.path_visible = False
        elif tui.path_visible and tui.path_hits:
            tui._apply_path_suggestion(tui.path_hits[tui.path_sel])
        elif tui.picker_visible:
            _picker_move_selection(tui, 1)
        return

    if key == "ENTER":
        if getattr(tui, "browser_visible", False):
            tui._browser_select()
            return
        if tui.picker_visible:
            tui._confirm_picker()
            return
        if tui.slash_visible and tui.slash_hits:
            cmd = tui.slash_hits[tui.slash_sel][0]
            tui.slash_visible = False
            tui.buf = ""
            tui.cur_pos = 0
            tui._execute_command(cmd, "")
            return
        if tui.multiline and tui._pending_file_plan is None:
            tui.buf = tui.buf[: tui.cur_pos] + "\n" + tui.buf[tui.cur_pos :]
            tui.cur_pos += 1
            tui.path_visible = False
            tui.slash_visible = False
            return
        text = tui.buf.strip()
        tui.buf = ""
        tui.cur_pos = 0
        tui.slash_visible = False
        tui.history.reset_navigation()
        tui.path_visible = False
        if tui._pending_file_plan is not None and not tui.busy and not text:
            tui._consume_pending_file_plan("")
            return
        if text and not tui.busy:
            if tui._consume_pending_file_plan(text):
                return
            tui.history.append(text)
            if text.startswith("/"):
                parts = text.split(None, 1)
                tui._execute_command(parts[0].lower(), parts[1] if len(parts) > 1 else "")
            else:
                if tui._active_task and not tui._active_task.done():
                    tui._err("Still busy — wait for the current reply.")
                else:
                    tui._active_task = tui._task_executor.submit(tui._run_message, text)
        return
    if key == "CTRL_D":
        text = tui.buf.strip()
        tui.buf = ""
        tui.cur_pos = 0
        tui.slash_visible = False
        tui.history.reset_navigation()
        tui.path_visible = False
        if tui._pending_file_plan is not None and not tui.busy and not text:
            tui._consume_pending_file_plan("")
            return
        if text and not tui.busy:
            if tui._consume_pending_file_plan(text):
                return
            tui.history.append(text)
            if text.startswith("/"):
                parts = text.split(None, 1)
                tui._execute_command(parts[0].lower(), parts[1] if len(parts) > 1 else "")
            else:
                if tui._active_task and not tui._active_task.done():
                    tui._err("Still busy — wait for the current reply.")
                else:
                    tui._active_task = tui._task_executor.submit(tui._run_message, text)
        return

    if key == "BACKSPACE":
        if tui.picker_visible:
            if tui.picker_query:
                tui.picker_query = tui.picker_query[:-1]
                tui._refresh_picker()
            return
        if getattr(tui, "browser_visible", False):
            parent = os.path.dirname(tui.browser_cwd)
            if parent != tui.browser_cwd:
                tui.browser_sel = 0
                tui.browser_cwd = parent
                tui._refresh_browser()
                tui.redraw()
            return
        if tui.cur_pos > 0:
            tui.buf = tui.buf[: tui.cur_pos - 1] + tui.buf[tui.cur_pos :]
            tui.cur_pos -= 1
        tui._update_slash()
        return
    if key == "DELETE":
        if tui.picker_visible:
            return
        if tui.cur_pos < len(tui.buf):
            tui.buf = tui.buf[: tui.cur_pos] + tui.buf[tui.cur_pos + 1 :]
        tui._update_slash()
        return
    if key == "CTRL_W":
        if tui.picker_visible:
            if tui.picker_query:
                tui.picker_query = tui.picker_query.rstrip()
                cut = tui.picker_query.rfind(" ")
                tui.picker_query = tui.picker_query[: cut + 1] if cut >= 0 else ""
                tui._refresh_picker()
            return
        if tui.cur_pos > 0:
            trimmed = tui.buf[: tui.cur_pos].rstrip()
            idx = trimmed.rfind(" ")
            keep = trimmed[: idx + 1] if idx >= 0 else ""
            tui.buf = keep + tui.buf[tui.cur_pos :]
            tui.cur_pos = len(keep)
        tui._update_slash()
        return

    if key == "CTRL_RIGHT":
        idx = tui.cur_pos
        while idx < len(tui.buf) and tui.buf[idx] == " ":
            idx += 1
        while idx < len(tui.buf) and tui.buf[idx] != " ":
            idx += 1
        tui.cur_pos = idx
        tui._update_slash()
        return
    if key == "CTRL_LEFT":
        idx = tui.cur_pos
        while idx > 0 and tui.buf[idx - 1] == " ":
            idx -= 1
        while idx > 0 and tui.buf[idx - 1] != " ":
            idx -= 1
        tui.cur_pos = idx
        tui._update_slash()
        return
    if key == "LEFT":
        if getattr(tui, "browser_visible", False):
            parent = os.path.dirname(tui.browser_cwd)
            if parent != tui.browser_cwd:
                tui.browser_sel = 0
                tui.browser_cwd = parent
                tui._refresh_browser()
                tui.redraw()
                return
        tui.cur_pos = max(0, tui.cur_pos - 1)
        tui._update_slash()
        return
    if key == "RIGHT":
        if getattr(tui, "browser_visible", False):
            tui._browser_select()
            return
        tui.cur_pos = min(len(tui.buf), tui.cur_pos + 1)
        tui._update_slash()
        return
    if key == "HOME":
        if tui.picker_visible:
            tui.picker_sel = _picker_first_selectable(tui.picker_items)
            _update_picker_preview(tui)
            return
        tui.cur_pos = 0
        tui._update_slash()
        return
    if key == "END":
        if tui.picker_visible:
            selectable = _picker_selectable_indexes(tui.picker_items)
            if selectable:
                tui.picker_sel = selectable[-1]
                _update_picker_preview(tui)
            return
        tui.cur_pos = len(tui.buf)
        tui._update_slash()
        return

    if tui.picker_visible and key == "CTRL_F":
        selected = tui.picker_items[tui.picker_sel] if tui.picker_items else {}
        if selected.get("kind") == "model":
            provider = selected.get("provider", tui.picker_provider_key)
            model = selected.get("value", "")
            added = tui.little_notes.toggle_favorite_model(provider, model)
            tui._refresh_picker()
            tui._notify("Added to favorites" if added else "Removed from favorites", duration=1.5)
        return

    if tui.picker_visible and key and all((char.isprintable() or ord(char) > 127) for char in key):
        tui.picker_query += key
        tui._refresh_picker()
        return

    if key and all((char.isprintable() or ord(char) > 127 or char == "\n") for char in key):
        tui.buf = tui.buf[: tui.cur_pos] + key + tui.buf[tui.cur_pos :]
        tui.cur_pos += len(key)
        update_slash(tui, registry=registry, suggest_paths_fn=suggest_paths_fn)
