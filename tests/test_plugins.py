"""Tests for Lumi plugin metadata and validation."""

from __future__ import annotations

from src.utils import plugins


def _reset_plugins() -> None:
    plugins._registry.clear()
    plugins._plugin_meta.clear()


def test_load_plugins_tracks_metadata(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "greet.py").write_text(
        """
PLUGIN_META = {
    "name": "Greeter",
    "version": "1.2.0",
    "description": "Friendly greetings",
    "permissions": ["read_workspace"],
}

def greet(args, **kwargs):
    return f"hi {args}".strip()

COMMANDS = {"/greet": greet}
DESCRIPTION = {"/greet": "Say hi"}
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(plugins, "PLUGIN_DIR", plugin_dir)
    _reset_plugins()

    loaded = plugins.load_plugins()
    described = plugins.describe_plugins()

    assert "Greeter" in loaded
    assert described[0]["name"] == "Greeter"
    assert described[0]["permissions"] == ["read_workspace"]
    assert described[0]["commands"] == ["/greet"]


def test_load_plugins_rejects_unknown_permissions(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "bad.py").write_text(
        """
PLUGIN_META = {"permissions": ["admin"]}
def bad(args, **kwargs):
    return "nope"
COMMANDS = {"/bad": bad}
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(plugins, "PLUGIN_DIR", plugin_dir)
    _reset_plugins()

    loaded = plugins.load_plugins()

    assert loaded == []
    assert plugins.describe_plugins() == []


def test_render_permission_report_includes_catalog_and_loaded_plugins(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "greet.py").write_text(
        """
PLUGIN_META = {
    "name": "Greeter",
    "permissions": ["read_workspace", "network"],
}

def greet(args, **kwargs):
    return f"hi {args}".strip()

COMMANDS = {"/greet": greet}
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(plugins, "PLUGIN_DIR", plugin_dir)
    _reset_plugins()
    plugins.load_plugins()

    report = plugins.render_permission_report("all")

    assert "Plugin permissions" in report
    assert "available" in report
    assert "read_workspace: Read files inside the current workspace." in report
    assert "network: Make network requests to external services." in report
    assert "loaded plugins" in report
    assert "Greeter: network, read_workspace" in report
