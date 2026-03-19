"""Tests for src.cli.render."""

from unittest.mock import patch

from src.cli import render


class TestRender:
    @patch("src.cli.render.clear_screen")
    @patch("src.cli.render.os.getcwd", return_value="/tmp/demo")
    def test_draw_header_includes_model_provider_and_workspace(self, _cwd, _clear, capsys):
        with patch("src.cli.render.terminal_width", return_value=100):
            render.draw_header("gpt-4o", turns=3, provider="github")
        out = capsys.readouterr().out
        assert "lumi" in out
        assert "terminal coding assistant" in out
        assert "gpt-4o" in out
        assert "github" in out
        assert "/tmp/demo" in out

    def test_print_you_and_welcome_render_core_labels(self, capsys):
        with patch("src.cli.render.terminal_width", return_value=100):
            render.print_you("hello from user")
            render.print_welcome("Lumi")
        out = capsys.readouterr().out
        assert "you" in out
        assert "hello from user" in out
        assert "ready" in out
        assert "Lumi" in out
