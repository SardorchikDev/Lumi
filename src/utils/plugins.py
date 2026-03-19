"""
Lumi Plugin System.

Users drop .py files into ~/Lumi/plugins/
Each plugin defines:
    COMMANDS = {"/mycommand": handler_fn}
    DESCRIPTION = {"description": "what it does"}

Optional metadata:
    PLUGIN_META = {
        "name": "My Plugin",
        "version": "0.1.0",
        "description": "extra detail",
        "permissions": ["read_workspace", "network"],
    }

Handler signature:
    def handler(args: str, client, model: str, memory, system_prompt: str, name: str) -> str | None

Example plugin (~/Lumi/plugins/greet.py):
    COMMANDS = {"/greet": greet}
    def greet(args, client, model, memory, system_prompt, name):
        print(f"  Hello, {args or 'friend'}!")
        return None
"""

import importlib.util
import pathlib
from collections.abc import Callable
from dataclasses import dataclass

PLUGIN_DIR = pathlib.Path.home() / "Lumi" / "plugins"
ALLOWED_PERMISSIONS = frozenset(
    {"read_workspace", "write_workspace", "network", "clipboard", "shell"}
)
PERMISSION_DESCRIPTIONS = {
    "read_workspace": "Read files inside the current workspace.",
    "write_workspace": "Write or modify files inside the current workspace.",
    "network": "Make network requests to external services.",
    "clipboard": "Read from or write to the system clipboard.",
    "shell": "Run shell commands on the local machine.",
}

# Registry: {"/command": (handler_fn, description)}
_registry: dict[str, tuple[Callable, str]] = {}
_plugin_meta: dict[str, "PluginMeta"] = {}


@dataclass(frozen=True)
class PluginMeta:
    name: str
    path: str
    version: str
    description: str
    permissions: tuple[str, ...]
    commands: tuple[str, ...]


def _normalize_permissions(raw_permissions) -> tuple[str, ...]:
    if raw_permissions is None:
        return ()
    if not isinstance(raw_permissions, (list, tuple, set)):
        raise ValueError("permissions must be a list of strings")
    permissions = []
    for item in raw_permissions:
        if not isinstance(item, str):
            raise ValueError("permissions must be a list of strings")
        normalized = item.strip()
        if not normalized:
            continue
        if normalized not in ALLOWED_PERMISSIONS:
            raise ValueError(
                f"unknown permission '{normalized}' (allowed: {', '.join(sorted(ALLOWED_PERMISSIONS))})"
            )
        permissions.append(normalized)
    return tuple(sorted(set(permissions)))


def _build_plugin_meta(path: pathlib.Path, module, commands: dict[str, Callable], descs: dict) -> PluginMeta:
    raw_meta = getattr(module, "PLUGIN_META", {})
    if raw_meta is None:
        raw_meta = {}
    if not isinstance(raw_meta, dict):
        raise ValueError("PLUGIN_META must be a dict when provided")

    permissions = _normalize_permissions(raw_meta.get("permissions"))
    name = str(raw_meta.get("name") or path.stem).strip() or path.stem
    version = str(raw_meta.get("version") or "0.1.0").strip() or "0.1.0"
    description = str(
        raw_meta.get("description")
        or descs.get("description")
        or f"Plugin: {path.stem}"
    ).strip()
    return PluginMeta(
        name=name,
        path=str(path),
        version=version,
        description=description,
        permissions=permissions,
        commands=tuple(sorted(commands)),
    )


def load_plugins() -> list[str]:
    """Load all plugins from ~/Lumi/plugins/. Returns list of loaded plugin names."""
    loaded = []
    if not PLUGIN_DIR.exists():
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        return []

    for path in sorted(PLUGIN_DIR.glob("*.py")):
        try:
            spec   = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            commands = getattr(module, "COMMANDS", {})
            descs    = getattr(module, "DESCRIPTION", {})
            if not isinstance(commands, dict):
                raise ValueError("COMMANDS must be a dict")
            if descs is None:
                descs = {}
            if not isinstance(descs, dict):
                raise ValueError("DESCRIPTION must be a dict when provided")

            normalized_commands: dict[str, Callable] = {}
            for cmd, fn in commands.items():
                if not callable(fn):
                    raise ValueError(f"Handler for {cmd!r} is not callable")
                normalized = cmd if str(cmd).startswith("/") else "/" + str(cmd)
                normalized_commands[normalized] = fn

            meta = _build_plugin_meta(path, module, normalized_commands, descs)

            for cmd, fn in normalized_commands.items():
                desc = descs.get(cmd, descs.get(cmd.lstrip("/"), meta.description))
                _registry[cmd] = (fn, desc)

            _plugin_meta[path.stem] = meta
            loaded.append(meta.name)
        except Exception as e:
            print(f"  [plugin] Failed to load {path.name}: {e}")

    return loaded


def get_commands() -> dict:
    """Return {cmd: description} for all loaded plugins."""
    return {cmd: desc for cmd, (_, desc) in _registry.items()}


def describe_plugins() -> list[dict[str, object]]:
    """Return structured metadata for loaded plugins."""
    items = []
    for key in sorted(_plugin_meta):
        meta = _plugin_meta[key]
        items.append(
            {
                "name": meta.name,
                "path": meta.path,
                "version": meta.version,
                "description": meta.description,
                "permissions": list(meta.permissions),
                "commands": list(meta.commands),
            }
        )
    return items


def describe_permissions() -> list[dict[str, str]]:
    """Return the supported plugin permission catalog."""
    return [
        {"name": name, "description": PERMISSION_DESCRIPTIONS.get(name, "")}
        for name in sorted(ALLOWED_PERMISSIONS)
    ]


def render_permission_report(scope: str = "summary") -> str:
    """Render plugin permission information for TUI/CLI commands."""
    normalized = (scope or "summary").strip().lower()
    if normalized in {"", "summary"}:
        normalized = "summary"
    elif normalized not in {"all", "plugins", "summary"}:
        normalized = "all"

    details = describe_plugins()
    lines = ["Plugin permissions"]

    if normalized in {"summary", "all"}:
        lines.append("  available")
        for item in describe_permissions():
            lines.append(f"    {item['name']}: {item['description']}")

    if normalized in {"plugins", "all"}:
        lines.append("")
        lines.append("  loaded plugins")
        if not details:
            lines.append("    none loaded")
        else:
            for item in details:
                perms = ", ".join(item["permissions"]) if item["permissions"] else "none declared"
                lines.append(f"    {item['name']}: {perms}")

    if normalized == "summary":
        declared = sorted(
            {
                permission
                for item in details
                for permission in item["permissions"]
            }
        )
        lines.append("")
        lines.append(
            "  active"
            + (" " + ", ".join(declared) if declared else " none declared by loaded plugins")
        )

    return "\n".join(lines)


def dispatch(cmd: str, args: str, **kwargs) -> tuple[bool, str | None]:
    """
    Try to dispatch a command to a plugin.
    Returns (handled: bool, result: str | None).
    """
    if cmd not in _registry:
        return False, None
    fn, _ = _registry[cmd]
    try:
        result = fn(args, **kwargs)
        return True, result
    except Exception as e:
        return True, f"Plugin error: {e}"


def reload_plugins() -> list[str]:
    """Reload all plugins (clear registry first)."""
    _registry.clear()
    _plugin_meta.clear()
    return load_plugins()
