"""Tests for lightweight VS Code integration."""

from __future__ import annotations

from pathlib import Path

from src.utils import ide


def test_parse_vscode_target_supports_line_and_column(tmp_path):
    target = ide.parse_vscode_target("src/app.py:12:4", base_dir=tmp_path)

    assert target.path == (tmp_path / "src" / "app.py").resolve()
    assert target.line == 12
    assert target.column == 4


def test_render_vscode_status_mentions_missing_cli(tmp_path, monkeypatch):
    monkeypatch.setattr("src.utils.ide.detect_vscode_cli", lambda: None)

    status = ide.render_vscode_status(base_dir=tmp_path)

    assert "code CLI not found" in status
    assert str(tmp_path.resolve()) in status


def test_open_in_vscode_uses_code_cli(tmp_path, monkeypatch):
    target = tmp_path / "app.py"
    target.write_text("print('hi')\n", encoding="utf-8")
    captured: dict[str, object] = {}

    monkeypatch.setattr("src.utils.ide.detect_vscode_cli", lambda: "code")

    def fake_popen(argv):
        captured["argv"] = argv
        return object()

    monkeypatch.setattr("src.utils.ide.subprocess.Popen", fake_popen)

    ok, message = ide.open_in_vscode("app.py:7:2", base_dir=tmp_path)

    assert ok is True
    assert "Opened in VS Code" in message
    assert captured["argv"] == [
        "code",
        "--reuse-window",
        "--goto",
        f"{target.resolve()}:7:2",
    ]
