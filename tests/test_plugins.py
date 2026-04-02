"""Tests for Lumi plugin validation, approval, and audit flows."""

from __future__ import annotations

from src.utils import plugins


def _reset_plugins() -> None:
    plugins._registry.clear()
    plugins._plugin_meta.clear()
    plugins._plugin_inventory.clear()


def _configure_plugin_env(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    trust_file = tmp_path / "plugin_trust.json"
    audit_log = tmp_path / "plugin_runtime_audit.log"
    monkeypatch.setattr(plugins, "PLUGIN_DIR", plugin_dir)
    monkeypatch.setattr(plugins, "PLUGIN_TRUST_FILE", trust_file)
    monkeypatch.setattr(plugins, "PLUGIN_AUDIT_LOG", audit_log)
    _reset_plugins()
    return plugin_dir


def test_load_plugins_requires_explicit_approval(tmp_path, monkeypatch):
    plugin_dir = _configure_plugin_env(tmp_path, monkeypatch)
    (plugin_dir / "greet.py").write_text(
        """
PLUGIN_META = {
    "name": "Greeter",
    "version": "1.2.0",
    "description": "Friendly greetings",
    "permissions": ["read_workspace"],
}
DESCRIPTION = {"/greet": "Say hi"}

def greet(args, **kwargs):
    return f"hi {args}".strip()

COMMANDS = {"/greet": greet}
        """.strip(),
        encoding="utf-8",
    )

    inventory = plugins.scan_plugins()
    assert inventory[0]["status"] == "untrusted"

    loaded_before = plugins.load_plugins()
    assert loaded_before == []

    ok, message = plugins.approve_plugin("Greeter")
    assert ok is True
    assert "Approved plugin" in message

    loaded_after = plugins.reload_plugins()
    described = plugins.describe_plugins()

    assert "Greeter" in loaded_after
    assert described[0]["name"] == "Greeter"
    assert described[0]["permissions"] == ["read_workspace"]
    assert described[0]["commands"] == ["/greet"]
    assert described[0]["loaded"] is True


def test_scan_plugins_handles_empty_directory_without_recursing(tmp_path, monkeypatch):
    _configure_plugin_env(tmp_path, monkeypatch)

    inventory = plugins.scan_plugins()
    described = plugins.describe_plugin_inventory()

    assert inventory == []
    assert described == []


def test_file_change_invalidates_plugin_trust(tmp_path, monkeypatch):
    plugin_dir = _configure_plugin_env(tmp_path, monkeypatch)
    plugin_path = plugin_dir / "greet.py"
    plugin_path.write_text(
        """
PLUGIN_META = {
    "name": "Greeter",
    "version": "1.0.0",
    "description": "Friendly greetings",
    "permissions": ["read_workspace"],
}
DESCRIPTION = {"/greet": "Say hi"}

def greet(args, **kwargs):
    return f"hi {args}".strip()

COMMANDS = {"/greet": greet}
        """.strip(),
        encoding="utf-8",
    )
    assert plugins.approve_plugin("Greeter")[0] is True
    assert plugins.reload_plugins() == ["Greeter"]

    plugin_path.write_text(
        """
PLUGIN_META = {
    "name": "Greeter",
    "version": "1.0.1",
    "description": "Friendly greetings",
    "permissions": ["read_workspace"],
}
DESCRIPTION = {"/greet": "Say hi"}

def greet(args, **kwargs):
    return f"hello {args}".strip()

COMMANDS = {"/greet": greet}
        """.strip(),
        encoding="utf-8",
    )

    inventory = plugins.scan_plugins()
    assert inventory[0]["trusted"] is False
    assert inventory[0]["status"] == "untrusted"
    assert plugins.reload_plugins() == []


def test_render_permission_report_includes_loaded_plugins_after_approval(tmp_path, monkeypatch):
    plugin_dir = _configure_plugin_env(tmp_path, monkeypatch)
    (plugin_dir / "greet.py").write_text(
        """
PLUGIN_META = {
    "name": "Greeter",
    "version": "1.0.0",
    "description": "Friendly greetings",
    "permissions": ["read_workspace", "network"],
}
DESCRIPTION = {"/greet": "Say hi"}

def greet(args, **kwargs):
    return f"hi {args}".strip()

COMMANDS = {"/greet": greet}
        """.strip(),
        encoding="utf-8",
    )
    assert plugins.approve_plugin("Greeter")[0] is True
    plugins.reload_plugins()

    report = plugins.render_permission_report("all")

    assert "Plugin permissions" in report
    assert "available" in report
    assert "read_workspace: Read files inside the current workspace." in report
    assert "network: Make network requests to external services." in report
    assert "loaded plugins" in report
    assert "Greeter: network, read_workspace" in report


def test_render_plugin_audit_report_flags_permission_mismatches(tmp_path, monkeypatch):
    plugin_dir = _configure_plugin_env(tmp_path, monkeypatch)
    (plugin_dir / "risky.py").write_text(
        """
PLUGIN_META = {
    "name": "Risky",
    "version": "0.1.0",
    "description": "Runs shell commands",
    "permissions": ["read_workspace"],
}
DESCRIPTION = {"/risky": "Risky"}

def risky(args, **kwargs):
    import subprocess
    subprocess.run(["echo", args or "hi"], check=False)
    return "ok"

COMMANDS = {"/risky": risky}
        """.strip(),
        encoding="utf-8",
    )

    report = plugins.render_plugin_audit_report()

    assert "Plugin audit" in report
    assert "Risky" in report
    assert "blocked" in report
    assert "uses shell APIs without declaring shell" in report


def test_render_plugin_inventory_report_shows_runtime_and_approval_hint(tmp_path, monkeypatch):
    plugin_dir = _configure_plugin_env(tmp_path, monkeypatch)
    (plugin_dir / "greet.py").write_text(
        """
PLUGIN_META = {
    "name": "Greeter",
    "version": "1.0.0",
    "description": "Friendly greetings",
    "permissions": ["read_workspace"],
}
DESCRIPTION = {"/greet": "Say hi"}

def greet(args, **kwargs):
    return f"hi {args}".strip()

COMMANDS = {"/greet": greet}
        """.strip(),
        encoding="utf-8",
    )

    report = plugins.render_plugin_inventory_report("inspect")

    assert "Plugin inventory" in report
    assert "runtime: subprocess sandbox" in report
    assert "/plugins approve greet" in report


def test_dispatch_blocks_dynamic_network_import_without_permission(tmp_path, monkeypatch):
    plugin_dir = _configure_plugin_env(tmp_path, monkeypatch)
    (plugin_dir / "nety.py").write_text(
        """
PLUGIN_META = {
    "name": "Nety",
    "version": "0.1.0",
    "description": "Attempts network import dynamically",
    "permissions": ["read_workspace"],
}
DESCRIPTION = {"/nety": "Network test"}

def nety(args, **kwargs):
    __import__("requests")
    return "ok"

COMMANDS = {"/nety": nety}
        """.strip(),
        encoding="utf-8",
    )

    assert plugins.approve_plugin("Nety")[0] is True
    plugins.reload_plugins()

    handled, message = plugins.dispatch("/nety", "", workspace=tmp_path)

    assert handled is True
    assert "network permission" in (message or "")


def test_manifest_is_required_for_approval(tmp_path, monkeypatch):
    plugin_dir = _configure_plugin_env(tmp_path, monkeypatch)
    (plugin_dir / "legacy.py").write_text(
        """
def legacy(args, **kwargs):
    return "hi"

COMMANDS = {"/legacy": legacy}
        """.strip(),
        encoding="utf-8",
    )

    inventory = plugins.scan_plugins()
    assert inventory[0]["status"] == "blocked"
    assert "PLUGIN_META must declare" in inventory[0]["issues"][0]

    ok, message = plugins.approve_plugin("legacy")
    assert ok is False
    assert "cannot be approved" in message


def test_dispatch_logs_runtime_audit_events(tmp_path, monkeypatch):
    plugin_dir = _configure_plugin_env(tmp_path, monkeypatch)
    (plugin_dir / "greet.py").write_text(
        """
PLUGIN_META = {
    "name": "Greeter",
    "version": "1.0.0",
    "description": "Friendly greetings",
    "permissions": ["read_workspace"],
}
DESCRIPTION = {"/greet": "Say hi"}

def greet(args, **kwargs):
    return f"hi {args}".strip()

COMMANDS = {"/greet": greet}
        """.strip(),
        encoding="utf-8",
    )
    assert plugins.approve_plugin("Greeter")[0] is True
    plugins.reload_plugins()

    handled, message = plugins.dispatch("/greet", "there", workspace=tmp_path)
    assert handled is True
    assert message == "hi there"

    report = plugins.render_plugin_audit_report()
    assert "recent runtime events" in report
    assert "Greeter /greet -> ok" in report
