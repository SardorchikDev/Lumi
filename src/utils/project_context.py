"""Helpers for loading Lumi/Claude project context files."""

from __future__ import annotations

from pathlib import Path

PROJECT_CONTEXT_CANDIDATES: tuple[str, ...] = (
    "LUMI.md",
    "lumi.md",
    "CLAUDE.md",
    "claude.md",
)


def find_project_context_file(base_dir: Path | None = None) -> Path | None:
    root = (base_dir or Path.cwd()).resolve()
    for name in PROJECT_CONTEXT_CANDIDATES:
        candidate = root / name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def load_project_context(base_dir: Path | None = None) -> tuple[Path | None, str]:
    path = find_project_context_file(base_dir)
    if path is None:
        return None, ""
    try:
        return path, path.read_text(encoding="utf-8").strip()
    except OSError:
        return path, ""


def preferred_project_context_name(base_dir: Path | None = None) -> str:
    path = find_project_context_file(base_dir)
    return path.name if path is not None else "LUMI.md"
