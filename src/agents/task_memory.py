"""Persistent task memory for Lumi agent runs."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import DATA_DIR

TASK_MEMORY_PATH = DATA_DIR / "agent" / "task_memory.json"
MAX_RUNS = 25


def _default_state() -> dict[str, Any]:
    return {"runs": [], "active": None}


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


def start_active_run(objective: str) -> None:
    data = _load()
    data["active"] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "objective": " ".join(objective.split())[:200],
        "status": "running",
        "summary": "",
        "touched_files": [],
        "failed_checks": [],
    }
    _save(data)


def update_active_run(
    *,
    status: str | None = None,
    summary: str | None = None,
    touched_files: list[str] | None = None,
    failed_checks: list[str] | None = None,
) -> None:
    data = _load()
    active = data.get("active")
    if not isinstance(active, dict):
        return
    if status:
        active["status"] = status
    if summary is not None:
        active["summary"] = summary[:400]
    if touched_files is not None:
        active["touched_files"] = sorted(set(touched_files))[:20]
    if failed_checks is not None:
        active["failed_checks"] = sorted(set(failed_checks))[:10]
    data["active"] = active
    _save(data)


def clear_active_run() -> None:
    data = _load()
    data["active"] = None
    _save(data)


def get_active_run() -> dict[str, Any] | None:
    active = _load().get("active")
    return active if isinstance(active, dict) else None


def record_run(
    objective: str,
    *,
    status: str,
    summary: str,
    touched_files: list[str] | None = None,
    failed_checks: list[str] | None = None,
    recovery_used: bool = False,
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
    }
    data["runs"] = [run] + data.get("runs", [])
    data["runs"] = data["runs"][:MAX_RUNS]
    data["active"] = None
    _save(data)


def get_recent_runs(limit: int = 5) -> list[dict[str, Any]]:
    return _load().get("runs", [])[:limit]


def render_task_memory_context(task: str, limit: int = 3) -> str:
    runs = get_recent_runs(limit=10)
    active = get_active_run()
    if not runs and not active:
        return ""

    keywords = {word.lower() for word in task.replace("/", " ").split() if len(word) > 2}
    scored: list[tuple[int, dict[str, Any]]] = []
    for run in runs:
        haystack = " ".join(
            [
                str(run.get("objective", "")),
                str(run.get("summary", "")),
                " ".join(run.get("touched_files", [])),
                " ".join(run.get("failed_checks", [])),
            ]
        ).lower()
        score = sum(1 for keyword in keywords if keyword in haystack)
        if score or len(scored) < limit:
            scored.append((score, run))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [run for _, run in scored[:limit]]
    lines = ["Recent agent task memory:"]
    if active:
        touched = ", ".join(active.get("touched_files", [])[:4]) or "none"
        failed = ", ".join(active.get("failed_checks", [])[:3]) or "none"
        lines.append(
            f"* active [{active.get('status', '?')}] {active.get('objective', '')}"
        )
        lines.append(f"  touched: {touched}")
        lines.append(f"  failed checks: {failed}")
    if selected and active:
        lines.append("")
    for idx, run in enumerate(selected, start=1):
        touched = ", ".join(run.get("touched_files", [])[:4]) or "none"
        failed = ", ".join(run.get("failed_checks", [])[:3]) or "none"
        lines.append(
            f"{idx}. [{run.get('status', '?')}] {run.get('objective', '')}"
        )
        lines.append(f"   touched: {touched}")
        lines.append(f"   failed checks: {failed}")
    return "\n".join(lines) if len(lines) > 1 else ""
