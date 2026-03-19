"""Shared git helpers for Lumi slash commands."""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_USAGE = "status|log|diff|commit|commit-confirm|push|pull|branch|branches|remote|fetch|sync"


def _run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _clean_output(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or result.stderr or "").strip()


def _format_sync_output(cwd: Path | None = None) -> str:
    fetch_result = _run_git(["fetch", "--all", "--prune"], cwd=cwd)
    fetch_output = _clean_output(fetch_result)

    status_result = _run_git(["status", "-sb"], cwd=cwd)
    status_output = _clean_output(status_result)
    if not status_output:
        return fetch_output or "Nothing to show (not a git repo or no remotes configured)"

    lines = []
    if fetch_output:
        lines.append(fetch_output)
        lines.append("")
    lines.append("status")
    lines.append(status_output)

    ahead_result = _run_git(["log", "--oneline", "@{upstream}..HEAD"], cwd=cwd)
    behind_result = _run_git(["log", "--oneline", "HEAD..@{upstream}"], cwd=cwd)
    ahead_output = _clean_output(ahead_result)
    behind_output = _clean_output(behind_result)

    if ahead_result.returncode == 0:
        lines.append("")
        lines.append("local only commits")
        lines.append(ahead_output or "(none)")
    if behind_result.returncode == 0:
        lines.append("")
        lines.append("remote only commits")
        lines.append(behind_output or "(none)")

    return "\n".join(lines).strip()


def run_git_subcommand(subcommand: str, cwd: Path | None = None) -> tuple[bool, str]:
    sub = (subcommand or "status").strip().lower()
    if sub == "status":
        status = _run_git(["status", "-sb"], cwd=cwd)
        log = _run_git(["log", "--oneline", "-5"], cwd=cwd)
        combined = "\n".join(part for part in (_clean_output(status), _clean_output(log)) if part).strip()
        return True, combined or "Nothing to show (not a git repo or no changes)"
    if sub == "log":
        result = _run_git(["log", "--oneline", "--graph", "-15"], cwd=cwd)
        return True, _clean_output(result) or "(no commits)"
    if sub == "diff":
        result = _run_git(["diff", "--stat"], cwd=cwd)
        return True, _clean_output(result) or "(no diff)"
    if sub in {"branch", "branches"}:
        result = _run_git(["branch", "-vv" if sub == "branches" else "-a"], cwd=cwd)
        return True, _clean_output(result) or "(no branches)"
    if sub == "remote":
        result = _run_git(["remote", "-v"], cwd=cwd)
        return True, _clean_output(result) or "(no remotes configured)"
    if sub == "fetch":
        result = _run_git(["fetch", "--all", "--prune"], cwd=cwd)
        return True, _clean_output(result) or "Fetch completed."
    if sub == "pull":
        result = _run_git(["pull"], cwd=cwd)
        return True, _clean_output(result) or "Pull completed."
    if sub == "push":
        result = _run_git(["push"], cwd=cwd)
        return True, _clean_output(result) or "Push completed."
    if sub == "sync":
        return True, _format_sync_output(cwd=cwd)
    return False, f"Unknown git subcommand: {sub}  —  try: /git {GIT_USAGE}"
