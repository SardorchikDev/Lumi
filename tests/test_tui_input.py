"""Tests for TUI input helpers."""

from pathlib import Path

from src.tui.input import InputHistory, parse_escape_sequence


def test_parse_escape_sequence_handles_modifier_arrows():
    assert parse_escape_sequence(b"\x1b[1;2A") == "SHIFT_UP"
    assert parse_escape_sequence(b"\x1b[1;5B") == "CTRL_DOWN"
    assert parse_escape_sequence(b"\x1b[C") == "RIGHT"


def test_input_history_restores_draft_when_navigating_back(tmp_path):
    history = InputHistory(tmp_path / "history")
    history.append("first")
    history.append("second")

    assert history.navigate("draft", -1) == "second"
    assert history.navigate("second", -1) == "first"
    assert history.navigate("first", 1) == "second"
    assert history.navigate("second", 1) == "draft"


def test_input_history_skips_duplicate_adjacent_entries(tmp_path):
    history = InputHistory(tmp_path / "history")
    history.append("same")
    history.append("same")
    history.append("other")

    assert history.entries == ["same", "other"]
    assert Path(tmp_path / "history").read_text(encoding="utf-8").splitlines() == ["same", "other"]
