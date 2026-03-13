"""Tests for src.utils.themes — color theme system."""

import json
import pathlib
from unittest.mock import patch

from src.utils.themes import (
    DEFAULT,
    THEMES,
    get_theme,
    list_themes,
    load_theme_name,
    save_theme_name,
)


class TestThemes:
    def test_default_theme_exists(self):
        assert DEFAULT in THEMES

    def test_all_themes_have_required_keys(self):
        required = {"name", "C1", "C2", "C3", "PU", "BL", "CY", "GR", "DG", "MU", "GN", "RE", "YE", "WH"}
        for name, theme in THEMES.items():
            missing = required - set(theme.keys())
            assert not missing, f"Theme '{name}' missing keys: {missing}"

    def test_list_themes(self):
        themes = list_themes()
        assert isinstance(themes, list)
        assert len(themes) == len(THEMES)
        assert "tokyo" in themes
        assert "dracula" in themes
        assert "nord" in themes

    def test_get_theme_default(self):
        theme = get_theme()
        assert isinstance(theme, dict)
        assert "name" in theme

    def test_get_theme_by_name(self):
        theme = get_theme("dracula")
        assert theme["name"] == "Dracula"

    def test_get_theme_invalid_falls_back(self):
        theme = get_theme("nonexistent")
        assert theme == THEMES[DEFAULT]

    def test_theme_values_are_ansi_codes(self):
        theme = get_theme("tokyo")
        for key in ("C1", "C2", "C3", "PU", "BL", "CY", "GR", "DG", "GN", "RE", "YE", "WH"):
            assert theme[key].startswith("\033["), f"Key {key} is not an ANSI code"


class TestThemePersistence:
    def setup_method(self):
        self._tmp = pathlib.Path("/tmp/lumi_test_theme.json")
        self._patcher = patch("src.utils.themes.THEME_FILE", self._tmp)
        self._patcher.start()
        if self._tmp.exists():
            self._tmp.unlink()

    def teardown_method(self):
        self._patcher.stop()
        if self._tmp.exists():
            self._tmp.unlink()

    def test_load_theme_name_default(self):
        name = load_theme_name()
        assert name == DEFAULT

    def test_save_and_load_theme_name(self):
        save_theme_name("dracula")
        assert load_theme_name() == "dracula"

    def test_save_creates_file(self):
        save_theme_name("nord")
        assert self._tmp.exists()
        data = json.loads(self._tmp.read_text())
        assert data["theme"] == "nord"
