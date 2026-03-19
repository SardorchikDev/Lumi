"""Shared git helpers for Lumi slash commands."""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_USAGE = "status|summary|review|changed|prepare|log|diff|commit|commit-confirm|push|pull|branch|branches|remote|fetch|sync"


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


def summarize_git_state(cwd: Path | None = None) -> str:
    status = _run_git(["status", "-sb"], cwd=cwd)
    status_output = _clean_output(status)
    if not status_output:
        return "unavailable"
    if status.returncode != 0:
        return status_output

    lines = status_output.splitlines()
    summary = [lines[0]]
    staged = 0
    unstaged = 0
    untracked = 0
    for line in lines[1:]:
        if not line.strip():
            continue
        if line.startswith("??"):
            untracked += 1
        else:
            if len(line) > 0 and line[0] not in {" ", "?"}:
                staged += 1
            if len(line) > 1 and line[1] not in {" ", "?"}:
                unstaged += 1
    summary.append(f"staged {staged} · unstaged {unstaged} · untracked {untracked}")
    return "\n".join(summary)


def _format_review_output(cwd: Path | None = None) -> str:
    status = _run_git(["status", "-sb"], cwd=cwd)
    if status.returncode != 0:
        return _clean_output(status) or "Not a git repository."

    diff_stat = _run_git(["diff", "--stat"], cwd=cwd)
    staged_stat = _run_git(["diff", "--cached", "--stat"], cwd=cwd)
    changed_names = _run_git(["diff", "--name-only"], cwd=cwd)
    staged_names = _run_git(["diff", "--cached", "--name-only"], cwd=cwd)
    recent = _run_git(["log", "--oneline", "-5"], cwd=cwd)

    lines = ["review", summarize_git_state(cwd=cwd), ""]
    staged_output = _clean_output(staged_stat)
    if staged_output:
        lines.append("staged diff")
        lines.append(staged_output)
        lines.append("")
    diff_output = _clean_output(diff_stat)
    if diff_output:
        lines.append("working diff")
        lines.append(diff_output)
        lines.append("")
    staged_files = _clean_output(staged_names)
    if staged_files:
        lines.append("staged files")
        lines.extend(staged_files.splitlines()[:10])
        lines.append("")
    changed_output = _clean_output(changed_names)
    if changed_output:
        lines.append("changed files")
        lines.extend(changed_output.splitlines()[:10])
        lines.append("")
    recent_output = _clean_output(recent)
    if recent_output:
        lines.append("recent commits")
        lines.extend(recent_output.splitlines()[:5])
    return "\n".join(line for line in lines if line is not None).strip()


def _format_changed_output(cwd: Path | None = None) -> str:
    status = _run_git(["status", "--short"], cwd=cwd)
    output = _clean_output(status)
    if not output:
        return "(no changed files)"
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    for line in output.splitlines():
        if line.startswith("??"):
            untracked.append(line[3:])
            continue
        if len(line) > 0 and line[0] not in {" ", "?"}:
            staged.append(line[3:])
        if len(line) > 1 and line[1] not in {" ", "?"}:
            unstaged.append(line[3:])
    lines = ["changed files"]
    if staged:
        lines.append("staged")
        lines.extend(f"  {name}" for name in staged[:12])
    if unstaged:
        lines.append("unstaged")
        lines.extend(f"  {name}" for name in unstaged[:12])
    if untracked:
        lines.append("untracked")
        lines.extend(f"  {name}" for name in untracked[:12])
    return "\n".join(lines)


def _format_prepare_output(cwd: Path | None = None) -> str:
    branch = _run_git(["branch", "--show-current"], cwd=cwd)
    summary = summarize_git_state(cwd=cwd)
    diff_stat = _run_git(["diff", "--stat"], cwd=cwd)
    staged_stat = _run_git(["diff", "--cached", "--stat"], cwd=cwd)
    changed = _run_git(["diff", "--name-only"], cwd=cwd)
    staged = _run_git(["diff", "--cached", "--name-only"], cwd=cwd)
    changed_files = [line for line in _clean_output(changed).splitlines() if line.strip()]
    staged_files = [line for line in _clean_output(staged).splitlines() if line.strip()]
    headline_source = staged_files or changed_files
    headline = "update workspace"
    if headline_source:
        focus = ", ".join(headline_source[:2])
        headline = f"update {focus}"
    lines = [
        "prepare commit",
        f"branch: {_clean_output(branch) or '(detached)'}",
        summary,
        "",
        "suggested commit title",
        f"  {headline}",
    ]
    staged_output = _clean_output(staged_stat)
    diff_output = _clean_output(diff_stat)
    if staged_output:
        lines.extend(["", "staged diff", staged_output])
    if diff_output:
        lines.extend(["", "working diff", diff_output])
    if changed_files:
        lines.extend(["", "focus files", *[f"  {name}" for name in changed_files[:8]]])
    return "\n".join(lines).strip()


def run_git_subcommand(subcommand: str, cwd: Path | None = None) -> tuple[bool, str]:
    sub = (subcommand or "status").strip().lower()
    if sub == "status":
        status = _run_git(["status", "-sb"], cwd=cwd)
        log = _run_git(["log", "--oneline", "-5"], cwd=cwd)
        combined = "\n".join(part for part in (_clean_output(status), _clean_output(log)) if part).strip()
        return True, combined or "Nothing to show (not a git repo or no changes)"
    if sub == "summary":
        return True, summarize_git_state(cwd=cwd)
    if sub == "review":
        return True, _format_review_output(cwd=cwd)
    if sub == "changed":
        return True, _format_changed_output(cwd=cwd)
    if sub == "prepare":
        return True, _format_prepare_output(cwd=cwd)
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
