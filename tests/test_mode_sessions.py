"""Tests for external CLI handoff transcript helpers."""

from __future__ import annotations

import json

from src.tui import mode_sessions


def test_sanitize_handoff_transcript_strips_ansi_and_script_headers():
    raw = (
        "Script started on 2026-03-21 00:00:00+00:00 [COMMAND=\"gemini\"]\n"
        "\x1b[31mhello\x1b[0m\r\n"
        "\r\n"
        "world\r\n"
        "Script done on 2026-03-21 00:01:00+00:00 [COMMAND_EXIT_CODE=\"0\"]\n"
    )

    cleaned = mode_sessions.sanitize_handoff_transcript(raw)

    assert cleaned == "hello\n\nworld"


def test_save_mode_conversation_uses_cli_subdirectory(tmp_path, monkeypatch):
    monkeypatch.setattr(mode_sessions, "CONVERSATIONS_DIR", tmp_path)

    path = mode_sessions.save_mode_conversation(
        cli_name="gemini",
        display_name="Gemini CLI",
        transcript="user: hi\nassistant: hello",
        summary={"tldr": "Discussed a fix.", "files": ["app.py"], "commands": ["pytest"], "decisions": [], "next_steps": []},
        exit_code=0,
        cwd="/home/sadi/Lumi",
        started_at="2026-03-21T10:00:00",
        ended_at="2026-03-21T10:01:30",
        duration_seconds=90.0,
        git_branch="main",
        binary="gemini",
        binary_path="/usr/bin/gemini",
        binary_version="gemini 1.2.3",
        captured=True,
    )

    assert path.parent == tmp_path / "gemini"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["cli"] == "gemini"
    assert data["name"] == "Gemini CLI"
    assert data["summary"]["tldr"] == "Discussed a fix."
    assert data["binary_version"] == "gemini 1.2.3"
    assert data["transcript"] == "user: hi\nassistant: hello"


def test_parse_and_format_mode_summary_response_returns_structured_tldr():
    raw = """
    ```json
    {
      "tldr": "Fixed the failing test and confirmed the workflow.",
      "files": ["tests/test_app.py"],
      "commands": ["pytest -q"],
      "decisions": ["Keep the existing CLI wrapper."],
      "next_steps": ["Run the full suite in Lumi."]
    }
    ```
    """

    summary = mode_sessions.parse_mode_summary_response(raw, "Codex CLI", "edited tests/test_app.py\npytest -q")
    rendered = mode_sessions.format_mode_tldr(summary, "Codex CLI")

    assert summary["files"] == ["tests/test_app.py"]
    assert summary["commands"] == ["pytest -q"]
    assert rendered.startswith("TL;DR from your Codex CLI session:")
    assert "- Run the full suite in Lumi." in rendered


def test_search_mode_conversations_finds_saved_record(tmp_path, monkeypatch):
    monkeypatch.setattr(mode_sessions, "CONVERSATIONS_DIR", tmp_path)
    path = mode_sessions.save_mode_conversation(
        cli_name="codex",
        display_name="Codex CLI",
        transcript="edited src/tui/app.py\nran pytest tests/test_tui_integration.py",
        summary={
            "tldr": "Adjusted the TUI layout and reran tests.",
            "files": ["src/tui/app.py"],
            "commands": ["pytest tests/test_tui_integration.py"],
            "decisions": ["Keep the bordered prompt."],
            "next_steps": ["Polish the empty state."],
        },
        exit_code=0,
        cwd="/home/sadi/Lumi",
        started_at="2026-03-21T10:00:00",
        ended_at="2026-03-21T10:03:00",
        duration_seconds=180.0,
        git_branch="main",
        binary="codex",
        binary_path="/usr/bin/codex",
        binary_version="codex 0.1.0",
        captured=True,
    )

    results = mode_sessions.search_mode_conversations("bordered prompt", "codex")

    assert len(results) == 1
    assert results[0]["path"] == str(path)
    context = mode_sessions.build_mode_context_text(results[0])
    assert "Keep the bordered prompt." in context
