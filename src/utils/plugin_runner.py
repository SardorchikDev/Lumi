"""Subprocess runtime for executing Lumi plugins with basic permission guards."""

from __future__ import annotations

import builtins
import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
from typing import Any
from urllib import request as urllib_request


def _resolve(path_value: str | os.PathLike[str]) -> pathlib.Path:
    return pathlib.Path(path_value).expanduser().resolve()


def _inside_workspace(path: pathlib.Path, workspace: pathlib.Path) -> bool:
    try:
        path.relative_to(workspace)
        return True
    except ValueError:
        return False


def _install_permission_guards(context: dict[str, Any]) -> None:
    workspace = _resolve(str(context.get("workspace") or pathlib.Path.cwd()))
    allow_read = bool(context.get("cwd"))
    allow_write = bool(context.get("write_workspace"))
    allow_shell = bool(context.get("shell"))
    allow_network = bool(context.get("network"))

    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        path = _resolve(file)
        wants_write = any(flag in mode for flag in ("w", "a", "x", "+"))
        if _inside_workspace(path, workspace):
            if wants_write and not allow_write:
                raise PermissionError("plugin does not have write_workspace permission")
            if not wants_write and not allow_read:
                raise PermissionError("plugin does not have read_workspace permission")
        return real_open(file, mode, *args, **kwargs)

    builtins.open = guarded_open

    real_run = subprocess.run
    real_popen = subprocess.Popen
    real_system = os.system
    real_urlopen = urllib_request.urlopen
    real_socket = socket.socket

    def guarded_run(*args, **kwargs):
        if not allow_shell:
            raise PermissionError("plugin does not have shell permission")
        return real_run(*args, **kwargs)

    def guarded_popen(*args, **kwargs):
        if not allow_shell:
            raise PermissionError("plugin does not have shell permission")
        return real_popen(*args, **kwargs)

    def guarded_system(*args, **kwargs):
        if not allow_shell:
            raise PermissionError("plugin does not have shell permission")
        return real_system(*args, **kwargs)

    def guarded_urlopen(*args, **kwargs):
        if not allow_network:
            raise PermissionError("plugin does not have network permission")
        return real_urlopen(*args, **kwargs)

    class GuardedSocket(socket.socket):
        def __new__(cls, *args, **kwargs):
            if not allow_network:
                raise PermissionError("plugin does not have network permission")
            return real_socket(*args, **kwargs)

    subprocess.run = guarded_run
    subprocess.Popen = guarded_popen
    os.system = guarded_system
    urllib_request.urlopen = guarded_urlopen
    socket.socket = GuardedSocket

    real_unlink = pathlib.Path.unlink
    real_mkdir = pathlib.Path.mkdir
    real_rename = pathlib.Path.rename
    real_replace = pathlib.Path.replace

    def guarded_unlink(self, *args, **kwargs):
        path = _resolve(self)
        if _inside_workspace(path, workspace) and not allow_write:
            raise PermissionError("plugin does not have write_workspace permission")
        return real_unlink(self, *args, **kwargs)

    def guarded_mkdir(self, *args, **kwargs):
        path = _resolve(self)
        if _inside_workspace(path, workspace) and not allow_write:
            raise PermissionError("plugin does not have write_workspace permission")
        return real_mkdir(self, *args, **kwargs)

    def guarded_rename(self, target, *args, **kwargs):
        path = _resolve(self)
        if _inside_workspace(path, workspace) and not allow_write:
            raise PermissionError("plugin does not have write_workspace permission")
        return real_rename(self, target, *args, **kwargs)

    def guarded_replace(self, target, *args, **kwargs):
        path = _resolve(self)
        if _inside_workspace(path, workspace) and not allow_write:
            raise PermissionError("plugin does not have write_workspace permission")
        return real_replace(self, target, *args, **kwargs)

    pathlib.Path.unlink = guarded_unlink
    pathlib.Path.mkdir = guarded_mkdir
    pathlib.Path.rename = guarded_rename
    pathlib.Path.replace = guarded_replace


def _load_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(f"lumi_plugin_runner_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create import spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(path: pathlib.Path, command: str, payload: dict[str, Any]) -> str | None:
    context = payload.get("context", {})
    args = str(payload.get("args", ""))
    if not isinstance(context, dict):
        raise RuntimeError("invalid plugin context payload")
    _install_permission_guards(context)
    module = _load_module(path)
    commands = getattr(module, "COMMANDS", {})
    if not isinstance(commands, dict):
        raise RuntimeError("COMMANDS must be a dict")
    handler = commands.get(command) or commands.get(command.lstrip("/"))
    if not callable(handler):
        raise RuntimeError(f"command not found: {command}")
    result = handler(args, **context)
    return None if result is None else str(result)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if len(argv) != 2:
        sys.stderr.write("usage: plugin_runner.py <plugin.py> <command>\n")
        return 2
    path = _resolve(argv[0])
    command = argv[1]
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = _run(path, command, payload)
        sys.stdout.write(json.dumps({"ok": True, "result": result}))
        return 0
    except Exception as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
