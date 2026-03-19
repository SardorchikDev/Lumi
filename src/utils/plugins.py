"""
Lumi plugin system with manifest validation and explicit trust.

Plugins live in ``~/Lumi/plugins`` and must declare:
    PLUGIN_META = {
        "name": "My Plugin",
        "version": "0.1.0",
        "description": "What this plugin does",
        "permissions": ["read_workspace"],
    }

    COMMANDS = {"/hello": hello}
    DESCRIPTION = {"/hello": "Say hello"}

Plugins are scanned with ``ast`` first so untrusted files are never imported
just by being present on disk. A plugin must be explicitly approved, and any
file change invalidates that approval until the new fingerprint is approved.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import pathlib
from collections.abc import Callable
from dataclasses import dataclass

PLUGIN_DIR = pathlib.Path.home() / "Lumi" / "plugins"
PLUGIN_TRUST_FILE = pathlib.Path.home() / ".lumi" / "plugin_trust.json"
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

_registry: dict[str, tuple[Callable, str]] = {}
_plugin_meta: dict[str, PluginMeta] = {}
_plugin_inventory: dict[str, PluginMeta] = {}


@dataclass(frozen=True)
class PluginMeta:
    name: str
    path: str
    version: str
    description: str
    permissions: tuple[str, ...]
    commands: tuple[str, ...]
    fingerprint: str
    trusted: bool
    loaded: bool
    status: str
    warnings: tuple[str, ...]
    issues: tuple[str, ...]


def _normalize_permissions(raw_permissions) -> tuple[str, ...]:
    if raw_permissions is None:
        raise ValueError("PLUGIN_META.permissions is required")
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


def _read_trust_store() -> dict[str, dict[str, str]]:
    if not PLUGIN_TRUST_FILE.exists():
        return {}
    try:
        data = json.loads(PLUGIN_TRUST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    plugins = data.get("plugins", {})
    return plugins if isinstance(plugins, dict) else {}


def _write_trust_store(plugins: dict[str, dict[str, str]]) -> None:
    PLUGIN_TRUST_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"plugins": plugins}
    tmp = PLUGIN_TRUST_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(PLUGIN_TRUST_FILE)


def _fingerprint_text(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _assignment_name(node: ast.stmt) -> str | None:
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _assignment_value(node: ast.stmt):
    if isinstance(node, ast.Assign):
        return node.value
    if isinstance(node, ast.AnnAssign):
        return node.value
    return None


def _extract_command_keys(value) -> tuple[str, ...]:
    if not isinstance(value, ast.Dict):
        raise ValueError("COMMANDS must be a dict literal")
    commands: list[str] = []
    for key in value.keys:
        if key is None:
            continue
        parsed = ast.literal_eval(key)
        if not isinstance(parsed, str):
            raise ValueError("COMMANDS keys must be strings")
        normalized = parsed if parsed.startswith("/") else "/" + parsed
        commands.append(normalized)
    return tuple(sorted(set(commands)))


def _extract_manifest(path: pathlib.Path) -> tuple[dict, dict, tuple[str, ...], str]:
    source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(path))
    raw_meta = None
    raw_desc = {}
    command_keys: tuple[str, ...] = ()
    for node in tree.body:
        name = _assignment_name(node)
        if not name:
            continue
        value = _assignment_value(node)
        if name == "PLUGIN_META" and value is not None:
            raw_meta = ast.literal_eval(value)
        elif name == "DESCRIPTION" and value is not None:
            raw_desc = ast.literal_eval(value)
        elif name == "COMMANDS" and value is not None:
            command_keys = _extract_command_keys(value)
    if raw_meta is None:
        raw_meta = {}
    if raw_desc is None:
        raw_desc = {}
    if not isinstance(raw_meta, dict):
        raise ValueError("PLUGIN_META must be a dict literal")
    if not isinstance(raw_desc, dict):
        raise ValueError("DESCRIPTION must be a dict literal when provided")
    return raw_meta, raw_desc, command_keys, source


PLUGIN_RISK_RULES = {
    "shell": ("subprocess", "os.system", "pty", "Popen(", "run("),
    "network": ("requests.", "urllib.", "httpx.", "socket.", "urlopen("),
    "clipboard": ("pyperclip", "clipboard_", "xclip", "pbcopy", "pbpaste"),
    "write_workspace": (".write_text(", ".write_bytes(", ".unlink(", ".mkdir(", ".rename(", "open("),
}


def _source_warnings(source: str, declared_permissions: set[str]) -> tuple[str, ...]:
    warnings: list[str] = []
    lowered = source.lower()
    for permission, needles in PLUGIN_RISK_RULES.items():
        if any(needle.lower() in lowered for needle in needles) and permission not in declared_permissions:
            warnings.append(f"uses {permission} APIs without declaring {permission}")
    return tuple(warnings)


def _build_plugin_meta(
    path: pathlib.Path,
    *,
    raw_meta: dict,
    raw_desc: dict,
    command_keys: tuple[str, ...],
    source: str,
    trust_store: dict[str, dict[str, str]],
) -> PluginMeta:
    issues: list[str] = []
    missing = [
        key
        for key in ("name", "version", "description", "permissions")
        if key not in raw_meta
    ]
    if missing:
        issues.append("PLUGIN_META must declare " + ", ".join(missing))
    if not command_keys:
        issues.append("COMMANDS must declare at least one command")

    try:
        permissions = _normalize_permissions(raw_meta.get("permissions"))
    except ValueError as exc:
        permissions = ()
        issues.append(str(exc))

    name = str(raw_meta.get("name") or path.stem).strip() or path.stem
    version = str(raw_meta.get("version") or "0.1.0").strip() or "0.1.0"
    description = str(
        raw_meta.get("description")
        or raw_desc.get("description")
        or f"Plugin: {path.stem}"
    ).strip()
    fingerprint = _fingerprint_text(source)
    trusted = trust_store.get(str(path), {}).get("fingerprint") == fingerprint
    warnings = _source_warnings(source, set(permissions))
    blocked = bool(issues or warnings)
    status = "loaded" if trusted and not blocked else "blocked" if blocked else "untrusted"
    return PluginMeta(
        name=name,
        path=str(path),
        version=version,
        description=description,
        permissions=permissions,
        commands=command_keys,
        fingerprint=fingerprint,
        trusted=trusted,
        loaded=False,
        status=status,
        warnings=warnings,
        issues=tuple(issues),
    )


def _meta_to_dict(meta: PluginMeta) -> dict[str, object]:
    return {
        "name": meta.name,
        "path": meta.path,
        "version": meta.version,
        "description": meta.description,
        "permissions": list(meta.permissions),
        "commands": list(meta.commands),
        "fingerprint": meta.fingerprint,
        "trusted": meta.trusted,
        "loaded": meta.loaded,
        "status": meta.status,
        "warnings": list(meta.warnings),
        "issues": list(meta.issues),
    }


def scan_plugins() -> list[dict[str, object]]:
    _plugin_inventory.clear()
    if not PLUGIN_DIR.exists():
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        return []

    trust_store = _read_trust_store()
    for path in sorted(PLUGIN_DIR.glob("*.py")):
        try:
            raw_meta, raw_desc, command_keys, source = _extract_manifest(path)
            meta = _build_plugin_meta(
                path,
                raw_meta=raw_meta,
                raw_desc=raw_desc,
                command_keys=command_keys,
                source=source,
                trust_store=trust_store,
            )
        except Exception as exc:
            meta = PluginMeta(
                name=path.stem,
                path=str(path),
                version="0.0.0",
                description=f"Plugin: {path.stem}",
                permissions=(),
                commands=(),
                fingerprint="",
                trusted=False,
                loaded=False,
                status="blocked",
                warnings=(),
                issues=(f"manifest parse failed: {exc}",),
            )
        _plugin_inventory[path.stem] = meta
    return [_meta_to_dict(_plugin_inventory[key]) for key in sorted(_plugin_inventory)]


def _plugin_lookup(identifier: str) -> PluginMeta | None:
    ident = identifier.strip()
    if not ident:
        return None
    if not _plugin_inventory:
        scan_plugins()
    lowered = ident.lower()
    for meta in _plugin_inventory.values():
        candidates = {
            meta.name.lower(),
            pathlib.Path(meta.path).stem.lower(),
            pathlib.Path(meta.path).name.lower(),
            meta.path.lower(),
        }
        if lowered in candidates:
            return meta
    return None


def approve_plugin(identifier: str) -> tuple[bool, str]:
    meta = _plugin_lookup(identifier)
    if meta is None:
        return False, f"Plugin not found: {identifier}"
    if meta.issues or meta.warnings:
        details = list(meta.issues) + list(meta.warnings)
        return False, "Plugin cannot be approved: " + "; ".join(details)
    trust_store = _read_trust_store()
    trust_store[meta.path] = {"fingerprint": meta.fingerprint, "name": meta.name}
    _write_trust_store(trust_store)
    scan_plugins()
    return True, f"Approved plugin: {meta.name}"


def revoke_plugin(identifier: str) -> tuple[bool, str]:
    meta = _plugin_lookup(identifier)
    if meta is None:
        return False, f"Plugin not found: {identifier}"
    trust_store = _read_trust_store()
    if meta.path not in trust_store:
        return False, f"Plugin is not approved: {meta.name}"
    trust_store.pop(meta.path, None)
    _write_trust_store(trust_store)
    scan_plugins()
    return True, f"Revoked plugin approval: {meta.name}"


def _import_plugin_module(path: pathlib.Path, fingerprint: str):
    module_name = f"lumi_plugin_{path.stem}_{fingerprint[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError("could not create import spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_plugins() -> list[str]:
    """Load all trusted plugins from ``~/Lumi/plugins``."""
    loaded: list[str] = []
    _registry.clear()
    _plugin_meta.clear()
    scan_plugins()

    for key in sorted(_plugin_inventory):
        meta = _plugin_inventory[key]
        if not meta.trusted or meta.issues or meta.warnings:
            continue
        path = pathlib.Path(meta.path)
        try:
            module = _import_plugin_module(path, meta.fingerprint)
            commands = getattr(module, "COMMANDS", {})
            descs = getattr(module, "DESCRIPTION", {})
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

            loaded_meta = PluginMeta(
                **{
                    **meta.__dict__,
                    "commands": tuple(sorted(normalized_commands)),
                    "loaded": True,
                    "status": "loaded",
                }
            )
            for cmd, fn in normalized_commands.items():
                desc = descs.get(cmd, descs.get(cmd.lstrip("/"), loaded_meta.description))
                _registry[cmd] = (fn, desc)
            _plugin_meta[key] = loaded_meta
            _plugin_inventory[key] = loaded_meta
            loaded.append(loaded_meta.name)
        except Exception as exc:
            blocked_meta = PluginMeta(
                **{
                    **meta.__dict__,
                    "loaded": False,
                    "status": "blocked",
                    "issues": meta.issues + (f"import failed: {exc}",),
                }
            )
            _plugin_inventory[key] = blocked_meta
    return loaded


def reload_plugins() -> list[str]:
    _registry.clear()
    _plugin_meta.clear()
    return load_plugins()


def get_commands() -> dict[str, str]:
    return {cmd: desc for cmd, (_, desc) in _registry.items()}


def describe_plugins() -> list[dict[str, object]]:
    return [_meta_to_dict(_plugin_meta[key]) for key in sorted(_plugin_meta)]


def describe_plugin_inventory() -> list[dict[str, object]]:
    if not _plugin_inventory:
        scan_plugins()
    return [_meta_to_dict(_plugin_inventory[key]) for key in sorted(_plugin_inventory)]


def describe_permissions() -> list[dict[str, str]]:
    return [
        {"name": name, "description": PERMISSION_DESCRIPTIONS.get(name, "")}
        for name in sorted(ALLOWED_PERMISSIONS)
    ]


def audit_plugins() -> list[dict[str, object]]:
    return [
        {
            "name": item["name"],
            "path": item["path"],
            "permissions": item["permissions"],
            "commands": item["commands"],
            "trusted": item["trusted"],
            "loaded": item["loaded"],
            "status": item["status"],
            "warnings": item["warnings"],
            "issues": item["issues"],
        }
        for item in describe_plugin_inventory()
    ]


def render_plugin_audit_report() -> str:
    lines = ["Plugin audit"]
    items = audit_plugins()
    if not items:
        lines.append("  no plugins discovered")
        return "\n".join(lines)
    for item in items:
        trust = "trusted" if item["trusted"] else "approval required"
        lines.append(f"  {item['name']}  [{item['status']}; {trust}]")
        if item["issues"]:
            for issue in item["issues"]:
                lines.append(f"    issue: {issue}")
        if item["warnings"]:
            for warning in item["warnings"]:
                lines.append(f"    warning: {warning}")
        if not item["issues"] and not item["warnings"]:
            lines.append("    audit: manifest and declared permissions look consistent")
    return "\n".join(lines)


def render_permission_report(scope: str = "summary") -> str:
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
    if cmd not in _registry:
        return False, None
    fn, _ = _registry[cmd]
    try:
        result = fn(args, **kwargs)
        return True, result
    except Exception as exc:
        return True, f"Plugin error: {exc}"
