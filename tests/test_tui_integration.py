"""Integration-style tests for the TUI controller and renderer state."""

from __future__ import annotations

import re
from types import SimpleNamespace

from src.memory.conversation_store import load_repo_autosave, save_repo_autosave
from src.tui.app import LumiTUI, _strip_ansi, registry
from src.tui.notes import LittleNotesStore
from src.tui.state import Msg


def _make_tui(tmp_path, monkeypatch) -> LumiTUI:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr("src.tui.mode_sessions.CONVERSATIONS_DIR", tmp_path / "conversations")
    monkeypatch.setattr("src.memory.longterm.MEMORY_FILE", tmp_path / "longterm.json")
    monkeypatch.setattr("src.utils.skills.LUMI_HOME", tmp_path / "lumi-home")
    monkeypatch.setattr("src.utils.hooks.LUMI_HOME", tmp_path / "lumi-home")
    tui = LumiTUI()
    notes_path = tmp_path / "little_notes.json"
    tui.little_notes = LittleNotesStore(notes_path)
    tui.recent_commands = tui.little_notes.recent_commands[:3]
    tui.recent_actions = tui.little_notes.recent_actions[:4]
    tui.current_model = "meta-llama/Llama-3.3-70B-Instruct"
    return tui


def _patch_inline_thread(monkeypatch) -> None:
    class InlineThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            if self._target is not None:
                self._target(*self._args, **self._kwargs)

    monkeypatch.setattr("src.tui.app.threading.Thread", InlineThread)


def test_starter_panel_renders_minimal_header(tmp_path, monkeypatch):
    monkeypatch.setattr("src.tui.session.random.choice", lambda _seq: "Tip: Short tip.")
    tui = _make_tui(tmp_path, monkeypatch)
    tui.show_starter_panel = True
    tui.little_notes.record_command("/agent")
    tui.little_notes.record_command("/help")
    tui.recent_commands = tui.little_notes.recent_commands[:3]

    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    joined = "\n".join(lines)

    assert "Operator" in joined
    assert "HuggingFace" in joined
    assert "Llama-3.3" in joined
    assert "▐▛███▜▌" in joined
    assert "▝▜█████▛▘" in joined
    assert "Tips for getting started" not in joined
    assert not any(line.startswith("╭") for line in lines)
    assert lines[0] == ""
    tui._task_executor.shutdown(wait=False)


def test_starter_panel_stays_minimal_even_with_tip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.tui.session.random.choice",
        lambda _seq: "Tip: Use /imagine <prompt> to generate images with Gemini and then ask Lumi to iterate on lighting, framing, and style.",
    )
    tui = _make_tui(tmp_path, monkeypatch)
    tui.show_starter_panel = True

    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    joined = "\n".join(lines)

    assert "/imagine <prompt>" not in joined
    assert "Tips for getting started" not in joined
    assert "Lumi Operator" in joined
    tui._task_executor.shutdown(wait=False)


