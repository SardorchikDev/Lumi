"""Helpers for external CLI handoff capture, storage, and search."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import CONVERSATIONS_DIR

_ANSI_RE = re.compile(r"\033\[[^a-zA-Z]*[a-zA-Z]|\033\].*?\007|\033.")
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _slug(value: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("-", value.strip().lower()).strip("-")
    return cleaned or "session"


def _normalize_list(values: Any) -> list[str]:
    if isinstance(values, list):
        return [str(value).strip() for value in values if str(value).strip()]
    if isinstance(values, str) and values.strip():
        return [values.strip()]
    return []


def sanitize_handoff_transcript(text: str) -> str:
    """Strip terminal control codes and `script` wrapper noise."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = _ANSI_RE.sub("", normalized)
    lines: list[str] = []
    for raw in stripped.splitlines():
        line = raw.rstrip()
        if line.startswith(("Script started on ", "Script done on ")):
            continue
        if not line and lines and not lines[-1]:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def conversation_dir_for(cli_name: str) -> Path:
    path = CONVERSATIONS_DIR / _slug(cli_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extract_json_block(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].startswith("```"):
            stripped = "\n".join(lines[1:-1]).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def fallback_mode_summary_data(display_name: str, transcript: str, *, max_lines: int = 5) -> dict[str, Any]:
    """Build a lightweight structured fallback summary if model parsing fails."""
    visible: list[str] = []
    for line in reversed([item.strip() for item in transcript.splitlines() if item.strip()]):
        if line in visible:
            continue
        visible.append(line[:160])
        if len(visible) >= max_lines:
            break
    visible.reverse()

    commands = [line for line in visible if line.startswith(("$ ", "> ", "/", "git ", "python ", "pytest ", "npm ", "pnpm "))]
    files = [line for line in visible if "/" in line and "." in line]
    tldr = f"Returned from {display_name}." if not visible else f"Returned from {display_name} after discussing or running work in the external CLI."
    return {
        "tldr": tldr,
        "files": files[:4],
        "commands": commands[:4],
        "decisions": visible[:3],
        "next_steps": visible[-2:] if visible else [],
    }


def parse_mode_summary_response(text: str, display_name: str, transcript: str) -> dict[str, Any]:
    """Parse the model summary response into a structured dict."""
    fallback = fallback_mode_summary_data(display_name, transcript)
    payload = _extract_json_block(text)
    try:
        data = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    if not isinstance(data, dict):
        return fallback
    return {
        "tldr": str(data.get("tldr") or fallback["tldr"]).strip(),
        "files": _normalize_list(data.get("files")) or fallback["files"],
        "commands": _normalize_list(data.get("commands")) or fallback["commands"],
        "decisions": _normalize_list(data.get("decisions")) or fallback["decisions"],
        "next_steps": _normalize_list(data.get("next_steps")) or fallback["next_steps"],
    }


def format_mode_tldr(summary: dict[str, Any], display_name: str) -> str:
    """Render a structured mode summary into a concise assistant message."""
    lines = [f"TL;DR from your {display_name} session:"]
    tldr = str(summary.get("tldr", "")).strip()
    if tldr:
        lines.append(tldr)

    def add_block(label: str, values: Any, limit: int = 4) -> None:
        items = _normalize_list(values)[:limit]
        if not items:
            return
        lines.append(f"{label}:")
        lines.extend(f"- {item}" for item in items)

    add_block("files", summary.get("files"))
    add_block("commands", summary.get("commands"))
    add_block("decisions", summary.get("decisions"))
    add_block("next steps", summary.get("next_steps"))
    return "\n".join(lines)


def save_mode_conversation(
    *,
    cli_name: str,
    display_name: str,
    transcript: str,
    summary: dict[str, Any],
    exit_code: int,
    cwd: str,
    started_at: str,
    ended_at: str,
    duration_seconds: float,
    git_branch: str,
    binary: str,
    binary_path: str,
    binary_version: str,
    captured: bool,
) -> Path:
    """Persist a captured `/mode` session under `conversations/<cli>/`."""
    root = conversation_dir_for(cli_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = root / f"{timestamp}.json"
    payload = {
        "cli": cli_name,
        "name": display_name,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "cwd": cwd,
        "git_branch": git_branch,
        "binary": binary,
        "binary_path": binary_path,
        "binary_version": binary_version,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": round(duration_seconds, 2),
        "exit_code": exit_code,
        "captured": captured,
        "summary": summary,
        "transcript": transcript,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_mode_conversation(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    data["path"] = str(path)
    return data


def list_mode_conversations(cli_name: str | None = None, *, limit: int | None = None) -> list[dict[str, Any]]:
    root = conversation_dir_for(cli_name) if cli_name else CONVERSATIONS_DIR
    if not root.exists():
        return []
    if cli_name:
        files = sorted(root.glob("*.json"), reverse=True)
    else:
        files = sorted(root.glob("*/*.json"), reverse=True)
    results: list[dict[str, Any]] = []
    for path in files:
        loaded = load_mode_conversation(path)
        if loaded:
            results.append(loaded)
        if limit is not None and len(results) >= limit:
            break
    return results


def search_mode_conversations(query: str, cli_name: str | None = None, *, limit: int = 8) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return list_mode_conversations(cli_name, limit=limit)
    scored: list[tuple[int, dict[str, Any]]] = []
    for record in list_mode_conversations(cli_name):
        haystack = "\n".join(
            [
                str(record.get("name", "")),
                str(record.get("cwd", "")),
                json.dumps(record.get("summary", {}), ensure_ascii=False),
                str(record.get("transcript", "")),
            ]
        ).lower()
        score = haystack.count(needle)
        if score:
            scored.append((score, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [record for _, record in scored[:limit]]


def build_mode_review_card(record: dict[str, Any]) -> dict[str, Any]:
    summary = record.get("summary", {}) if isinstance(record.get("summary"), dict) else {}
    summary_lines = [
        f"cli: {record.get('name', record.get('cli', '?'))}",
        f"cwd: {record.get('cwd', '?')}",
        f"duration: {record.get('duration_seconds', '?')}s",
        f"saved: {Path(str(record.get('path', ''))).name if record.get('path') else '?'}",
    ]
    if record.get("git_branch"):
        summary_lines.append(f"branch: {record['git_branch']}")
    preview_lines = []
    if summary.get("tldr"):
        preview_lines.append(str(summary["tldr"]))
    preview_lines.extend(_normalize_list(summary.get("next_steps"))[:3])
    if not preview_lines:
        preview_lines = ["No summary preview available."]
    return {
        "title": f"{record.get('cli', 'mode')} return",
        "summary_lines": summary_lines,
        "preview_lines": preview_lines,
        "footer": "Esc close  ·  /mode conversations",
    }


def build_mode_context_text(record: dict[str, Any]) -> str:
    """Flatten a saved mode record into retrievable context text."""
    summary = record.get("summary", {}) if isinstance(record.get("summary"), dict) else {}
    lines = [
        f"CLI: {record.get('name', record.get('cli', '?'))}",
        f"Directory: {record.get('cwd', '?')}",
    ]
    if record.get("git_branch"):
        lines.append(f"Branch: {record['git_branch']}")
    if record.get("binary_version"):
        lines.append(f"Version: {record['binary_version']}")
    if summary.get("tldr"):
        lines.append(f"TL;DR: {summary['tldr']}")
    for label in ("files", "commands", "decisions", "next_steps"):
        values = _normalize_list(summary.get(label))
        if values:
            lines.append(f"{label}:")
            lines.extend(f"- {item}" for item in values[:6])
    transcript = str(record.get("transcript", "")).strip()
    if transcript:
        lines.append("")
        lines.append("Transcript:")
        lines.append(transcript)
    return "\n".join(lines).strip()
