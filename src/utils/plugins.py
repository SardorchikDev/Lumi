"""
Lumi Plugin System.

Users drop .py files into ~/Lumi/plugins/
Each plugin defines:
    COMMANDS = {"/mycommand": handler_fn}
    DESCRIPTION = {"description": "what it does"}

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

PLUGIN_DIR = pathlib.Path.home() / "Lumi" / "plugins"

# Registry: {"/command": (handler_fn, description)}
_registry: dict[str, tuple[Callable, str]] = {}


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

            for cmd, fn in commands.items():
                if not cmd.startswith("/"):
                    cmd = "/" + cmd
                desc = descs.get(cmd, descs.get(cmd.lstrip("/"), f"Plugin: {path.stem}"))
                _registry[cmd] = (fn, desc)

            loaded.append(path.stem)
        except Exception as e:
            print(f"  [plugin] Failed to load {path.name}: {e}")

    return loaded


def get_commands() -> dict:
    """Return {cmd: description} for all loaded plugins."""
    return {cmd: desc for cmd, (_, desc) in _registry.items()}


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
    return load_plugins()
