"""Lightweight VS Code integration helpers for Lumi."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VSCodeTarget:
    path: Path
    line: int | None = None
    column: int | None = None


def detect_vscode_cli() -> str | None:
    for candidate in ("code", "code-insiders"):
        resolved = shutil.which(candidate)
        if resolved:
            return candidate
    return None


def parse_vscode_target(raw: str, *, base_dir: Path | None = None) -> VSCodeTarget:
    text = (raw or "").strip()
    root = (base_dir or Path.cwd()).resolve()
    if not text:
        return VSCodeTarget(root)

    parts = text.split(":")
    path_text = text
    line: int | None = None
    column: int | None = None
    if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
        path_text = ":".join(parts[:-2])
        line = int(parts[-2])
        column = int(parts[-1])
    elif len(parts) >= 2 and parts[-1].isdigit():
        path_text = ":".join(parts[:-1])
        line = int(parts[-1])

    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = (root / path).resolve()
    return VSCodeTarget(path=path, line=line, column=column)


def render_vscode_status(*, base_dir: Path | None = None) -> str:
    command = detect_vscode_cli()
    root = (base_dir or Path.cwd()).resolve()
    if command is None:
        return "\n".join(
            [
                "VS Code support",
                "  Status: code CLI not found",
                "  Install VS Code and enable the shell command from its command palette.",
                f"  Workspace: {root}",
            ]
        )
    return "\n".join(
        [
            "VS Code support",
            f"  Status: ready via `{command}`",
            f"  Workspace: {root}",
            "  Usage: /ide [path[:line[:column]]]",
        ]
    )


def open_in_vscode(
    raw_target: str = "",
    *,
    base_dir: Path | None = None,
    reuse_window: bool = True,
) -> tuple[bool, str]:
    command = detect_vscode_cli()
    if command is None:
        return False, "VS Code shell command not found. Install VS Code and enable `code` from its command palette."

    target = parse_vscode_target(raw_target, base_dir=base_dir)
    if not target.path.exists():
        return False, f"Path not found: {target.path}"

    argv = [command]
    if reuse_window:
        argv.append("--reuse-window")
    if target.line is not None:
        goto = str(target.path)
        if target.column is not None:
            goto = f"{goto}:{target.line}:{target.column}"
        else:
            goto = f"{goto}:{target.line}"
        argv.extend(["--goto", goto])
    else:
        argv.append(str(target.path))

    try:
        subprocess.Popen(argv)
    except OSError as exc:
        return False, f"Failed to launch VS Code: {exc}"

    label = target.path.name if target.path != (base_dir or Path.cwd()).resolve() else str(target.path)
    return True, f"Opened in VS Code: {label}"
