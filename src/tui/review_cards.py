"""Helpers for building starter-panel review cards in the TUI."""

from __future__ import annotations

from pathlib import Path

from src.utils.repo_profile import inspect_workspace


def file_review_card(path: Path, *, mode: str) -> dict[str, object]:
    resolved = path.expanduser().resolve()
    workspace = inspect_workspace(Path.cwd())
    summary = [
        f"target: {resolved.name}",
        f"mode: {mode}",
    ]
    if workspace.verification_commands:
        checks = ", ".join(sorted(workspace.verification_commands))
        summary.append(f"checks: {checks}")
    else:
        summary.append("checks: none detected")
    if workspace.frameworks:
        summary.append(f"stack: {', '.join(workspace.frameworks[:3])}")

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        preview = ["preview unavailable"]
    else:
        preview = []
        for line in content.splitlines()[:4]:
            preview.append(line if line.strip() else "(blank)")
        if len(content.splitlines()) > 4:
            preview.append("…")

    footer = "running review" if mode == "review" else "preparing edit"
    title = "code review" if mode == "review" else "edit preview"
    return {
        "title": title,
        "summary_lines": summary,
        "preview_lines": preview,
        "footer": footer,
    }
