"""Controller-side helpers extracted from the Lumi TUI app module."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

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


def open_picker(
    tui: Any,
    *,
    get_available_providers_fn,
    get_provider_fn,
    get_models_fn,
    provider_names: dict[str, str],
    log,
) -> None:
    items = []
    try:
        available = get_available_providers_fn()
        models = get_models_fn(get_provider_fn()) if tui.current_model not in ("council", "unknown") else []
        items.append(("header", "", "Providers"))
        for provider in available:
            items.append(("provider", provider, provider_names.get(provider, provider)))
        if len(available) >= 2:
            items.append(("provider", "council", "⚡ Council"))
        if models:
            items.append(("header", "", f"Models ({provider_names.get(get_provider_fn(), get_provider_fn())})"))
            for model in models[:16]:
                items.append(("model", model, model.split("/")[-1]))
    except Exception:
        log.exception("Picker open failed")
    tui.picker_items = items
    tui.picker_sel = 0
    tui.picker_visible = True


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
    kind, value, _label = tui.picker_items[tui.picker_sel]
    if kind == "header":
        return
    if kind == "provider":
        if value == "council":
            tui.current_model = "council"
        else:
            try:
                set_provider_fn(value)
                tui.client = get_client_fn()
                models = get_models_fn(value)
                tui.current_model = models[0] if models else ""
                tui.little_notes.record_model(value, tui.current_model)
                open_picker(
                    tui,
                    get_available_providers_fn=get_available_providers_fn,
                    get_provider_fn=get_provider_fn,
                    get_models_fn=get_models_fn,
                    provider_names=provider_names,
                    log=log,
                )
                return
            except Exception:
                log.exception("Provider switch failed")
        tui._sys(f"Provider → {provider_names.get(tui.current_model, tui.current_model)}")
    elif kind == "model":
        tui.current_model = value
        tui._notify(f"Model → {value.split('/')[-1]}")
    try:
        provider_key = "council" if tui.current_model == "council" else get_provider_fn()
    except Exception:
        provider_key = "huggingface"
    tui.little_notes.record_model(provider_key, tui.current_model)
    tui.picker_visible = False


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
            new_index = tui.picker_sel - 1
            while new_index >= 0 and tui.picker_items[new_index][0] == "header":
                new_index -= 1
            if new_index >= 0:
                tui.picker_sel = new_index
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
            new_index = tui.picker_sel + 1
            while new_index < len(tui.picker_items) and tui.picker_items[new_index][0] == "header":
                new_index += 1
            if new_index < len(tui.picker_items):
                tui.picker_sel = new_index
        else:
            tui._hist_nav(1)
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
        if tui.cur_pos < len(tui.buf):
            tui.buf = tui.buf[: tui.cur_pos] + tui.buf[tui.cur_pos + 1 :]
        tui._update_slash()
        return
    if key == "CTRL_W":
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
        tui.cur_pos = 0
        tui._update_slash()
        return
    if key == "END":
        tui.cur_pos = len(tui.buf)
        tui._update_slash()
        return

    if len(key) == 1 and (key.isprintable() or ord(key) > 127):
        tui.buf = tui.buf[: tui.cur_pos] + key + tui.buf[tui.cur_pos :]
        tui.cur_pos += 1
        update_slash(tui, registry=registry, suggest_paths_fn=suggest_paths_fn)
