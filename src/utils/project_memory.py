"""Project-scoped memory for Lumi workspaces."""

from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.chat.optimizer import estimate_tokens
from src.utils.repo_profile import inspect_workspace

PROJECT_MEMORY_ROOT = Path.home() / ".codex" / "memories" / "lumi" / "projects"
MAX_MEMORY_TOKENS = 500


@dataclass(frozen=True)
class ProjectRun:
    command: str
    summary: str
    timestamp: str


@dataclass(frozen=True)
class ProjectDecision:
    fact: str
    timestamp: str


@dataclass(frozen=True)
class ProjectMemory:
    repo: str
    stack: tuple[str, ...] = ()
    test_command: str = ""
    lint_command: str = ""
    conventions: tuple[str, ...] = ()
    recent_runs: tuple[ProjectRun, ...] = ()
    decisions: tuple[ProjectDecision, ...] = ()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def repo_hash(base_dir: Path | None = None) -> str:
    root = str((base_dir or Path.cwd()).expanduser().resolve())
    return hashlib.sha256(root.encode("utf-8")).hexdigest()[:12]


def memory_path(base_dir: Path | None = None) -> Path:
    return PROJECT_MEMORY_ROOT / repo_hash(base_dir) / "memory.json"


def _detect_stack(base_dir: Path) -> tuple[str, ...]:
    profile = inspect_workspace(base_dir)
    ordered: list[str] = []
    seen: set[str] = set()
    for item in [*profile.languages, *profile.frameworks]:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered[:8])


def _detect_command(base_dir: Path, kind: str) -> str:
    profile = inspect_workspace(base_dir)
    command = profile.verification_commands.get(kind)
    if not command:
        return ""
    return shlex.join(command)


def _normalize_conventions(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values or ():
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value[:180])
    return tuple(ordered[:16])


def _truncate_decisions(values: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> tuple[ProjectDecision, ...]:
    decisions: list[ProjectDecision] = []
    for raw in values or ():
        if not isinstance(raw, dict):
            continue
        fact = str(raw.get("fact") or "").strip()
        if not fact:
            continue
        decisions.append(ProjectDecision(fact=fact[:220], timestamp=str(raw.get("timestamp") or _now())))
    return tuple(decisions[:20])


def _truncate_runs(values: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> tuple[ProjectRun, ...]:
    runs: list[ProjectRun] = []
    for raw in values or ():
        if not isinstance(raw, dict):
            continue
        command = str(raw.get("command") or "").strip()
        summary = str(raw.get("summary") or "").strip()
        if not command and not summary:
            continue
        runs.append(ProjectRun(command=command[:80], summary=summary[:220], timestamp=str(raw.get("timestamp") or _now())))
    return tuple(runs[:12])


def load_project_memory(base_dir: Path | None = None) -> ProjectMemory:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    path = memory_path(root)
    if not path.exists():
        return ProjectMemory(
            repo=str(root),
            stack=_detect_stack(root),
            test_command=_detect_command(root, "tests"),
            lint_command=_detect_command(root, "lint"),
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return ProjectMemory(
        repo=str(payload.get("repo") or root),
        stack=tuple(str(item) for item in payload.get("stack", []) if str(item).strip()) or _detect_stack(root),
        test_command=str(payload.get("test_command") or _detect_command(root, "tests")),
        lint_command=str(payload.get("lint_command") or _detect_command(root, "lint")),
        conventions=_normalize_conventions(payload.get("conventions", [])),
        recent_runs=_truncate_runs(payload.get("recent_runs", [])),
        decisions=_truncate_decisions(payload.get("decisions", [])),
    )


def save_project_memory(memory: ProjectMemory, base_dir: Path | None = None) -> ProjectMemory:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    path = memory_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repo": str(root),
        "stack": list(memory.stack),
        "test_command": memory.test_command,
        "lint_command": memory.lint_command,
        "conventions": list(memory.conventions),
        "recent_runs": [asdict(item) for item in memory.recent_runs],
        "decisions": [asdict(item) for item in memory.decisions],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return load_project_memory(root)


def remember_decision(fact: str, *, base_dir: Path | None = None) -> ProjectMemory:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    memory = load_project_memory(root)
    new = ProjectDecision(fact=str(fact or "").strip()[:220], timestamp=_now())
    decisions = [new]
    seen = {new.fact}
    for item in memory.decisions:
        if item.fact in seen:
            continue
        seen.add(item.fact)
        decisions.append(item)
    updated = ProjectMemory(
        repo=memory.repo,
        stack=memory.stack,
        test_command=memory.test_command,
        lint_command=memory.lint_command,
        conventions=memory.conventions,
        recent_runs=memory.recent_runs,
        decisions=tuple(decisions[:20]),
    )
    return save_project_memory(updated, base_dir=root)


def record_project_run(command: str, summary: str, *, base_dir: Path | None = None) -> ProjectMemory:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    memory = load_project_memory(root)
    run = ProjectRun(command=str(command or "").strip()[:80], summary=str(summary or "").strip()[:220], timestamp=_now())
    updated = ProjectMemory(
        repo=memory.repo,
        stack=memory.stack,
        test_command=memory.test_command,
        lint_command=memory.lint_command,
        conventions=memory.conventions,
        recent_runs=(run, *memory.recent_runs)[:12],
        decisions=memory.decisions,
    )
    return save_project_memory(updated, base_dir=root)


def render_memory_block(base_dir: Path | None = None) -> str:
    memory = load_project_memory(base_dir)
    lines = [
        f"Repo: {memory.repo}",
    ]
    if memory.stack:
        lines.append("Stack: " + ", ".join(memory.stack[:6]))
    if memory.test_command:
        lines.append("Test command: " + memory.test_command)
    if memory.lint_command:
        lines.append("Lint command: " + memory.lint_command)
    if memory.conventions:
        lines.append("Conventions: " + "; ".join(memory.conventions[:5]))
    if memory.decisions:
        lines.append("Decisions:")
        lines.extend(f"- {item.fact}" for item in memory.decisions[:5])
    if memory.recent_runs:
        lines.append("Recent runs:")
        for item in memory.recent_runs[:3]:
            lines.append(f"- {item.command}: {item.summary}")
    block = "\n".join(lines).strip()
    if estimate_tokens(block) <= MAX_MEMORY_TOKENS:
        return block
    trimmed = lines[:4]
    if memory.decisions:
        trimmed.append("Decisions: " + " | ".join(item.fact for item in memory.decisions[:3]))
    if memory.recent_runs:
        trimmed.append("Recent: " + " | ".join(f"{item.command}: {item.summary}" for item in memory.recent_runs[:2]))
    block = "\n".join(trimmed)
    while estimate_tokens(block) > MAX_MEMORY_TOKENS and " | " in block:
        block = block.rsplit(" | ", 1)[0]
    return block


__all__ = [
    "MAX_MEMORY_TOKENS",
    "PROJECT_MEMORY_ROOT",
    "ProjectMemory",
    "ProjectDecision",
    "ProjectRun",
    "load_project_memory",
    "memory_path",
    "record_project_run",
    "remember_decision",
    "render_memory_block",
    "repo_hash",
    "save_project_memory",
]