def test_chat_layout_keeps_prompt_and_transcript_separate(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.store.add(Msg("user", "hi"))
    tui.store.add(Msg("assistant", "hello back"))

    starter = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(36, 110, 110)
    prompt = [_strip_ansi(line) for line in prompt_lines]
    chat = [_strip_ansi(line) for line in tui.renderer._build_chat_lines(110)]
    transcript_top = tui.renderer._transcript_top(len(starter), len(chat))
    prompt_top = tui.renderer._prompt_top(36, transcript_top, len(prompt_lines), len(chat))

    assert any("Lumi Operator" in line for line in starter)
    assert any("›" in line for line in prompt)
    assert any("› hi" in line for line in chat)
    assert any("hello back" in line for line in chat)
    assert prompt_top == tui.renderer._transcript_top(len(starter), len(chat)) + len(chat)
    tui._task_executor.shutdown(wait=False)


def test_prompt_follows_transcript_until_it_hits_bottom(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    for index in range(8):
        tui.store.add(Msg("user", f"message {index}"))
        tui.store.add(Msg("assistant", f"reply {index}"))

    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(18, 110, 110)
    chat = tui.renderer._build_chat_lines(110)
    prompt_top = tui.renderer._prompt_top(18, 1, len(prompt_lines), len(chat))

    assert prompt_top == 18 - len(prompt_lines) + 1
    tui._task_executor.shutdown(wait=False)


def test_header_keeps_a_blank_row_before_transcript_when_visible(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.show_starter_panel = True
    tui.starter_panel_pinned = True
    tui.store.add(Msg("user", "hi"))
    tui.store.add(Msg("assistant", "hello"))

    starter = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    chat = [_strip_ansi(line) for line in tui.renderer._build_chat_lines(110)]
    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(36, 110, 110)
    transcript_top = tui.renderer._transcript_top(len(starter), len(chat))
    prompt_top = tui.renderer._prompt_top(36, transcript_top, len(prompt_lines), len(chat))

    assert starter
    assert transcript_top == 2 + len(starter)
    assert prompt_top == transcript_top + len(chat)
    tui._task_executor.shutdown(wait=False)


def test_transcript_renders_compact_role_headers(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.store.add(Msg("user", "hi", ts="14:05"))
    tui.store.add(Msg("assistant", "hello back", label="◆ lumi", ts="14:05"))

    chat = [_strip_ansi(line) for line in tui.renderer._build_chat_lines(110)]
    joined = "\n".join(chat)

    assert "◆ lumi" not in joined
    assert "  › hi" in joined
    assert "  • hello back" in joined
    tui._task_executor.shutdown(wait=False)


def test_starter_header_aligns_with_transcript_markers(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.tui.session.random.choice",
        lambda _seq: "Tip: Use /voice [seconds] to record and transcribe straight into the prompt.",
    )
    tui = _make_tui(tmp_path, monkeypatch)
    tui.show_starter_panel = True
    tui.starter_panel_pinned = True
    tui.store.add(Msg("user", "hi"))

    starter = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    chat = [_strip_ansi(line) for line in tui.renderer._build_chat_lines(110)]
    header_line = next(line for line in starter if "Lumi Operator" in line)
    user_line = next(line for line in chat if line.strip().startswith("›"))

    assert "Lumi Operator" in header_line
    assert user_line.startswith("  ›")
    tui._task_executor.shutdown(wait=False)


def test_prompt_line_stays_flush_when_header_is_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.tui.session.random.choice",
        lambda _seq: "Tip: Use /doctor to check provider setup and runtime health.",
    )
    tui = _make_tui(tmp_path, monkeypatch)
    tui.show_starter_panel = True

    starter = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(36, 110, 110)
    prompt = [_strip_ansi(line) for line in prompt_lines]
    prompt_line = next(line for line in prompt if line.strip().startswith("›"))

    assert any("Lumi Operator" in line for line in starter)
    assert prompt[0].strip().startswith("─")
    assert "shortcuts" in prompt[-1]
    assert prompt_line.startswith("›")
    assert len(prompt[0]) == 110
    tui._task_executor.shutdown(wait=False)


def test_notification_bar_renders_boxed_status_toast(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.notification = "Model → gemini-2.5-flash"

    rendered = _strip_ansi(tui.renderer._notification_bar(30, 100))

    assert "╭" in rendered
    assert "╰" in rendered
    assert "status" in rendered
    assert "Model → gemini-2.5-flash" in rendered
    tui._task_executor.shutdown(wait=False)


def test_mode_missing_cli_shows_install_hint(tmp_path, monkeypatch):
    monkeypatch.setattr("src.tui.app.shutil.which", lambda _binary: None)
    tui = _make_tui(tmp_path, monkeypatch)
    tui.system_prompt = tui._make_system_prompt()

    registry.commands["/mode"]["func"](tui, "vessel gemini")

    assert tui._pending_handoff is None
    assert any("Gemini CLI is not installed" in msg.text for msg in tui.store.snapshot() if msg.role == "system")
    assert any("/mode vessel gemini again" in msg.text for msg in tui.store.snapshot() if msg.role == "system")
    tui._task_executor.shutdown(wait=False)


def test_mode_vessel_queues_installed_cli_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr("src.tui.app.shutil.which", lambda binary: f"/usr/bin/{binary}")
    tui = _make_tui(tmp_path, monkeypatch)
    tui.vessel_mode = True
    tui.active_vessel = "gemini"
    tui.system_prompt = "old prompt"

    registry.commands["/mode"]["func"](tui, "vessel codex")

    assert tui._pending_handoff is not None
    assert tui._pending_handoff["key"] == "codex"
    assert tui._pending_handoff["binary"] == "codex"
    assert tui.vessel_mode is False
    assert tui.active_vessel is None
    assert tui.system_prompt != "old prompt"
    tui._task_executor.shutdown(wait=False)


def test_mode_shorthand_still_queues_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr("src.tui.app.shutil.which", lambda binary: f"/usr/bin/{binary}")
    tui = _make_tui(tmp_path, monkeypatch)

    registry.commands["/mode"]["func"](tui, "qwen")

    assert tui._pending_handoff is not None
    assert tui._pending_handoff["key"] == "qwen"
    tui._task_executor.shutdown(wait=False)


def test_mode_requires_cli_name_after_vessel(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    registry.commands["/mode"]["func"](tui, "vessel")

    assert any("Usage: /mode vessel <name>" in msg.text for msg in tui.store.snapshot() if msg.role == "error")
    tui._task_executor.shutdown(wait=False)


def test_mode_conversations_opens_pane_for_saved_records(tmp_path, monkeypatch):
    from src.tui import mode_sessions

    tui = _make_tui(tmp_path, monkeypatch)
    monkeypatch.setattr("src.tui.app.shutil.which", lambda binary: f"/usr/bin/{binary}")
    mode_sessions.save_mode_conversation(
        cli_name="codex",
        display_name="Codex CLI",
        transcript="edited src/tui/app.py\nran pytest",
        summary={
            "tldr": "Adjusted the TUI prompt layout.",
            "files": ["src/tui/app.py"],
            "commands": ["pytest"],
            "decisions": ["Keep the prompt bordered."],
            "next_steps": ["Polish the status line."],
        },
        exit_code=0,
        cwd=str(tmp_path),
        started_at="2026-03-21T10:00:00",
        ended_at="2026-03-21T10:02:00",
        duration_seconds=120.0,
        git_branch="main",
        binary="codex",
        binary_path="/usr/bin/codex",
        binary_version="codex 1.0.0",
        captured=True,
    )

    registry.commands["/mode"]["func"](tui, "conversations codex prompt")

    assert tui.pane.active is True
    assert tui.pane.title == "mode conversations"
    assert any("Adjusted the TUI prompt layout." in line for line in tui.pane.content())
    tui._task_executor.shutdown(wait=False)


def test_rebirth_status_command_renders_capability_matrix(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    registry.commands["/rebirth"]["func"](tui, "status")

    assert any(
        msg.role == "system" and "capability matrix" in msg.text.lower()
        for msg in tui.store.snapshot()
    )
    tui._task_executor.shutdown(wait=False)


def test_rebirth_on_applies_profile_defaults(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui._compact = True
    tui.response_mode = "short"
    tui.guardian_enabled = False

    registry.commands["/rebirth"]["func"](tui, "on")

    assert tui.response_mode == "detailed"
    assert tui._compact is False
    assert tui.guardian_enabled is True
    tui._task_executor.shutdown(wait=False)


def test_identity_questions_answer_as_lumi(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._run_message("hi whats your name")

    messages = tui.store.snapshot()
    assert any(
        msg.role == "assistant"
        and "I’m Lumi" in msg.text
        and "terminal coding agent" in msg.text
        and "SardorchikDev" in msg.text
        for msg in messages
    )
    assert all("Claude Code" not in msg.text for msg in messages if msg.role == "assistant")
    tui._task_executor.shutdown(wait=False)


def test_identity_followup_reaffirms_lumi_without_model_fallback(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    def _unexpected_stream(*_args, **_kwargs):
        raise AssertionError("identity follow-up should not hit the model")

    tui._tui_stream = _unexpected_stream

    tui._run_message("who are you")
    tui._run_message("are you sure")

    assistant_messages = [msg.text for msg in tui.store.snapshot() if msg.role == "assistant"]

    assert any("I’m Lumi" in text for text in assistant_messages)
    assert any("not Codex CLI or Claude Code" in text for text in assistant_messages)
    assert all("I am Codex CLI" not in text for text in assistant_messages)
    tui._task_executor.shutdown(wait=False)


def test_first_casual_turn_uses_bootstrap_prompt_before_warmup_finishes(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.system_prompt = "BOOTSTRAP PROMPT"
    tui._startup_warmed = False

    def _unexpected_prompt(*_args, **_kwargs):
        raise AssertionError("first casual turn should not build the heavy prompt")

    captured: dict[str, object] = {}

    def _fake_stream(messages, _model, *_args, **_kwargs):
        captured["messages"] = messages
        return "hello back"

    tui._make_system_prompt = _unexpected_prompt
    tui._tui_stream = _fake_stream

    tui._run_message("hello")

    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][0]["content"].startswith("BOOTSTRAP PROMPT")
    tui._task_executor.shutdown(wait=False)


def test_creator_questions_answer_with_sardor_identity(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._run_message("do you know your creator")

    messages = tui.store.snapshot()
    assert any(
        msg.role == "assistant"
        and "Sardor Sodiqov" in msg.text
        and "SardorchikDev" in msg.text
        and "maintains the project" in msg.text
        for msg in messages
    )
    tui._task_executor.shutdown(wait=False)


def test_capability_questions_answer_with_lumi_self_profile(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._run_message("what can you do")

    messages = tui.store.snapshot()
    assert any(
        msg.role == "assistant"
        and "In Operator" in msg.text
        and "edit" in msg.text
        and "search the web" in msg.text
        and "/build" in msg.text
        and "skills" in msg.text
        for msg in messages
    )
    tui._task_executor.shutdown(wait=False)


def test_runtime_questions_answer_with_provider_and_model(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._run_message("what model are you using right now")

    messages = tui.store.snapshot()
    assert any(
        msg.role == "assistant"
        and "HuggingFace" in msg.text
        and "Llama-3.3-70B-Instruct" in msg.text
        and "effort=" in msg.text
        and "0.7.0 Operator" in msg.text
        for msg in messages
    )
    tui._task_executor.shutdown(wait=False)


def test_workspace_questions_answer_with_current_folder(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._run_message("what project are you in")

    messages = tui.store.snapshot()
    assert any(
        msg.role == "assistant"
        and str(tmp_path.name) in msg.text
        and "working in" in msg.text
        for msg in messages
    )
    tui._task_executor.shutdown(wait=False)


def test_memory_commands_remember_and_forget_fact(tmp_path, monkeypatch):
    from src.memory.longterm import get_facts

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    registry.commands["/remember"]["func"](tui, "User prefers TypeScript")
    assert get_facts() == ["User prefers TypeScript"]

    registry.commands["/forget"]["func"](tui, "1")
    assert get_facts() == []

    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Remembered fact #1" in msg.text for msg in messages)
    assert any(msg.role == "system" and "Forgot fact #1" in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)


def test_empty_state_keeps_prompt_under_starter_card(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    starter = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    prompt_lines, cursor_row, _cursor_col = tui.renderer._prompt_bar(36, 110, 110)
    prompt_lines = [_strip_ansi(line) for line in prompt_lines]
    prompt_top = tui.renderer._prompt_top(
        36,
        tui.renderer._transcript_top(len(starter), 0),
        len(prompt_lines),
        0,
    )
    resolved_cursor_row = tui.renderer._prompt_cursor_row(36, len(prompt_lines), prompt_top, cursor_row)

    assert any("Lumi Operator" in line for line in starter)
    assert prompt_top == 1 + len(starter)
    assert resolved_cursor_row == prompt_top + 1
    assert len(prompt_lines) == 4
    assert prompt_lines[0].strip().startswith("─")
    assert prompt_lines[1].strip().startswith("›")
    assert prompt_lines[2].strip().startswith("─")
    assert "inspect this repo" in prompt_lines[1]
    assert "shortcuts" in prompt_lines[3]
    tui._task_executor.shutdown(wait=False)


def test_ctrl_g_toggles_starter_panel(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    tui._handle_key("CTRL_G")
    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(90)]
    prompt_lines, cursor_row, _cursor_col = tui.renderer._prompt_bar(30, 90, 90)
    prompt = [_strip_ansi(line) for line in prompt_lines]
    prompt_top = tui.renderer._prompt_top(30, tui.renderer._transcript_top(0, 0), len(prompt_lines), 0)
    resolved_cursor_row = tui.renderer._prompt_cursor_row(30, len(prompt_lines), prompt_top, cursor_row)

    assert not lines
    assert prompt_top == 1
    assert resolved_cursor_row == prompt_top + 1
    assert any("›" in line for line in prompt)
    tui._task_executor.shutdown(wait=False)


def test_starter_panel_stays_visible_after_chat_begins(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.store.add(Msg("user", "hi"))

    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]

    assert any("Lumi Operator" in line for line in lines)
    tui._task_executor.shutdown(wait=False)


def test_ctrl_g_toggles_starter_panel_during_active_chat(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.store.add(Msg("user", "hi"))

    tui._handle_key("CTRL_G")
    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]

    assert lines == []
    assert tui.show_starter_panel is False
    assert tui.starter_panel_pinned is False

    tui._handle_key("CTRL_G")
    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]

    assert any("Lumi Operator" in line for line in lines)
    assert tui.show_starter_panel is True
    assert tui.starter_panel_pinned is True
    tui._task_executor.shutdown(wait=False)


def test_prompt_bar_renders_claude_style_rail(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(30, 90, 90)
    prompt = [_strip_ansi(line) for line in prompt_lines]

    assert len(prompt) == 4
    assert prompt[0].strip().startswith("─")
    assert prompt[1].strip().startswith("›")
    assert prompt[2].strip().startswith("─")
    assert "inspect this repo" in prompt[1]
    assert "shortcuts" in prompt[3]
    assert len(prompt[0]) == 90
    tui._task_executor.shutdown(wait=False)


def test_empty_prompt_shows_inline_placeholder_suggestion(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(30, 90, 90)
    prompt = [_strip_ansi(line) for line in prompt_lines]

    assert prompt[1].strip().startswith("›")
    assert "inspect this repo and tell me how it works" in prompt[1]
    assert "try:" not in "\n".join(prompt)
    assert "/claude.md create" not in "\n".join(prompt)
    tui._task_executor.shutdown(wait=False)


def test_resume_prefers_repo_autosave_for_current_workspace(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    history = [{"role": "user", "content": "repo hello"}, {"role": "assistant", "content": "repo hi"}]

    save_repo_autosave(history, base_dir=tmp_path)
    registry.commands["/load"]["func"](tui, "")

    messages = tui.memory.get()
    assert len(messages) == 2
    assert messages[0]["content"] == "repo hello"
    assert messages[1]["content"] == "repo hi"
    tui._task_executor.shutdown(wait=False)


def test_clear_resets_repo_autosave_slot(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    history = [{"role": "user", "content": "old chat"}, {"role": "assistant", "content": "old reply"}]
    save_repo_autosave(history, base_dir=tmp_path)
    tui.memory.set_history(history)

    registry.commands["/clear"]["func"](tui, "")

    assert load_repo_autosave(tmp_path) == []
    tui._task_executor.shutdown(wait=False)


def test_inline_placeholder_varies_with_repo_state_and_turns(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.turns = 3
    tui.workspace_profile = SimpleNamespace(
        changed_files=("src/tui/app.py",),
        verification_commands={"tests": ("pytest -q",)},
        frameworks=("FastAPI",),
    )

    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(30, 90, 90)
    prompt = [_strip_ansi(line) for line in prompt_lines]
    placeholder = prompt[1]

    expected = (
        "review the current changes and find issues",
        "summarize what changed and what looks risky",
        "trace the changed files and explain the impact",
        "check the diff for regressions and edge cases",
        "identify the highest-risk change before we merge anything",
        "show me which edit is most likely to break prod",
        "find the bug hiding in the latest changes",
        "tell me which edit is acting confident for no reason",
        "show me the diff line that is about to start drama",
    )

    assert prompt[1].strip().startswith("›")
    assert any(candidate in placeholder for candidate in expected)
    assert "try:" not in "\n".join(prompt)
    assert "/doctor" not in "\n".join(prompt)
    assert "/claude.md create" not in "\n".join(prompt)
    tui._task_executor.shutdown(wait=False)


def test_recent_commands_clear_between_tui_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.tui.session.random.choice",
        lambda _seq: "Tip: Use /doctor to check provider setup and runtime health.",
    )
    first = _make_tui(tmp_path, monkeypatch)
    first.redraw = lambda: None
    first.show_starter_panel = True
    first._execute_command("/clear", "")

    second = _make_tui(tmp_path, monkeypatch)
    second.little_notes = LittleNotesStore(tmp_path / "little_notes.json")
    second.recent_commands = second.little_notes.recent_commands[:3]
    second.show_starter_panel = True

    lines = [_strip_ansi(line) for line in second.renderer._build_starter_lines(110)]
    joined = "\n".join(lines)
    assert "/clear" not in joined
    assert "Operator" in joined

    first._task_executor.shutdown(wait=False)
    second._task_executor.shutdown(wait=False)


def test_starter_panel_hides_session_summary_in_minimal_mode(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.show_starter_panel = True
    tui.little_notes.record_action("Created 2 file(s) and 1 folder(s).")
    tui.recent_actions = tui.little_notes.recent_actions[:4]

    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    joined = "\n".join(lines)

    assert "HuggingFace" in joined
    assert "Created 2 file(s) and 1 folder(s)." not in joined
    tui._task_executor.shutdown(wait=False)


def test_pending_plan_changes_prompt_hint(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui._pending_file_plan = {"plan": {"operation": "delete"}, "base_dir": str(tmp_path), "inspection": {}}

    lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(36, 110, 110)
    lines = [_strip_ansi(line) for line in lines]
    joined = "\n".join(lines)

    assert "confirm removal" in joined
    assert "y apply" in joined
    assert any(line.strip().startswith("─") for line in lines)
    tui._task_executor.shutdown(wait=False)


def test_pending_plan_renders_inline_review_panel(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui._pending_file_plan = {
        "plan": {"operation": "delete", "targets": [{"path": "docs", "kind": "dir"}]},
        "base_dir": str(tmp_path),
        "inspection": {
            "summary_lines": ["1 folder will be removed", "2 files are inside"],
            "preview_lines": ["- docs/", "- docs/README.md"],
        },
    }

    lines = [_strip_ansi(line) for line in tui.renderer._build_starter_lines(110)]
    joined = "\n".join(lines)

    assert "review removal" in joined
    assert "1 folder will be removed" in joined
    assert "docs/README.md" in joined
    tui._task_executor.shutdown(wait=False)


def test_escape_cancels_pending_file_plan(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._pending_file_plan = {
        "plan": {"operation": "delete", "targets": [{"path": "docs", "kind": "dir"}]},
        "base_dir": str(tmp_path),
        "inspection": {},
    }

    tui._handle_key("ESC")

    assert tui._pending_file_plan is None
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Removal cancelled." in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)


def test_escape_closes_transient_ui_and_clears_prompt(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.shortcuts_visible = True
    tui.browser_visible = True
    tui.slash_visible = True
    tui.path_visible = True
    tui.path_hits = ["src/app.py"]
    tui.picker_visible = True
    tui.buf = "/help"
    tui.cur_pos = len(tui.buf)

    tui._handle_key("ESC")

    assert tui.shortcuts_visible is False
    assert tui.browser_visible is False
    assert tui.slash_visible is False
    assert tui.path_visible is False
    assert tui.path_hits == []
    assert tui.picker_visible is False
    assert tui.buf == ""
    assert tui.cur_pos == 0
    tui._task_executor.shutdown(wait=False)


def test_question_mark_toggles_shortcuts_popup_when_prompt_is_empty(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._handle_key("?")

    assert tui.shortcuts_visible is True
    popup = tui.renderer._shortcuts_popup(30, 90)
    first_cursor = re.match(r"\x1b\[(\d+);(\d+)H", popup)

    assert first_cursor is not None
    assert first_cursor.group(2) == "1"
    assert "Ctrl+N" in _strip_ansi(popup)
    assert "open the model picker" in _strip_ansi(popup)

    tui._handle_key("?")

    assert tui.shortcuts_visible is False
    tui._task_executor.shutdown(wait=False)


def test_question_mark_is_inserted_into_prompt_when_typing(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.buf = "who"
    tui.cur_pos = len(tui.buf)

    tui._handle_key("?")

    assert tui.shortcuts_visible is False
    assert tui.buf == "who?"
    assert tui.cur_pos == len("who?")
    tui._task_executor.shutdown(wait=False)


def test_bracketed_paste_inserts_multiline_text_without_submitting(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._handle_key(("PASTE", "line one\nline two"))

    assert tui.buf == "line one\nline two"
    assert tui.cur_pos == len("line one\nline two")
    assert tui.store.snapshot() == []
    tui._task_executor.shutdown(wait=False)


def test_bracketed_paste_updates_picker_query(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr(
        "src.tui.app.get_models",
        lambda provider=None: ["meta-llama/Llama-3.3-70B-Instruct", "Qwen/Qwen3-Coder"],
    )
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._open_picker()
    tui.picker_stage = "models"
    tui.picker_provider_key = "huggingface"
    tui._refresh_picker()

    tui._handle_key(("PASTE", "qwen"))

    assert tui.picker_query == "qwen"
    assert any(item.get("value") == "Qwen/Qwen3-Coder" for item in tui.picker_items if item.get("kind") == "model")
    tui._task_executor.shutdown(wait=False)


def test_empty_prompt_arrow_keys_scroll_transcript(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._handle_key("UP")
    assert tui.scroll_offset == 3

    tui._handle_key("DOWN")
    assert tui.scroll_offset == 0
    tui._task_executor.shutdown(wait=False)


def test_arrow_keys_keep_history_navigation_when_prompt_has_text(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    seen: list[int] = []
    tui.buf = "who"
    tui.cur_pos = len(tui.buf)
    tui._hist_nav = lambda direction: seen.append(direction)

    tui._handle_key("UP")
    tui._handle_key("DOWN")

    assert seen == [-1, 1]
    assert tui.scroll_offset == 0
    tui._task_executor.shutdown(wait=False)


def test_busy_state_blocks_typing_and_escape_requests_stop(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.busy = True
    tui.buf = "draft"
    tui.cur_pos = len(tui.buf)

    tui._handle_key("a")

    assert tui.buf == "draft"
    assert tui.cur_pos == len("draft")

    tui._handle_key("ESC")

    assert tui.stop_requested() is True
    tui._task_executor.shutdown(wait=False)


def test_escape_closes_closeable_side_pane(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.set_pane(title="live command", subtitle="pytest -q", lines=["running"], close_on_escape=True)

    tui._handle_key("ESC")

    assert tui.pane_active is False
    assert tui.pane.active is False
    tui._task_executor.shutdown(wait=False)


def test_escape_closes_mode_return_review_card(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.set_review_card(
        title="claude return",
        summary_lines=["cli: Claude Code", "cwd: /home/sadi/Lumi"],
        preview_lines=["Returned from Claude Code after discussing work."],
        footer="Esc close  ·  /mode conversations",
    )

    tui._handle_key("ESC")

    assert tui.review_card.active is False
    tui._task_executor.shutdown(wait=False)


def test_pending_file_plan_confirmation_creates_files_without_chat_fallback(tmp_path, monkeypatch):
    class FailingExecutor:
        def submit(self, *_args, **_kwargs):
            raise AssertionError("pending file plan should not fall through to chat execution")

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._task_executor.shutdown(wait=False)
    tui._task_executor = FailingExecutor()
    tui._pending_file_plan = (
        {
            "root": "docs",
            "files": [{"path": "README.md", "content": "# hello\n"}],
        },
        str(tmp_path),
    )
    tui.buf = "yes"
    tui.cur_pos = len(tui.buf)

    tui._handle_key("ENTER")

    assert tui._pending_file_plan is None
    assert (tmp_path / "docs").is_dir()
    assert (tmp_path / "docs" / "README.md").read_text(encoding="utf-8") == "# hello\n"
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Created" in msg.text for msg in messages)


def test_pending_delete_plan_confirmation_removes_paths_without_chat_fallback(tmp_path, monkeypatch):
    class FailingExecutor:
        def submit(self, *_args, **_kwargs):
            raise AssertionError("pending delete plan should not fall through to chat execution")

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._task_executor.shutdown(wait=False)
    tui._task_executor = FailingExecutor()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# hello\n", encoding="utf-8")
    tui._pending_file_plan = (
        {
            "operation": "delete",
            "targets": [{"path": "docs", "kind": "dir"}],
        },
        str(tmp_path),
    )
    tui.buf = "yes"
    tui.cur_pos = len(tui.buf)

    tui._handle_key("ENTER")

    assert tui._pending_file_plan is None
    assert not (tmp_path / "docs").exists()
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Removed" in msg.text for msg in messages)


def test_path_suggestions_complete_with_tab(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    tui.buf = "delete src/a"
    tui.cur_pos = len(tui.buf)

    tui._update_slash()

    assert tui.path_visible is True
    assert "src/app.py" in tui.path_hits
    tui._handle_key("TAB")
    assert tui.buf == "delete src/app.py"
    tui._task_executor.shutdown(wait=False)


def test_multiline_enter_inserts_newline_and_prompt_shows_content(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.multiline = True
    tui.buf = "hello"
    tui.cur_pos = len(tui.buf)

    tui._handle_key("ENTER")
    tui.buf += "world"
    tui.cur_pos = len(tui.buf)

    lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(36, 110, 110)
    lines = [_strip_ansi(line) for line in lines]
    joined = "\n".join(lines)

    assert tui.buf == "hello\nworld"
    assert "› hello" in joined
    assert "world" in joined
    tui._task_executor.shutdown(wait=False)


def test_workspace_trust_popup_renders_access_prompt(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.workspace_trust_visible = True

    popup = _strip_ansi(tui.renderer._workspace_trust_popup(36, 110))

    assert "Accessing workspace:" in popup
    assert str(tmp_path) in popup
    assert "Yes, I trust this folder" in popup
    assert "No, exit" in popup
    tui._task_executor.shutdown(wait=False)


def test_workspace_trust_prompt_accepts_current_folder(tmp_path, monkeypatch):
    trust_file = tmp_path / "trusted_workspaces.json"
    monkeypatch.setattr("src.tui.app._WORKSPACE_TRUST_FILE", trust_file)
    tui = _make_tui(tmp_path, monkeypatch)
    tui.workspace_trust_visible = True
    tui.redraw = lambda: None

    tui._handle_key("ENTER")

    assert tui.workspace_trust_visible is False
    assert str(tmp_path.resolve()) in trust_file.read_text(encoding="utf-8")
    tui._task_executor.shutdown(wait=False)


def test_effort_command_accepts_ehigh_and_updates_request_profile(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.client = object()
    captured: dict[str, object] = {}

    def fake_chat_stream(client, messages, model, max_tokens, temperature, on_delta=None, on_status=None):
        captured["client"] = client
        captured["messages"] = messages
        captured["model"] = model
        captured["max_tokens"] = max_tokens
        captured["temperature"] = temperature
        if on_delta is not None:
            on_delta("ok")
        return "ok"

    monkeypatch.setattr("src.tui.app.chat_stream", fake_chat_stream)

    registry.commands["/effort"]["func"](tui, "ehigh")
    reply = tui._tui_stream(
        [{"role": "system", "content": "You are Lumi."}, {"role": "user", "content": "solve this carefully"}],
        "demo-model",
    )

    assert reply == "ok"
    assert tui.reasoning_effort == "ehigh"
    assert captured["client"] is tui.client
    assert captured["max_tokens"] == 16384
    assert captured["temperature"] == 0.1
    assert "Reasoning effort: extra high." in str(captured["messages"][0]["content"])
    tui._task_executor.shutdown(wait=False)


def test_tui_defaults_to_medium_effort_with_tighter_chat_budget(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.client = object()
    captured: dict[str, object] = {}

    def fake_chat_stream(client, messages, model, max_tokens, temperature, on_delta=None, on_status=None):
        captured["messages"] = messages
        captured["max_tokens"] = max_tokens
        captured["temperature"] = temperature
        if on_delta is not None:
            on_delta("ok")
        return "ok"

    monkeypatch.setattr("src.tui.app.chat_stream", fake_chat_stream)

    reply = tui._tui_stream(
        [{"role": "system", "content": "You are Lumi."}, {"role": "user", "content": "answer this"}],
        "demo-model",
    )

    assert reply == "ok"
    assert tui.reasoning_effort == "medium"
    assert captured["max_tokens"] == 4096
    assert captured["temperature"] == 0.7
    assert str(captured["messages"][0]["content"]) == "You are Lumi."
    tui._task_executor.shutdown(wait=False)


def test_silent_call_honors_low_effort(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.reasoning_effort = "low"
    captured: dict[str, object] = {}

    class DummyCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="done"))],
                usage=SimpleNamespace(completion_tokens=12),
            )

    tui.client = SimpleNamespace(chat=SimpleNamespace(completions=DummyCompletions()))
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr("src.tui.app.get_models", lambda provider=None: ["demo-model"])
    monkeypatch.setattr("src.tui.app.route_model", lambda model, available, mode, provider=None: model)

    reply = tui._silent_call("Summarize this.", "demo-model", max_tokens=1000)

    assert reply == "done"
    assert captured["max_tokens"] == 1000
    assert captured["temperature"] == 1.0
    assert "Reasoning effort: low." in str(captured["messages"][0]["content"])
    tui._task_executor.shutdown(wait=False)


def test_registry_fuzzy_hits_match_non_contiguous_queries():
    hits = registry.get_hits("/prj")

    assert any(hit[0] == "/project" for hit in hits)


def test_side_pane_renders_title_subtitle_and_footer(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.set_pane(
        title="live command",
        subtitle="pytest -q",
        lines=["collected 1 item", "tests/test_tui.py ."],
        footer="Esc close",
        close_on_escape=True,
    )

    lines = [_strip_ansi(line) for line in tui.renderer._build_pane_lines(40, 12)]
    joined = "\n".join(lines)

    assert "live command" in joined
    assert "pytest -q" in joined
    assert "collected 1 item" in joined
    assert "Esc close" in joined
    tui._task_executor.shutdown(wait=False)


def test_model_picker_opens_in_provider_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr("src.tui.app.get_models", lambda provider=None: ["meta-llama/Llama-3.3-70B-Instruct"])
    tui = _make_tui(tmp_path, monkeypatch)

    tui._open_picker()

    assert tui.picker_visible is True
    assert tui.picker_stage == "providers"
    assert any(item.get("kind") == "provider" for item in tui.picker_items)
    assert tui.picker_preview_lines == []
    tui._task_executor.shutdown(wait=False)


def test_picker_popup_anchors_below_top_prompt_on_left(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr("src.tui.app.get_models", lambda provider=None: ["meta-llama/Llama-3.3-70B-Instruct"])
    tui = _make_tui(tmp_path, monkeypatch)

    tui._open_picker()
    starter = tui.renderer._build_starter_lines(90)
    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(30, 90, 90)
    prompt_top = tui.renderer._prompt_top(
        30,
        tui.renderer._transcript_top(len(starter), 0),
        len(prompt_lines),
        0,
    )
    popup = tui.renderer._picker_popup(30, 90)
    first_cursor = re.match(r"\x1b\[(\d+);(\d+)H", popup)

    assert first_cursor is not None
    assert first_cursor.group(2) == "1"
    assert int(first_cursor.group(1)) > prompt_top
    tui._task_executor.shutdown(wait=False)


def test_browser_popup_anchors_below_top_prompt_on_left(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.browser_visible = True
    tui.browser_cwd = str(tmp_path)
    tui.browser_items = [("file", "app.py", str(tmp_path / "app.py"))]

    starter = tui.renderer._build_starter_lines(90)
    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(30, 90, 90)
    prompt_top = tui.renderer._prompt_top(
        30,
        tui.renderer._transcript_top(len(starter), 0),
        len(prompt_lines),
        0,
    )
    popup = tui.renderer._browser_popup(30, 90)
    first_cursor = re.match(r"\x1b\[(\d+);(\d+)H", popup)

    assert first_cursor is not None
    assert first_cursor.group(2) == "1"
    assert int(first_cursor.group(1)) > prompt_top
    tui._task_executor.shutdown(wait=False)


def test_browser_popup_stays_compact_and_shows_paging_hint(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.browser_visible = True
    tui.browser_cwd = str(tmp_path)
    tui.browser_items = [("dir", f"dir-{index}", str(tmp_path / f"dir-{index}")) for index in range(24)]
    tui.browser_sel = 12

    popup = _strip_ansi(tui.renderer._browser_popup(30, 90))
    assert "PgUp/PgDn" in popup
    assert "browser ↑ ↓" in popup
    assert popup.count("dir-") <= 10
    tui._task_executor.shutdown(wait=False)


def test_slash_popup_renders_codex_style_command_and_description(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.buf = "/"
    tui.cur_pos = 1
    tui._update_slash()

    popup = _strip_ansi(tui.renderer._slash_popup(30, 90))

    assert "[settings]" not in popup
    assert "/agent" in popup
    assert "Plan a multi-step agent workflow" in popup
    tui._task_executor.shutdown(wait=False)


def test_slash_popup_stays_below_top_prompt_rail(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.buf = "/"
    tui.cur_pos = 1
    tui._update_slash()

    prompt_lines, _cursor_row, _cursor_col = tui.renderer._prompt_bar(30, 90, 90)
    starter = tui.renderer._build_starter_lines(90)
    prompt_top = tui.renderer._prompt_top(
        30,
        tui.renderer._transcript_top(len(starter), 0),
        len(prompt_lines),
        0,
    )
    popup = tui.renderer._slash_popup(30, 90)
    rows = [int(match) for match, _col in re.findall(r"\x1b\[(\d+);(\d+)H", popup)]

    assert rows
    assert min(rows) > prompt_top
    tui._task_executor.shutdown(wait=False)


def test_slash_hits_include_workspace_skill(tmp_path, monkeypatch):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "release.md").write_text(
        "---\nname: Release Helper\ncommand: /release\n---\nDraft release notes for {{args}}.\n",
        encoding="utf-8",
    )
    tui = _make_tui(tmp_path, monkeypatch)
    tui.buf = "/rel"
    tui.cur_pos = len(tui.buf)

    tui._update_slash()

    assert any(hit[0] == "/release" for hit in tui.slash_hits)
    tui._task_executor.shutdown(wait=False)


def test_page_keys_scroll_browser_popup_selection(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.browser_visible = True
    tui.browser_items = [("dir", f"dir-{index}", str(tmp_path / f"dir-{index}")) for index in range(24)]
    tui.browser_sel = 0

    tui._handle_key("PGDN")
    assert tui.browser_sel > 0

    tui._handle_key("PGUP")
    assert tui.browser_sel == 0
    tui._task_executor.shutdown(wait=False)


def test_mouse_wheel_scrolls_transcript(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._handle_key("WHEEL_UP")
    assert tui.scroll_offset == 3

    tui._handle_key("WHEEL_DOWN")
    assert tui.scroll_offset == 0
    tui._task_executor.shutdown(wait=False)


def test_mouse_wheel_scrolls_browser_popup_selection(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.browser_visible = True
    tui.browser_items = [("dir", f"dir-{index}", str(tmp_path / f"dir-{index}")) for index in range(24)]
    tui.browser_sel = 5

    tui._handle_key("WHEEL_UP")
    assert tui.browser_sel == 4

    tui._handle_key("WHEEL_DOWN")
    assert tui.browser_sel == 5
    tui._task_executor.shutdown(wait=False)


def test_mouse_wheel_scrolls_model_picker_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "gemini")
    monkeypatch.setattr(
        "src.tui.app.get_models",
        lambda provider=None: [f"gemini-model-{index}" for index in range(12)],
    )
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._open_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("value") == "gemini")
    tui._confirm_picker()
    first_model_index = next(index for index, item in enumerate(tui.picker_items) if item.get("kind") == "model")
    tui.picker_sel = first_model_index + 3

    tui._handle_key("WHEEL_UP")
    assert tui.picker_sel == first_model_index + 2

    tui._handle_key("WHEEL_DOWN")
    assert tui.picker_sel == first_model_index + 3
    tui._task_executor.shutdown(wait=False)


def test_model_picker_lists_only_configured_providers(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr("src.tui.app.get_models", lambda provider=None: ["meta-llama/Llama-3.3-70B-Instruct"])
    tui = _make_tui(tmp_path, monkeypatch)

    tui._open_picker()

    provider_values = [item.get("value") for item in tui.picker_items if item.get("kind") == "provider"]
    assert provider_values == ["gemini", "huggingface"] or provider_values == ["huggingface", "gemini"]
    assert "council" not in provider_values
    assert all(item.get("kind") != "provider" or item.get("disabled") is False for item in tui.picker_items)
    assert all(item.get("label") != "Requires setup" for item in tui.picker_items)
    tui._task_executor.shutdown(wait=False)


def test_model_picker_provider_confirm_enters_model_stage_and_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")

    def fake_models(provider=None):
        if provider == "gemini":
            return ["gemini-2.5-flash-lite", "gemini-2.5-pro"]
        return ["meta-llama/Llama-3.3-70B-Instruct"]

    monkeypatch.setattr("src.tui.app.get_models", fake_models)
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._open_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("value") == "gemini")
    tui._confirm_picker()

    assert tui.picker_stage == "models"
    assert tui.picker_provider_key == "gemini"
    assert any(item.get("kind") == "model" for item in tui.picker_items)

    tui._handle_key("l")
    tui._handle_key("i")
    tui._handle_key("t")

    model_values = [item.get("value") for item in tui.picker_items if item.get("kind") == "model"]
    assert model_values == ["gemini-2.5-flash-lite"]
    tui._task_executor.shutdown(wait=False)


def test_model_picker_can_toggle_favorite_model(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr("src.tui.app.get_models", lambda provider=None: ["gemini-2.5-flash-lite"] if provider == "gemini" else ["meta-llama/Llama-3.3-70B-Instruct"])
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._open_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("value") == "gemini")
    tui._confirm_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("kind") == "model")

    tui._handle_key("CTRL_F")

    assert "gemini-2.5-flash-lite" in tui.little_notes.favorite_models_for_provider("gemini")
    tui._task_executor.shutdown(wait=False)


def test_model_picker_uses_icons_without_preview_documentation(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr(
        "src.tui.app.get_models",
        lambda provider=None: ["gemini-2.5-flash-image", "gemini-2.5-flash"] if provider == "gemini" else ["meta-llama/Llama-3.3-70B-Instruct"],
    )

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._open_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("value") == "gemini")
    tui._confirm_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("value") == "gemini-2.5-flash-image")

    image_item = next(item for item in tui.picker_items if item.get("value") == "gemini-2.5-flash-image")
    popup = _strip_ansi(tui.renderer._picker_popup(30, 90))

    assert image_item["icon"] == "󰉏"
    assert tui.picker_preview_lines == []
    assert "Tags:" not in popup
    tui._task_executor.shutdown(wait=False)


def test_build_plan_command_opens_workbench_plan_pane(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    monkeypatch.setattr("src.tui.command_groups.prepare_workbench_plan", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr("src.tui.command_groups.render_workbench_plan", lambda _plan: "Operator\nbuild plan")

    registry.commands["/build"]["func"](tui, "--plan add search")

    assert tui.pane_active is True
    assert tui.pane.title == "build plan"
    assert "Operator" in "\n".join(tui.pane.content())
    tui._task_executor.shutdown(wait=False)


def test_learn_command_opens_workbench_report_pane(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    monkeypatch.setattr("src.tui.command_groups.render_workbench_report", lambda *_args, **_kwargs: "Operator\nrepo map")

    registry.commands["/learn"]["func"](tui, "architecture")

    assert tui.pane_active is True
    assert tui.pane.title == "workbench learn"
    assert "repo map" in "\n".join(tui.pane.content())
    tui._task_executor.shutdown(wait=False)


def test_launch_workbench_keeps_existing_non_jobs_pane(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    _patch_inline_thread(monkeypatch)
    tui._notify = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    monkeypatch.setattr(
        "src.tui.app.execute_workbench",
        lambda *_args, **_kwargs: SimpleNamespace(summary="created game", risk_level="low"),
    )
    monkeypatch.setattr("src.tui.app.render_workbench_result", lambda result: f"workbench ok: {result.summary}")

    tui.set_pane(title="browser", subtitle="cwd", lines=["src"], close_on_escape=True)
    tui.launch_workbench("build", "a simple number guessing python game")

    assert tui.pane_active is True
    assert tui.pane.title == "browser"
    assert tui.workbench_jobs[0]["status"] == "done"
    assert tui.workbench_jobs[0]["summary"] == "created game"
    assert tui.agent_active_objective is None
    assert any(msg.role == "system" and "workbench ok: created game" in msg.text for msg in tui.store.snapshot())
    tui._task_executor.shutdown(wait=False)


def test_launch_workbench_refreshes_jobs_pane_when_visible(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    _patch_inline_thread(monkeypatch)
    tui._notify = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    monkeypatch.setattr(
        "src.tui.app.execute_workbench",
        lambda *_args, **_kwargs: SimpleNamespace(summary="created game", risk_level="low"),
    )
    monkeypatch.setattr("src.tui.app.render_workbench_result", lambda result: f"workbench ok: {result.summary}")

    registry.commands["/jobs"]["func"](tui, "")
    tui.launch_workbench("build", "a simple number guessing python game")

    assert tui.pane_active is True
    assert tui.pane.title == "workbench jobs"
    assert any("[done] build" in line for line in tui.pane.lines)
    assert any("summary: created game" in line for line in tui.pane.lines)
    tui._task_executor.shutdown(wait=False)


def test_launch_workbench_failure_marks_job_and_clears_agent_state(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    _patch_inline_thread(monkeypatch)
    tui._notify = lambda *_args, **_kwargs: None  # type: ignore[method-assign]

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.tui.app.execute_workbench", _boom)

    tui.launch_workbench("build", "broken task")

    assert tui.workbench_jobs[0]["status"] == "failed"
    assert tui.workbench_jobs[0]["stage"] == "failed"
    assert tui.agent_active_objective is None
    assert tui.agent_tasks == []
    assert any(msg.role == "error" and "build failed: boom" in msg.text for msg in tui.store.snapshot())
    tui._task_executor.shutdown(wait=False)


def test_review_without_target_queues_workbench_review_job(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def _launch(mode: str, objective: str, *, dry_run: bool = False) -> str:
        captured["mode"] = mode
        captured["objective"] = objective
        captured["dry_run"] = dry_run
        return "wb-1"

    tui.launch_workbench = _launch  # type: ignore[method-assign]

    registry.commands["/review"]["func"](tui, "")

    assert captured["mode"] == "review"
    assert captured["dry_run"] is True
    assert "workspace changes" in str(captured["objective"]).lower()
    assert any("Queued review job" in msg.text for msg in tui.store.snapshot() if msg.role == "system")
    tui._task_executor.shutdown(wait=False)


def test_model_picker_filter_matches_best_coding_tag(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr(
        "src.tui.app.get_models",
        lambda provider=None: ["Qwen/Qwen2.5-Coder-32B-Instruct", "meta-llama/Llama-3.3-70B-Instruct"],
    )

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._open_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("value") == "huggingface")
    tui._confirm_picker()
    tui.picker_query = "best coding"
    tui._refresh_picker()

    model_values = [item.get("value") for item in tui.picker_items if item.get("kind") == "model"]
    assert model_values == ["Qwen/Qwen2.5-Coder-32B-Instruct"]
    tui._task_executor.shutdown(wait=False)


def test_model_picker_shows_full_gemini_list_without_group_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")

    gemini_models = [f"gemini-model-{index}" for index in range(15)]

    def fake_models(provider=None):
        if provider == "gemini":
            return gemini_models
        return ["meta-llama/Llama-3.3-70B-Instruct"]

    monkeypatch.setattr("src.tui.app.get_models", fake_models)
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._open_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("value") == "gemini")
    tui._confirm_picker()

    model_values = [item.get("value") for item in tui.picker_items if item.get("kind") == "model"]
    assert model_values == gemini_models
    tui._task_executor.shutdown(wait=False)


def test_model_picker_respects_env_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "y")
    monkeypatch.setenv("LUMI_GEMINI_MODELS", "gemini-2.5-pro")
    monkeypatch.delenv("LUMI_ALLOWED_MODELS", raising=False)
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr(
        "src.tui.app.get_models",
        lambda provider=None: ["gemini-2.5-flash", "gemini-2.5-pro"] if provider == "gemini" else ["meta-llama/Llama-3.3-70B-Instruct"],
    )

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._open_picker()
    tui.picker_sel = next(index for index, item in enumerate(tui.picker_items) if item.get("value") == "gemini")
    tui._confirm_picker()

    model_values = [item.get("value") for item in tui.picker_items if item.get("kind") == "model"]
    assert model_values == ["gemini-2.5-pro"]
    assert any(
        item.get("kind") == "hint" and ".env model allowlist active" in item.get("label", "")
        for item in tui.picker_items
    )
    tui._task_executor.shutdown(wait=False)


def test_undo_restores_last_filesystem_action(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._pending_file_plan = {
        "plan": {"operation": "create", "root": ".", "files": [{"path": "notes.txt", "content": "hello\n"}]},
        "base_dir": str(tmp_path),
        "inspection": {},
    }
    tui.buf = "yes"
    tui.cur_pos = len(tui.buf)
    tui._handle_key("ENTER")
    assert (tmp_path / "notes.txt").exists()

    tui._execute_command("/undo", "")

    assert not (tmp_path / "notes.txt").exists()
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Undid filesystem action" in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)


def test_fs_mkdir_queues_preview_instead_of_mutating_immediately(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._execute_command("/fs", "mkdir docs")

    assert tui._pending_file_plan is not None
    assert not (tmp_path / "docs").exists()
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Filesystem plan" in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)


def test_permissions_command_renders_permission_report(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    tui._execute_command("/permissions", "all")

    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Tool permissions" in msg.text for msg in messages)
    assert any(msg.role == "system" and "Plugin permissions" in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)


def test_command_palette_toggles_and_surfaces_recent_prompt(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui.history.entries.append("explain this repository")

    tui._handle_key("CTRL_P")

    assert tui.command_palette_visible is True
    assert any(item["kind"] == "prompt" and item["value"] == "explain this repository" for item in tui.command_palette_hits)

    tui._handle_key("ESC")

    assert tui.command_palette_visible is False
    tui._task_executor.shutdown(wait=False)


def test_transcript_renders_tool_rows_inline(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.store.add(
        Msg(
            "tool",
            "✓ 230ms",
            label="edit_file  src/core/session.py",
            meta={"status": "done", "ok": True, "duration_ms": 230},
        )
    )

    lines = [_strip_ansi(line) for line in tui.renderer._build_chat_lines(110)]

    assert any("✓ edit_file  src/core/session.py  ✓ 230ms" in line for line in lines)
    tui._task_executor.shutdown(wait=False)


def test_permission_popup_renders_modal(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)
    tui.permission_prompt.active = True
    tui.permission_prompt.tool_name = "run_shell"
    tui.permission_prompt.display = "$ pytest tests/ -q"
    tui.permission_prompt.rule_hint = "run_shell:pytest *"
    tui.permission_prompt.selected = 1
    tui.permission_prompt_active = True

    rendered = _strip_ansi(tui.renderer._permission_popup(30, 100))

    assert "Permission required" in rendered
    assert "run_shell" in rendered
    assert "pytest tests/ -q" in rendered
    assert "[Allow Always]" in rendered
    tui._task_executor.shutdown(wait=False)


def test_skill_command_executes_through_chat_runtime(tmp_path, monkeypatch):
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "release.md").write_text(
        "---\nname: Release Helper\ncommand: /release\n---\nDraft release notes for {{args}}.\n",
        encoding="utf-8",
    )
    tui = _make_tui(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def fake_stream(messages, _model, *_args):
        captured["messages"] = messages
        return "Release notes ready."

    tui._tui_stream = fake_stream

    tui._execute_command("/release", "v0.7.0")

    messages = tui.store.snapshot()
    assert any(msg.role == "user" and msg.text == "/release v0.7.0" for msg in messages)
    assert tui.last_reply == "Release notes ready."
    assert "Draft release notes for v0.7.0." in captured["messages"][-1]["content"]
    tui._task_executor.shutdown(wait=False)


def test_onboard_command_renders_guidance(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    tui._execute_command("/onboard", "")

    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Lumi onboarding" in msg.text for msg in messages)
    assert any(msg.role == "system" and "Starter prompts" in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)


def test_image_command_auto_routes_to_gemini_and_streams_reply(tmp_path, monkeypatch):
    class ImmediateThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            if self._target is not None:
                self._target(*self._args, **self._kwargs)

    class FakeChunk:
        def __init__(self, text: str):
            self.choices = [type("Choice", (), {"delta": type("Delta", (), {"content": text})()})()]

    class FakeCompletions:
        def __init__(self):
            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return [FakeChunk("It looks"), FakeChunk(" like a test.")]

    class FakeClient:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00")
    fake_client = FakeClient()

    monkeypatch.setattr("src.tui.app.threading.Thread", ImmediateThread)
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr(
        "src.tui.app.get_models",
        lambda provider=None: ["gemini-2.5-flash"] if provider == "gemini" else ["meta-llama/Llama-3.3-70B-Instruct"],
    )
    monkeypatch.setattr("src.tui.app.make_provider_client", lambda provider: fake_client)

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._execute_command("/image", f"{image_path} what is in this image?")

    assert tui.last_reply == "It looks like a test."
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Using Gemini vision via gemini-2.5-flash." in msg.text for msg in messages)
    payload = fake_client.chat.completions.calls[0]
    content = payload["messages"][1]["content"]
    assert content[0]["text"] == "what is in this image?"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    tui._task_executor.shutdown(wait=False)


def test_image_command_reports_missing_file(tmp_path, monkeypatch):
    tui = _make_tui(tmp_path, monkeypatch)

    tui._execute_command("/image", "missing.png what is this")

    messages = tui.store.snapshot()
    assert any(msg.role == "error" and "Not found:" in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)


def test_imagine_command_auto_routes_to_gemini_and_saves_image(tmp_path, monkeypatch):
    class ImmediateThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            if self._target is not None:
                self._target(*self._args, **self._kwargs)

    output_path = tmp_path / "generated.png"

    monkeypatch.setattr("src.tui.app.threading.Thread", ImmediateThread)
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "huggingface")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["huggingface", "gemini"])
    monkeypatch.setattr(
        "src.tui.app.get_models",
        lambda provider=None: ["gemini-2.5-flash-image"] if provider == "gemini" else ["meta-llama/Llama-3.3-70B-Instruct"],
    )
    monkeypatch.setattr(
        "src.tui.app.generate_gemini_images",
        lambda prompt, source_image=None, model="gemini-2.5-flash-image": ([output_path], "Rendered successfully."),
    )

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._execute_command("/imagine", "a glowing banana throne in a marble room")

    assert "Generated image with Nano Banana" in tui.last_reply
    assert str(output_path) in tui.last_reply
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Using Gemini image generation via gemini-2.5-flash-image." in msg.text for msg in messages)
    assert any(msg.role == "system" and "Saved image" in msg.text for msg in messages)
    tui._task_executor.shutdown(wait=False)


def test_imagine_command_accepts_source_image_for_edits(tmp_path, monkeypatch):
    class ImmediateThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            if self._target is not None:
                self._target(*self._args, **self._kwargs)

    source = tmp_path / "logo.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n\x00")
    captured: dict[str, object] = {}

    monkeypatch.setattr("src.tui.app.threading.Thread", ImmediateThread)
    monkeypatch.setattr("src.tui.app.get_provider", lambda: "gemini")
    monkeypatch.setattr("src.tui.app.get_available_providers", lambda: ["gemini"])
    monkeypatch.setattr("src.tui.app.get_models", lambda provider=None: ["gemini-2.5-flash-image"])

    def fake_generate(prompt, source_image=None, model="gemini-2.5-flash-image"):
        captured["prompt"] = prompt
        captured["source_image"] = source_image
        captured["model"] = model
        return ([tmp_path / "edited.png"], "")

    monkeypatch.setattr("src.tui.app.generate_gemini_images", fake_generate)

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None

    tui._execute_command("/imagine", f"{source} add a gold frame around this logo")

    assert captured["prompt"] == "add a gold frame around this logo"
    assert captured["source_image"] == source
    tui._task_executor.shutdown(wait=False)


def test_voice_command_records_and_injects_transcript(tmp_path, monkeypatch):
    class ImmediateExecutor:
        def submit(self, fn, *args, **kwargs):
            return fn(*args, **kwargs)

    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFFtest")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr("src.utils.voice.record_audio", lambda seconds=5: str(audio_path))
    monkeypatch.setattr("src.utils.voice.transcribe_groq", lambda path: "hello from voice")

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._task_executor.shutdown(wait=False)
    tui._task_executor = ImmediateExecutor()

    tui._execute_command("/voice", "7")

    assert tui.buf == "hello from voice"
    assert tui.cur_pos == len("hello from voice")
    assert not audio_path.exists()
    messages = tui.store.snapshot()
    assert any(msg.role == "system" and "Listening for 7 seconds" in msg.text for msg in messages)
    assert any(msg.role == "system" and "Transcribed via Groq Whisper" in msg.text for msg in messages)


def test_voice_command_rejects_invalid_duration(tmp_path, monkeypatch):
    class ImmediateExecutor:
        def submit(self, fn, *args, **kwargs):
            return fn(*args, **kwargs)

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._task_executor.shutdown(wait=False)
    tui._task_executor = ImmediateExecutor()

    tui._execute_command("/voice", "abc")

    messages = tui.store.snapshot()
    assert any(msg.role == "error" and "Usage: /voice [seconds]" in msg.text for msg in messages)


def test_voice_command_reports_missing_transcription_backend(tmp_path, monkeypatch):
    class ImmediateExecutor:
        def submit(self, fn, *args, **kwargs):
            return fn(*args, **kwargs)

    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"RIFFtest")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr("src.utils.voice.record_audio", lambda seconds=5: str(audio_path))

    tui = _make_tui(tmp_path, monkeypatch)
    tui.redraw = lambda: None
    tui._task_executor.shutdown(wait=False)
    tui._task_executor = ImmediateExecutor()

    tui._execute_command("/voice", "")

    messages = tui.store.snapshot()
    assert any(msg.role == "error" and "Voice transcription needs GROQ_API_KEY or HF_TOKEN" in msg.text for msg in messages)
    assert not audio_path.exists()


def test_config_command_updates_runtime_effort(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.runtime_config.RUNTIME_CONFIG_DIR", tmp_path / "runtime")
    tui = _make_tui(tmp_path, monkeypatch)

    registry.commands["/config"]["func"](tui, "set effort high")

    assert tui.reasoning_effort == "high"
    registry.commands["/config"]["func"](tui, "show")
    assert any(msg.role == "system" and "Lumi config" in msg.text for msg in tui.store.snapshot())
    tui._task_executor.shutdown(wait=False)



def test_add_dir_and_files_commands_include_extra_context_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.runtime_config.RUNTIME_CONFIG_DIR", tmp_path / "runtime")
    extra = tmp_path / "shared"
    extra.mkdir()
    (extra / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    tui = _make_tui(tmp_path, monkeypatch)

    registry.commands["/add-dir"]["func"](tui, "shared")
    registry.commands["/files"]["func"](tui, "helper")

    assert tui.pane.active is True
    joined = "\n".join(tui.pane.content())
    assert str(extra.resolve()) in joined
    assert "helper.py" in joined
    tui._task_executor.shutdown(wait=False)



def test_tasks_and_agents_commands_open_claude_style_reports(tmp_path, monkeypatch):
    from src.agents import task_memory

    monkeypatch.setattr("src.utils.runtime_config.RUNTIME_CONFIG_DIR", tmp_path / "runtime")
    monkeypatch.setattr(task_memory, "TASK_MEMORY_PATH", tmp_path / "task_memory.json")
    monkeypatch.setattr(
        "src.utils.claude_parity._get_available_agents",
        lambda: [{"name": "Gemini Lead", "provider": "gemini", "role": "lead", "strengths": ["planning", "coding"]}],
    )
    task_memory.start_active_run("fix the failing tests", base_dir=tmp_path)
    tui = _make_tui(tmp_path, monkeypatch)
    tui.agent_active_objective = "build: fix the failing tests"
    tui.agent_tasks = [{"status": "running", "text": "profiling workspace"}]

    registry.commands["/tasks"]["func"](tui, "")
    assert tui.pane.title == "tasks"
    assert any("fix the failing tests" in line for line in tui.pane.content())

    registry.commands["/agents"]["func"](tui, "")
    assert tui.pane.title == "agents"
    assert any("Gemini Lead" in line for line in tui.pane.content())
    tui._task_executor.shutdown(wait=False)
