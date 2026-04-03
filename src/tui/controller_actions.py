"""Controller-side helpers extracted from the Lumi TUI app module."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from src.chat.model_filters import (
    filter_models_by_allowlist,
    model_allowlist_env_keys,
)
from src.chat.optimizer import estimate_message_tokens, model_context_limit
from src.chat.providers import (
    get_provider_spec,
    provider_capability_model_hints,
    provider_context_limit,
    provider_health_snapshot,
    provider_supports,
)
from src.tui.state import Msg
from src.utils.hooks import run_hooks
from src.utils.skills import build_skill_prompt, find_skill, skill_hits
from src.utils.workbench import WORKBENCH_NAME, WORKBENCH_TITLE, WORKBENCH_VERSION


def _normalized_prompt(text: str) -> str:
    lowered = (text or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(lowered.split())


def _is_identity_prompt(text: str) -> bool:
    lowered = _normalized_prompt(text)
    phrases = (
        "who are you",
        "what are you",
        "tell me about yourself",
        "introduce yourself",
        "what do you know about yourself",
        "tell me everything about you",
        "what is your name",
        "whats your name",
        "what s your name",
        "what are you called",
        "what should i call you",
        "are you lumi",
        "aren t you lumi",
        "arent you lumi",
    )
    return any(phrase in lowered for phrase in phrases)


def _is_capabilities_prompt(text: str) -> bool:
    lowered = _normalized_prompt(text)
    phrases = (
        "what can you do",
        "what do you do",
        "what are your capabilities",
        "what are your features",
        "what are you capable of",
        "how can you help",
        "what do you help with",
        "what can lumi do",
        "what is lumi able to do",
        "what are all your commands",
        "what tools do you have",
        "what features does lumi have",
    )
    return any(phrase in lowered for phrase in phrases)


def _is_runtime_prompt(text: str) -> bool:
    lowered = _normalized_prompt(text)
    phrases = (
        "what model are you using",
        "what provider are you using",
        "what are you running on",
        "what powers you",
        "which model are you on",
        "which provider are you on",
        "what engine are you using",
        "what llm are you using",
        "what model powers you",
        "what version are you",
        "what release are you on",
    )
    return any(phrase in lowered for phrase in phrases)


def _is_workspace_prompt(text: str) -> bool:
    lowered = _normalized_prompt(text)
    phrases = (
        "what project are you in",
        "what repo are you in",
        "what repository are you in",
        "what folder are you in",
        "what workspace are you in",
        "where are you working",
        "are you repo aware",
        "do you know this repo",
        "do you know this project",
    )
    return any(phrase in lowered for phrase in phrases)


def _is_self_knowledge_followup_prompt(text: str) -> bool:
    lowered = _normalized_prompt(text)
    short_followups = {
        "are you sure",
        "you sure",
        "really",
        "really sure",
        "for real",
        "fr",
        "be honest",
        "seriously",
    }
    if lowered in short_followups:
        return True
    phrases = (
        "are you actually sure",
        "who are you actually",
        "what are you actually",
        "who are you really",
        "what are you really",
        "be honest who are you",
        "be honest what are you",
        "are you actually lumi",
        "so who are you",
        "what are you then",
    )
    return any(phrase in lowered for phrase in phrases)


def _is_continuation_prompt(text: str) -> bool:
    lowered = _normalized_prompt(text)
    if not lowered:
        return False
    exact_matches = {
        "continue",
        "continue it",
        "continue that",
        "continue this",
        "continue please",
        "go on",
        "keep going",
        "finish it",
        "finish that",
        "finish this",
        "finish please",
        "complete it",
        "complete that",
        "complete this",
        "resume",
        "resume that",
        "resume this",
        "you did not finish it",
        "you didnt finish it",
        "you did not finish",
        "you didnt finish",
    }
    if lowered in exact_matches:
        return True
    phrases = (
        "finish what you started",
        "complete what you started",
        "pick up where you left off",
        "continue where you left off",
        "continue from where you stopped",
        "continue your last answer",
        "finish your last answer",
        "complete the answer",
        "finish the answer",
        "you did not finish the answer",
        "you didnt finish the answer",
        "you cut off",
        "that got cut off",
        "that was cut off",
    )
    return any(phrase in lowered for phrase in phrases)


def _build_continuation_prompt(
    user_input: str,
    *,
    previous_request: str = "",
    previous_reply: str = "",
) -> str:
    tail = (previous_reply or "").strip()
    if len(tail) > 1200:
        tail = tail[-1200:]
    parts = [
        "[Continuation request]",
        "Continue your immediately previous answer from exactly where it stopped.",
        "Do not restart from the beginning.",
        "Do not apologize, explain the cutoff, or repeat sections you already completed.",
        "Finish the incomplete answer directly.",
        "If the previous answer ended inside a table, list, sentence, or code block, continue in that same structure.",
    ]
    if previous_request.strip():
        parts.append(f"Original request:\n{previous_request.strip()}")
    if tail:
        parts.append(f"Previous answer ending:\n{tail}")
    parts.append(f"User follow-up:\n{user_input.strip()}")
    return "\n\n".join(parts)


def _creator_profile(tui: Any) -> tuple[str, str, str]:
    creator = (
        getattr(tui, "persona_override", {}).get("creator")
        or getattr(tui, "persona", {}).get("creator")
        or "Sardor Sodiqov (SardorchikDev)"
    )
    full_name = "Sardor Sodiqov" if "Sardor" in creator else creator
    github = "SardorchikDev"
    return creator, full_name, github


def _summarize_hook_failure(result) -> str:
    detail = result.stderr or result.stdout or f"exit {result.returncode}"
    return f"Hook {result.spec.name} failed: {detail}"


def _emit_hook_results(tui: Any, results: list, *, notify: bool = False) -> bool:
    blocked = False
    for result in results:
        if result.stdout:
            tui._sys(f"hook {result.spec.name}: {result.stdout}")
        if not result.ok:
            message = _summarize_hook_failure(result)
            if notify:
                tui._notify(message)
            else:
                tui._err(message)
            blocked = blocked or result.blocked
    return blocked


def _run_skill_turn(
    tui: Any,
    command_text: str,
    prompt: str,
    *,
    build_messages_fn,
    session_save_fn,
    auto_extract_facts_fn,
    log,
) -> None:
    before = run_hooks(
        "before_message",
        base_dir=Path.cwd(),
        command=command_text.split()[0],
        args=command_text.split(None, 1)[1] if " " in command_text else "",
        user_input=command_text,
    )
    if _emit_hook_results(tui, before):
        return
    try:
        tui.set_busy(True)
        tui.scroll_offset = 0
        tui.last_msg = command_text
        tui.store.add(Msg("user", command_text))
        tui.memory.add("user", prompt)
        messages = build_messages_fn(tui.system_prompt, tui.memory.get())
        tui.redraw()
        raw_reply = tui._tui_stream(messages, tui.current_model)
        tui.memory.replace_last("user", command_text)
        tui.memory.add("assistant", raw_reply)
        after = run_hooks(
            "after_response",
            base_dir=Path.cwd(),
            command=command_text.split()[0],
            args=command_text.split(None, 1)[1] if " " in command_text else "",
            user_input=command_text,
            response=raw_reply,
        )
        _emit_hook_results(tui, after, notify=True)
        tui.prev_reply = tui.last_reply
        tui.last_reply = raw_reply
        tui.turns += 1
        tui._task_executor.submit(lambda: session_save_fn(tui.memory.get()))
        if tui.turns % 8 == 0:
            def _bg_remember() -> None:
                try:
                    if auto_extract_facts_fn(tui.client, tui.current_model, tui.memory.get()):
                        with tui._state_lock:
                            tui.system_prompt = tui._make_system_prompt()
                except Exception:
                    log.exception("Auto-remember failed")

            tui._task_executor.submit(_bg_remember)
    except Exception as exc:
        tui._err(str(exc))
    finally:
        tui.set_busy(False)


def _is_creator_prompt(text: str) -> bool:
    lowered = _normalized_prompt(text)
    direct_phrases = (
        "who is your creator",
        "who created you",
        "who made you",
        "who built you",
        "who is your developer",
        "who is your maker",
        "do you know your creator",
        "tell me your creator",
        "who s your creator",
        "whos your creator",
    )
    if any(phrase in lowered for phrase in direct_phrases):
        return True
    return "creator" in lowered and any(token in lowered for token in ("you", "your", "lumi"))


def _creator_reply(tui: Any) -> str:
    creator, full_name, github = _creator_profile(tui)
    if github in creator or full_name in creator:
        return (
            f"My creator is {full_name}. On GitHub he goes by {github}. "
            f"He built Lumi and maintains the project."
        )
    return f"My creator is {creator}."


def _display_path(path: Path, *, max_len: int = 56) -> str:
    text = str(path.resolve())
    home = str(Path.home())
    if text == home:
        text = "~"
    elif text.startswith(home + "/"):
        text = "~/" + text[len(home) + 1 :]
    if len(text) <= max_len:
        return text
    return "..." + text[-(max_len - 3) :]


def _runtime_identity_bits(tui: Any, *, get_provider_fn) -> tuple[str, str, str]:
    if getattr(tui, "current_model", "") == "council":
        return "Council", "council", "council mode"
    try:
        provider_key = get_provider_fn()
    except Exception:
        provider_key = ""
    spec = get_provider_spec(provider_key) if provider_key else None
    provider_label = spec.label if spec else (provider_key or "unknown provider")
    model = getattr(tui, "current_model", "unknown model") or "unknown model"
    return provider_label, model, provider_key


def _identity_reply(tui: Any, *, get_provider_fn) -> str:
    provider_label, model, _provider_key = _runtime_identity_bits(tui, get_provider_fn=get_provider_fn)
    _creator, full_name, github = _creator_profile(tui)
    return (
        f"I’m Lumi, the terminal coding agent for this app. "
        f"My current release line is {WORKBENCH_TITLE}. "
        f"I was created by {full_name}, known on GitHub as {github}. "
        f"I handle repo-aware coding, tools, memory, search, plugins, and workbench workflows. "
        f"Right now I’m running on {provider_label} with {model}."
    )


def _capabilities_reply(tui: Any, *, get_provider_fn) -> str:
    provider_label, model, provider_key = _runtime_identity_bits(tui, get_provider_fn=get_provider_fn)
    abilities = [
        "switch providers and models",
        "inspect, create, edit, move, and review files",
        "work repo-aware inside the current workspace",
        "search the web when needed",
        "remember user facts and recent conversation context",
        "hand off to external coding CLIs with /mode vessel",
        "run workbench flows like /build, /review, /ship, /learn, and /fixci",
        "use slash commands, command palette, permissions, hooks, skills, and plugins",
    ]
    if provider_supports(provider_key, "vision"):
        abilities.append("inspect images")
    if provider_supports(provider_key, "audio_transcription"):
        abilities.append("transcribe audio and voice notes")
    if getattr(tui, "_loaded_plugins", []):
        abilities.append("use trusted plugins")
    abilities_text = ", ".join(abilities[:-1]) + f", and {abilities[-1]}" if len(abilities) > 1 else abilities[0]
    return (
        f"I’m Lumi. In {WORKBENCH_NAME}, I can {abilities_text}. "
        f"My current runtime is {provider_label} with {model}."
    )


def _runtime_reply(tui: Any, *, get_provider_fn) -> str:
    provider_label, model, _provider_key = _runtime_identity_bits(tui, get_provider_fn=get_provider_fn)
    effort = getattr(tui, "reasoning_effort", "medium") or "medium"
    compact = "on" if getattr(tui, "_compact", False) else "off"
    guardian = "on" if getattr(tui, "guardian_enabled", False) else "off"
    return (
        f"I’m Lumi on {WORKBENCH_VERSION} {WORKBENCH_NAME}, currently running on {provider_label} with {model}. "
        f"Runtime state: effort={effort}, compact={compact}, guardian={guardian}."
    )


def _workspace_reply(tui: Any) -> str:
    workspace = Path.cwd().resolve()
    profile = getattr(tui, "workspace_profile", None)
    details: list[str] = []
    git_branch = getattr(profile, "git_branch", None)
    frameworks = tuple(getattr(profile, "frameworks", ()) or ())
    if git_branch:
        details.append(f"branch {git_branch}")
    if frameworks:
        details.append(f"stack {', '.join(frameworks[:3])}")
    details_text = f" I’m seeing {', '.join(details)}." if details else ""
    return (
        f"I’m currently working in {_display_path(workspace)}."
        f"{details_text} I can inspect the repo structure, files, git state, project context, and active code from here."
    )


def _recent_self_knowledge_topic(tui: Any) -> str | None:
    snapshot_fn = getattr(tui.store, "snapshot", None)
    recent = list(snapshot_fn() if callable(snapshot_fn) else [])
    for msg in reversed(recent[-6:]):
        text = str(getattr(msg, "text", "") or "")
        if not text:
            continue
        if getattr(msg, "role", "") == "user":
            if _is_identity_prompt(text):
                return "identity"
            if _is_creator_prompt(text):
                return "creator"
            if _is_capabilities_prompt(text):
                return "capabilities"
            if _is_runtime_prompt(text):
                return "runtime"
            if _is_workspace_prompt(text):
                return "workspace"
        elif getattr(msg, "role", "") == "assistant":
            lowered = _normalized_prompt(text)
            if "i m lumi" in lowered or "i am lumi" in lowered or "created by sardor sodiqov" in lowered:
                return "identity"
            if "my creator is" in lowered:
                return "creator"
            if "current runtime" in lowered or "running on" in lowered:
                return "runtime"
            if "i can inspect the repo structure" in lowered or "currently working in" in lowered:
                return "workspace"
            if "i can switch providers and models" in lowered or "what i can do" in lowered:
                return "capabilities"
    return None


def _self_knowledge_followup_reply(tui: Any, topic: str, *, get_provider_fn) -> str | None:
    provider_label, model, _provider_key = _runtime_identity_bits(tui, get_provider_fn=get_provider_fn)
    if topic == "creator":
        return (
            "Yes. My creator is Sardor Sodiqov, and his GitHub handle is SardorchikDev. "
            "He built Lumi and maintains the project."
        )
    if topic == "capabilities":
        return _capabilities_reply(tui, get_provider_fn=get_provider_fn)
    if topic == "runtime":
        return (
            f"Yes. I’m Lumi, and my current runtime is {provider_label} with {model}. "
            f"My release line is {WORKBENCH_TITLE}."
        )
    if topic == "workspace":
        return _workspace_reply(tui)
    if topic == "identity":
        return (
            f"Yes. I’m Lumi, not Codex CLI or Claude Code. "
            f"My release line is {WORKBENCH_TITLE}. "
            f"My creator is Sardor Sodiqov, known on GitHub as SardorchikDev. "
            f"Right now I’m running on {provider_label} with {model}."
        )
    return None


def _self_knowledge_reply(tui: Any, text: str, *, get_provider_fn) -> str | None:
    if _is_identity_prompt(text):
        return _identity_reply(tui, get_provider_fn=get_provider_fn)
    if _is_creator_prompt(text):
        return _creator_reply(tui)
    if _is_capabilities_prompt(text):
        return _capabilities_reply(tui, get_provider_fn=get_provider_fn)
    if _is_runtime_prompt(text):
        return _runtime_reply(tui, get_provider_fn=get_provider_fn)
    if _is_workspace_prompt(text):
        return _workspace_reply(tui)
    if _is_self_knowledge_followup_prompt(text):
        topic = _recent_self_knowledge_topic(tui)
        if topic:
            return _self_knowledge_followup_reply(tui, topic, get_provider_fn=get_provider_fn)
    return None


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
    if getattr(tui, "permission_prompt_active", False):
        tui._approve_pending_permission("deny")
        changed = True
    if getattr(tui, "command_palette_visible", False):
        tui.command_palette_visible = False
        tui.command_palette_query = ""
        tui.command_palette_hits = []
        tui.command_palette_sel = 0
        changed = True
    if getattr(tui, "shortcuts_visible", False):
        tui.shortcuts_visible = False
        changed = True
    if getattr(tui, "workspace_trust_visible", False):
        tui.workspace_trust_visible = False
        changed = True
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
    review_card = getattr(tui, "review_card", None)
    if getattr(review_card, "active", False):
        tui.clear_review_card()
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
    tui._notify(f"Loaded: {item_name}")
    tui._task_executor.submit(tui._execute_command, "/file", item_path)


def update_slash(tui: Any, *, registry, suggest_paths_fn) -> None:
    if tui.buf.startswith("/"):
        query = tui.buf.lower()
        dynamic_hits = skill_hits(
            query,
            base_dir=Path.cwd(),
            exclude_commands=set(registry.commands),
            limit=8,
        )
        hits = list(dynamic_hits)
        hits.extend(item for item in registry.get_hits(query) if item[0] not in {hit[0] for hit in hits})
        tui.slash_hits = hits[:12]
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
    before_hooks = run_hooks("before_message", base_dir=Path.cwd(), user_input=user_input)
    if _emit_hook_results(tui, before_hooks):
        tui.set_busy(False)
        return

    self_reply = _self_knowledge_reply(tui, user_input, get_provider_fn=get_provider_fn)
    if self_reply:
        tui.last_msg = user_input
        tui.store.add(Msg("user", user_input))
        tui.memory.add("user", user_input)
        tui.store.add(Msg("assistant", self_reply))
        tui.memory.add("assistant", self_reply)
        tui.prev_reply = tui.last_reply
        tui.last_reply = self_reply
        tui.turns += 1
        tui._task_executor.submit(lambda: session_save_fn(tui.memory.get()))
        after_hooks = run_hooks(
            "after_response",
            base_dir=Path.cwd(),
            user_input=user_input,
            response=self_reply,
        )
        _emit_hook_results(tui, after_hooks, notify=True)
        tui.set_busy(False)
        return

    is_code = is_complex_coding_task_fn(user_input) or is_coding_task_fn(user_input)
    is_files = is_file_generation_task_fn(user_input)
    system_prompt = tui._system_prompt_for_turn(
        user_input=user_input,
        coding_mode=is_code,
        file_mode=is_files,
    )

    if needs_plan_first_fn(user_input) and is_files:
        system_prompt += "\n\n[INSTRUCTION: Output a brief one-paragraph plan. Then write each file completely.]"
    if is_filesystem_request_fn(user_input):
        tui._run_file_agent(user_input, system_prompt)
        return

    emotion = detect_emotion_fn(user_input)
    augmented = user_input
    continuation_turn = _is_continuation_prompt(user_input) and bool(getattr(tui, "last_reply", ""))
    if continuation_turn:
        augmented = _build_continuation_prompt(
            user_input,
            previous_request=str(getattr(tui, "last_msg", "") or ""),
            previous_reply=str(getattr(tui, "last_reply", "") or ""),
        )
    elif emotion:
        hint = emotion_hint_fn(emotion)
        if hint:
            augmented = hint + augmented

    if continuation_turn:
        pass
    elif tui.response_mode == "short":
        augmented += "\n\n[Reply concisely — 2-3 sentences max.]"
    elif tui.response_mode == "detailed":
        augmented += "\n\n[Reply in detail — be thorough and comprehensive.]"
    elif tui.response_mode == "bullets":
        augmented += "\n\n[Reply using bullet points only.]"
    elif getattr(tui, "brief_mode", False):
        augmented += "\n\n[Reply concisely. Prefer dense, direct wording.]"
    tui.response_mode = None

    if (not continuation_turn) and should_search_fn(user_input):
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

    active_model = tui.current_model if tui.current_model != "council" else get_models_fn(get_provider_fn())[0]
    estimated_tokens = estimate_message_tokens(tui.memory.get()) + max(1, len(system_prompt) // 4)
    if estimated_tokens >= int(model_context_limit(active_model, get_provider_fn()) * 0.8):
        def _compress() -> None:
            try:
                history = tui.memory.get()
                take = max(2, int(len(history) * 0.3))
                snapshot = history[:take]
                if not snapshot:
                    return
                summary = tui._silent_call(
                    "Summarize the following conversation segment in 200 words, preserving key decisions, file paths, "
                    "and code changes made.\n\n"
                    + "\n".join(f"{item['role']}: {item['content'][:240]}" for item in snapshot),
                    active_model,
                    max_tokens=220,
                )
                if summary:
                    with tui._state_lock:
                        tail_messages = max(4, len(history) - take)
                        tui.memory.replace_with_summary(summary, tail_messages=tail_messages)
                        tui._cached_tok_len = -1
                    tui._notify(f"Context compacted. {len(snapshot)} messages summarized.", duration=2.0)
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
    after_hooks = run_hooks(
        "after_response",
        base_dir=Path.cwd(),
        user_input=user_input,
        response=raw_reply,
    )
    _emit_hook_results(tui, after_hooks, notify=True)

    tui.prev_reply = tui.last_reply
    tui.last_reply = raw_reply
    tui.turns += 1
    tui.set_busy(False)

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


def _scroll_active_surface(
    tui: Any,
    *,
    up: bool,
    overlay_amount: int = 1,
    transcript_amount: int = 3,
) -> None:
    overlay_step = max(1, overlay_amount)
    overlay_delta = -overlay_step if up else overlay_step
    if getattr(tui, "browser_visible", False):
        tui.browser_sel = max(0, min(len(tui.browser_items) - 1, tui.browser_sel + overlay_delta))
        return
    if tui.slash_visible:
        tui.slash_sel = max(0, min(len(tui.slash_hits) - 1, tui.slash_sel + overlay_delta))
        return
    if tui.path_visible:
        tui.path_sel = max(0, min(len(tui.path_hits) - 1, tui.path_sel + overlay_delta))
        return
    if tui.picker_visible:
        _picker_move_selection(tui, overlay_delta)
        return
    if getattr(tui, "command_palette_visible", False):
        if tui.command_palette_hits:
            tui.command_palette_sel = max(0, min(len(tui.command_palette_hits) - 1, tui.command_palette_sel + overlay_delta))
        return

    transcript_step = max(1, transcript_amount)
    if up:
        tui.scroll_offset += transcript_step
    else:
        tui.scroll_offset = max(0, tui.scroll_offset - transcript_step)


def _use_arrow_scroll(tui: Any) -> bool:
    return not any(
        (
            getattr(tui, "browser_visible", False),
            tui.slash_visible,
            tui.path_visible,
            tui.picker_visible,
            getattr(tui, "command_palette_visible", False),
            getattr(tui, "shortcuts_visible", False),
            getattr(tui, "workspace_trust_visible", False),
            getattr(tui, "permission_prompt_active", False),
            getattr(tui, "pane_active", False),
            getattr(getattr(tui, "review_card", None), "active", False),
            bool(tui.buf),
        )
    )


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


def _provider_icon(provider: str) -> str:
    return {
        "claude": "CL",
        "gemini": "GM",
        "groq": "GQ",
        "huggingface": "HF",
        "openrouter": "OR",
        "mistral": "MS",
        "cohere": "CH",
        "github": "GH",
        "bytez": "BZ",
        "cloudflare": "CF",
        "vercel": "VC",
        "vertex": "VX",
        "ollama": "OL",
        "council": "CO",
    }.get(provider, "AI")


def _model_icon(provider: str, model: str) -> str:
    tags = set(_model_tags(provider, model))
    if "image" in tags:
        return "img"
    if "vision" in tags:
        return "see"
    if "audio" in tags:
        return "aud"
    if "best coding" in tags or "coding" in tags:
        return "code"
    if "reasoning" in tags:
        return "think"
    if "fast" in tags:
        return "fast"
    return "mdl"


def _group_icon(group: str) -> str:
    return {
        "Current": "cur",
        "Favorites": "fav",
        "Recent": "new",
        "Recommended": "best",
        "Image": "img",
        "Vision": "see",
        "Audio": "aud",
        "Fast": "fast",
        "Coding": "code",
        "Reasoning": "think",
        "Long context": "long",
        "All models": "all",
    }.get(group, "all")


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
        current_provider = get_provider_fn()
        configured = [item for item in health_snapshot if item.configured and item.key in available]
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
                items.append(
                    {
                        "kind": "provider",
                        "value": item.key,
                        "label": provider_names.get(item.key, item.label),
                        "meta": "",
                        "icon": _provider_icon(item.key),
                        "current": item.key == current_provider,
                        "disabled": False,
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
    items = [{"kind": "action", "value": "__back__", "label": "back", "meta": "", "icon": "<-"}]
    try:
        all_models = get_models_fn(provider)
        models, allowlist = filter_models_by_allowlist(provider, all_models)
    except Exception as exc:
        tui.picker_items = items + [{"kind": "hint", "label": f"Could not load models: {exc}"}]
        tui.picker_sel = 0
        tui.picker_empty_message = "Model loading failed"
        _update_picker_preview(tui, provider_names=provider_names, health_by_key=health_by_key)
        return
    if allowlist:
        items.append(
            {
                "kind": "hint",
                "label": f".env model allowlist active ({len(models)}/{len(all_models)} shown)",
            }
        )

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
        items.append({"kind": "header", "label": group, "icon": _group_icon(group)})
        for model in group_models:
            current = provider == get_provider_fn() and model == tui.current_model
            recommended = group == "Recommended"
            label = model.split("/")[-1]
            items.append(
                {
                    "kind": "model",
                    "value": model,
                    "label": label,
                    "meta": "",
                    "icon": _model_icon(provider, model),
                    "tags": _model_tags(provider, model),
                    "provider": provider,
                    "recommended": recommended,
                    "current": current,
                    "favorite": model in favorites,
                }
            )

    if len(items) <= 2:
        if allowlist:
            key = model_allowlist_env_keys(provider)[0]
            items.append({"kind": "hint", "label": f"No models matched {key} in .env"})
        else:
            items.append({"kind": "hint", "label": "No models match this filter."})
    tui.picker_items = items
    tui.picker_sel = _picker_first_selectable(items)
    tui.picker_empty_message = "Type to filter models"
    _update_picker_preview(tui, provider_names=provider_names, health_by_key=health_by_key)


def _update_picker_preview(tui: Any, *, provider_names: dict[str, str] | None = None, health_by_key: dict[str, Any] | None = None) -> None:
    tui.picker_preview_lines = []


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


def execute_command(
    tui: Any,
    cmd,
    arg,
    *,
    registry,
    plugin_dispatch_fn,
    build_messages_fn,
    session_save_fn,
    auto_extract_facts_fn,
    log,
) -> None:
    before_hooks = run_hooks(
        "before_command",
        base_dir=Path.cwd(),
        command=cmd,
        args=arg,
        user_input=f"{cmd} {arg}".strip(),
    )
    if _emit_hook_results(tui, before_hooks):
        return
    if cmd in registry.commands:
        if cmd not in {"/help"}:
            tui.recent_commands = tui.little_notes.record_command(cmd)[:3]
        registry.commands[cmd]["func"](tui, arg)
        after_hooks = run_hooks(
            "after_command",
            base_dir=Path.cwd(),
            command=cmd,
            args=arg,
            user_input=f"{cmd} {arg}".strip(),
        )
        _emit_hook_results(tui, after_hooks, notify=True)
        return
    skill = find_skill(cmd, base_dir=Path.cwd())
    if skill is not None:
        tui.recent_commands = tui.little_notes.record_command(cmd)[:3]
        _run_skill_turn(
            tui,
            f"{cmd} {arg}".strip(),
            build_skill_prompt(skill, arg, workspace=Path.cwd()),
            build_messages_fn=build_messages_fn,
            session_save_fn=session_save_fn,
            auto_extract_facts_fn=auto_extract_facts_fn,
            log=log,
        )
        after_hooks = run_hooks(
            "after_command",
            base_dir=Path.cwd(),
            command=cmd,
            args=arg,
            user_input=f"{cmd} {arg}".strip(),
        )
        _emit_hook_results(tui, after_hooks, notify=True)
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
        after_hooks = run_hooks(
            "after_command",
            base_dir=Path.cwd(),
            command=cmd,
            args=arg,
            user_input=f"{cmd} {arg}".strip(),
        )
        _emit_hook_results(tui, after_hooks, notify=True)
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
    if isinstance(key, tuple) and len(key) == 2 and key[0] == "PASTE":
        if tui.busy:
            return
        pasted = str(key[1] or "")
        if getattr(tui, "command_palette_visible", False):
            tui.command_palette_query += pasted
            tui._refresh_command_palette()
            return
        if tui.picker_visible:
            tui.picker_query += pasted
            tui._refresh_picker()
            return
        if getattr(tui, "workspace_trust_visible", False):
            return
        tui.buf = tui.buf[: tui.cur_pos] + pasted + tui.buf[tui.cur_pos :]
        tui.cur_pos += len(pasted)
        update_slash(tui, registry=registry, suggest_paths_fn=suggest_paths_fn)
        return
    if getattr(tui, "permission_prompt_active", False):
        if key == "ESC":
            tui._approve_pending_permission("deny")
            return
        if key in {"LEFT", "UP", "TAB"}:
            tui.permission_prompt.selected = (int(getattr(tui.permission_prompt, "selected", 0) or 0) - 1) % 3
            tui.redraw()
            return
        if key in {"RIGHT", "DOWN"}:
            tui.permission_prompt.selected = (int(getattr(tui.permission_prompt, "selected", 0) or 0) + 1) % 3
            tui.redraw()
            return
        if key in {"1", "2", "3"}:
            tui.permission_prompt.selected = int(key) - 1
            tui.redraw()
            return
        if key == "ENTER":
            selected = int(getattr(tui.permission_prompt, "selected", 0) or 0)
            decision = ("allow_once", "allow_always", "deny")[selected]
            tui._approve_pending_permission(decision)
            return
        return
    if getattr(tui, "workspace_trust_visible", False):
        if key == "ESC":
            tui.workspace_trust_visible = False
            tui.redraw()
            return
        if key in {"UP", "DOWN", "TAB", "LEFT", "RIGHT"}:
            tui.workspace_trust_sel = 1 - int(getattr(tui, "workspace_trust_sel", 0) or 0)
            tui.redraw()
            return
        if key in {"1", "2"}:
            tui.workspace_trust_sel = 0 if key == "1" else 1
            tui.redraw()
            return
        if key == "ENTER":
            if int(getattr(tui, "workspace_trust_sel", 0) or 0) == 0:
                tui.accept_workspace_trust()
            else:
                tui.decline_workspace_trust()
            tui.redraw()
            return
        return
    if tui.busy:
        if key == "ESC":
            tui.request_stop()
        return
    shortcuts_visible = bool(getattr(tui, "shortcuts_visible", False))
    shortcuts_context_blocked = any(
        (
            getattr(tui, "browser_visible", False),
            tui.slash_visible,
            tui.path_visible,
            tui.picker_visible,
            getattr(tui, "command_palette_visible", False),
            getattr(tui, "pane_active", False),
            getattr(getattr(tui, "review_card", None), "active", False),
        )
    )
    if key == "?" and (shortcuts_visible or (not tui.buf and not shortcuts_context_blocked)):
        tui.shortcuts_visible = not shortcuts_visible
        tui.redraw()
        return
    if shortcuts_visible:
        if key == "ENTER":
            tui.shortcuts_visible = False
            tui.redraw()
            return
        tui.shortcuts_visible = False
    if key == "ESC":
        tui._cancel_transient_state()
        return
    if key in ("CTRL_Q", "CTRL_C"):
        with tui._state_lock:
            tui._running = False
        return
    if key == "CTRL_G":
        starter_visible = bool(getattr(tui, "show_starter_panel", True))
        tui.show_starter_panel = not starter_visible
        tui.starter_panel_pinned = tui.show_starter_panel
        tui.redraw()
        return
    if key == "CTRL_N":
        if not tui.slash_visible:
            tui._open_picker()
        return
    if key == "CTRL_P":
        tui._toggle_command_palette()
        return
    if key == "CTRL_T":
        tui._toggle_todo_pane()
        return
    if getattr(tui, "command_palette_visible", False) and key == "CTRL_U":
        tui.command_palette_query = ""
        tui._refresh_command_palette()
        return
    if tui.picker_visible and key == "CTRL_U":
        tui.picker_query = ""
        tui._refresh_picker()
        return
    if key == "CTRL_L":
        tui.memory.clear()
        tui.store.clear()
        tui.agents.clear()
        tui.tool_row_index = {}
        tui.agent_todos = []
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
        _scroll_active_surface(tui, up=True, overlay_amount=3, transcript_amount=3)
        return
    if key in ("SHIFT_DOWN", "CTRL_DOWN"):
        _scroll_active_surface(tui, up=False, overlay_amount=3, transcript_amount=3)
        return
    if key == "WHEEL_UP":
        _scroll_active_surface(tui, up=True, overlay_amount=1, transcript_amount=3)
        return
    if key == "WHEEL_DOWN":
        _scroll_active_surface(tui, up=False, overlay_amount=1, transcript_amount=3)
        return

    if key == "UP":
        if _use_arrow_scroll(tui):
            _scroll_active_surface(tui, up=True, overlay_amount=3, transcript_amount=3)
            return
        if getattr(tui, "command_palette_visible", False):
            tui.command_palette_sel = max(0, tui.command_palette_sel - 1)
            tui.redraw()
            return
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
        if _use_arrow_scroll(tui):
            _scroll_active_surface(tui, up=False, overlay_amount=3, transcript_amount=3)
            return
        if getattr(tui, "command_palette_visible", False):
            if tui.command_palette_hits:
                tui.command_palette_sel = min(len(tui.command_palette_hits) - 1, tui.command_palette_sel + 1)
            tui.redraw()
            return
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
        step = max(4, rows // 2)
        _scroll_active_surface(
            tui,
            up=True,
            overlay_amount=step,
            transcript_amount=max(1, rows - 6),
        )
        return
    if key == "PGDN":
        rows, _ = term_size_fn()
        step = max(4, rows // 2)
        _scroll_active_surface(
            tui,
            up=False,
            overlay_amount=step,
            transcript_amount=max(1, rows - 6),
        )
        return
    if key == "TAB":
        if getattr(tui, "command_palette_visible", False):
            if tui.command_palette_hits:
                tui.command_palette_sel = min(len(tui.command_palette_hits) - 1, tui.command_palette_sel + 1)
            tui.redraw()
            return
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
        if getattr(tui, "command_palette_visible", False):
            tui._run_command_palette_selection()
            return
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
        tui._submit_prompt_text(text)
        return
    if key == "CTRL_D":
        text = tui.buf.strip()
        tui.buf = ""
        tui.cur_pos = 0
        tui.slash_visible = False
        tui.history.reset_navigation()
        tui.path_visible = False
        tui._submit_prompt_text(text)
        return

    if key == "BACKSPACE":
        if getattr(tui, "command_palette_visible", False):
            if tui.command_palette_query:
                tui.command_palette_query = tui.command_palette_query[:-1]
                tui._refresh_command_palette()
            return
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
        if getattr(tui, "command_palette_visible", False):
            return
        if tui.picker_visible:
            return
        if tui.cur_pos < len(tui.buf):
            tui.buf = tui.buf[: tui.cur_pos] + tui.buf[tui.cur_pos + 1 :]
        tui._update_slash()
        return
    if key == "CTRL_W":
        if getattr(tui, "command_palette_visible", False):
            if tui.command_palette_query:
                tui.command_palette_query = tui.command_palette_query.rstrip()
                cut = tui.command_palette_query.rfind(" ")
                tui.command_palette_query = tui.command_palette_query[: cut + 1] if cut >= 0 else ""
                tui._refresh_command_palette()
            return
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
        if getattr(tui, "command_palette_visible", False):
            tui.command_palette_sel = 0
            tui.redraw()
            return
        if tui.picker_visible:
            tui.picker_sel = _picker_first_selectable(tui.picker_items)
            _update_picker_preview(tui)
            return
        tui.cur_pos = 0
        tui._update_slash()
        return
    if key == "END":
        if getattr(tui, "command_palette_visible", False):
            if tui.command_palette_hits:
                tui.command_palette_sel = len(tui.command_palette_hits) - 1
                tui.redraw()
            return
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

    if getattr(tui, "command_palette_visible", False) and key and all((char.isprintable() or ord(char) > 127) for char in key):
        tui.command_palette_query += key
        tui._refresh_command_palette()
        return

    if key and all((char.isprintable() or ord(char) > 127 or char == "\n") for char in key):
        tui.buf = tui.buf[: tui.cur_pos] + key + tui.buf[tui.cur_pos :]
        tui.cur_pos += len(key)
        update_slash(tui, registry=registry, suggest_paths_fn=suggest_paths_fn)
