"""Tests for TUI input helpers."""

from pathlib import Path

from src.tui.input import InputHistory, parse_escape_sequence, read_key


def test_parse_escape_sequence_handles_modifier_arrows():
    assert parse_escape_sequence(b"\x1b[1;2A") == "SHIFT_UP"
    assert parse_escape_sequence(b"\x1b[1;5B") == "CTRL_DOWN"
    assert parse_escape_sequence(b"\x1b[C") == "RIGHT"


def test_parse_escape_sequence_handles_mouse_wheel():
    assert parse_escape_sequence(b"\x1b[<64;40;12M") == "WHEEL_UP"
    assert parse_escape_sequence(b"\x1b[<65;40;12M") == "WHEEL_DOWN"


def test_read_key_handles_bracketed_paste(monkeypatch):
    reads = iter(
        [
            b"\x1b",
            b"[200~print('hi')\r\nprint('bye')\x1b[201~",
        ]
    )

    monkeypatch.setattr("src.tui.input.os.read", lambda _fd, _size: next(reads))
    monkeypatch.setattr("src.tui.input.select.select", lambda *_args, **_kwargs: ([0], [], []))

    assert read_key(0) == ("PASTE", "print('hi')\nprint('bye')")


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
