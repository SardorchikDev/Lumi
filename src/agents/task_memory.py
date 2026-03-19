"""Persistent task memory for Lumi agent runs."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import DATA_DIR

TASK_MEMORY_PATH = DATA_DIR / "agent" / "task_memory.json"
MAX_RUNS = 25


def _default_state() -> dict[str, Any]:
    return {"runs": [], "active": None}


def _workspace_key(base_dir: str | Path | None = None) -> str:
    root = Path(base_dir or Path.cwd()).expanduser().resolve()
    return str(root)


def _detect_branch(base_dir: str | Path | None = None) -> str | None:
    root = Path(base_dir or Path.cwd()).expanduser().resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch or branch == "HEAD":
        return None
    return branch


def _load() -> dict[str, Any]:
    if not TASK_MEMORY_PATH.exists():
        return _default_state()
    try:
        data = json.loads(TASK_MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_state()
    if not isinstance(data, dict):
        return _default_state()
    runs = data.get("runs", [])
    if not isinstance(runs, list):
        runs = []
    active = data.get("active")
    if not isinstance(active, dict):
        active = None
    return {"runs": [run for run in runs if isinstance(run, dict)], "active": active}


def _save(data: dict[str, Any]) -> None:
    TASK_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=TASK_MEMORY_PATH.parent, encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        temp_name = handle.name
    Path(temp_name).replace(TASK_MEMORY_PATH)


def start_active_run(objective: str, *, base_dir: str | Path | None = None, branch: str | None = None) -> None:
    data = _load()
    data["active"] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "objective": " ".join(objective.split())[:200],
        "status": "running",
        "summary": "",
        "touched_files": [],
        "failed_checks": [],
        "workspace": _workspace_key(base_dir),
        "branch": branch if branch is not None else _detect_branch(base_dir),
    }
    _save(data)


def update_active_run(
    *,
    status: str | None = None,
    summary: str | None = None,
    touched_files: list[str] | None = None,
    failed_checks: list[str] | None = None,
    base_dir: str | Path | None = None,
    branch: str | None = None,
) -> None:
    data = _load()
    active = data.get("active")
    if not isinstance(active, dict):
        return
    workspace = _workspace_key(base_dir)
    active_workspace = str(active.get("workspace") or workspace)
    if base_dir is not None and active_workspace != workspace:
        return
    if status:
        active["status"] = status
    if summary is not None:
        active["summary"] = summary[:400]
    if touched_files is not None:
        active["touched_files"] = sorted(set(touched_files))[:20]
    if failed_checks is not None:
        active["failed_checks"] = sorted(set(failed_checks))[:10]
    active["workspace"] = active_workspace
    if branch is not None:
        active["branch"] = branch
    data["active"] = active
    _save(data)


def clear_active_run() -> None:
    data = _load()
    data["active"] = None
    _save(data)


def get_active_run(base_dir: str | Path | None = None) -> dict[str, Any] | None:
    active = _load().get("active")
    if not isinstance(active, dict):
        return None
    if base_dir is None:
        return active
    return active if str(active.get("workspace") or "") == _workspace_key(base_dir) else None


def record_run(
    objective: str,
    *,
    status: str,
    summary: str,
    touched_files: list[str] | None = None,
    failed_checks: list[str] | None = None,
    recovery_used: bool = False,
    base_dir: str | Path | None = None,
    branch: str | None = None,
) -> None:
    data = _load()
    run = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "objective": " ".join(objective.split())[:200],
        "status": status,
        "summary": summary[:400],
        "touched_files": sorted(set(touched_files or []))[:20],
        "failed_checks": sorted(set(failed_checks or []))[:10],
        "recovery_used": bool(recovery_used),
        "workspace": _workspace_key(base_dir),
        "branch": branch if branch is not None else _detect_branch(base_dir),
    }
    data["runs"] = [run] + data.get("runs", [])
    data["runs"] = data["runs"][:MAX_RUNS]
    data["active"] = None
    _save(data)


def get_recent_runs(
    limit: int = 5,
    *,
    base_dir: str | Path | None = None,
    branch: str | None = None,
) -> list[dict[str, Any]]:
    runs = _load().get("runs", [])
    if base_dir is not None:
        workspace = _workspace_key(base_dir)
        runs = [run for run in runs if str(run.get("workspace") or "") == workspace]
    if branch is not None:
        runs = [run for run in runs if str(run.get("branch") or "") == branch]
    return runs[:limit]


def render_task_memory_context(
    task: str,
    limit: int = 3,
    *,
    base_dir: str | Path | None = None,
    branch: str | None = None,
) -> str:
    runs = get_recent_runs(limit=10, base_dir=base_dir, branch=branch)
    active = get_active_run(base_dir=base_dir)
    if not runs and not active:
        return ""

    keywords = {word.lower() for word in task.replace("/", " ").split() if len(word) > 2}
    path_hints = {path.lower() for path in task.split() if "/" in path or "." in path}
    scored: list[tuple[int, dict[str, Any]]] = []
    for run in runs:
        haystack = " ".join(
            [
                str(run.get("objective", "")),
                str(run.get("summary", "")),
                " ".join(run.get("touched_files", [])),
                " ".join(run.get("failed_checks", [])),
                str(run.get("branch", "")),
            ]
        ).lower()
        score = sum(1 for keyword in keywords if keyword in haystack)
        touched = [str(path).lower() for path in run.get("touched_files", [])]
        score += sum(3 for hint in path_hints if any(hint in path for path in touched))
        if branch and str(run.get("branch") or "") == branch:
            score += 2
        if score or len(scored) < limit:
            scored.append((score, run))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [run for _, run in scored[:limit]]
    lines = ["Recent agent task memory:"]
    if active:
        touched = ", ".join(active.get("touched_files", [])[:4]) or "none"
        failed = ", ".join(active.get("failed_checks", [])[:3]) or "none"
        branch_text = f" on {active.get('branch')}" if active.get("branch") else ""
        lines.append(
            f"* active [{active.get('status', '?')}] {active.get('objective', '')}{branch_text}"
        )
        lines.append(f"  touched: {touched}")
        lines.append(f"  failed checks: {failed}")
    if selected and active:
        lines.append("")
    for idx, run in enumerate(selected, start=1):
        touched = ", ".join(run.get("touched_files", [])[:4]) or "none"
        failed = ", ".join(run.get("failed_checks", [])[:3]) or "none"
        branch_text = f" on {run.get('branch')}" if run.get("branch") else ""
        lines.append(
            f"{idx}. [{run.get('status', '?')}] {run.get('objective', '')}{branch_text}"
        )
        lines.append(f"   touched: {touched}")
        lines.append(f"   failed checks: {failed}")
    return "\n".join(lines) if len(lines) > 1 else ""
