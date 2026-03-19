"""
Lumi Agent Mode — autonomous multi-step task execution.

Give Lumi a goal → it inspects the repo → plans safe steps → previews changes →
executes them → optionally rolls back on failure.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path
from typing import Any

R = "\033[0m"
B = "\033[1m"
D = "\033[2m"
GN = "\033[38;5;114m"
RE = "\033[38;5;203m"
YE = "\033[38;5;179m"
PU = "\033[38;5;141m"
CY = "\033[38;5;117m"
DG = "\033[38;5;238m"
WH = "\033[255m"
GR = "\033[38;5;245m"

RISKY_KEYWORDS = (
    "delete", "remove", "drop", "overwrite", "truncate",
    "deploy", "publish", "install", "network", "format",
)

MAX_DIFF_LINES = 80
MAX_DIFF_CHARS = 4000
MAX_READ_CHARS = 4000
MAX_CONTEXT_FILES = 6
MAX_CONTEXT_FILE_CHARS = 1200
MAX_CONTEXT_MATCHES = 8

SAFE_ACTIONS = {
    "list_dir",
    "read_file",
    "run_tests",
    "run_ruff",
    "run_mypy",
    "git_status",
    "git_diff",
    "mkdir",
    "write_json",
    "search_code",
    "patch_file",
    "patch_lines",
}
READ_ACTIONS = {"list_dir", "read_file", "search_code", "git_status", "git_diff"}
VERIFY_ACTIONS = {"run_tests", "run_ruff", "run_mypy"}
FILE_MUTATION_ACTIONS = {"write_json", "patch_file", "patch_lines"}
DIR_MUTATION_ACTIONS = {"mkdir"}

ACTION_HINTS = (
    ("git status", "git_status"),
    ("status of repo", "git_status"),
    ("git diff", "git_diff"),
    ("diff", "git_diff"),
    ("run tests", "run_tests"),
    ("run pytest", "run_tests"),
    ("pytest", "run_tests"),
    ("run ruff", "run_ruff"),
    ("lint", "run_ruff"),
    ("ruff", "run_ruff"),
    ("run mypy", "run_mypy"),
    ("type check", "run_mypy"),
    ("mypy", "run_mypy"),
    ("read file", "read_file"),
    ("open file", "read_file"),
    ("inspect file", "read_file"),
    ("create directory", "mkdir"),
    ("make directory", "mkdir"),
    ("create folder", "mkdir"),
    ("make folder", "mkdir"),
    ("mkdir", "mkdir"),
    ("write json", "write_json"),
    ("json file", "write_json"),
    ("json config", "write_json"),
    ("search code", "search_code"),
    ("search the codebase", "search_code"),
    ("find usages", "search_code"),
    ("find references", "search_code"),
    ("patch file", "patch_file"),
    ("edit file", "patch_file"),
    ("update file", "patch_file"),
    ("replace text", "patch_file"),
    ("replace lines", "patch_lines"),
    ("update lines", "patch_lines"),
    ("list files", "list_dir"),
    ("list directory", "list_dir"),
    ("show files", "list_dir"),
)

PLAN_SYSTEM_PROMPT = """You are an autonomous coding agent. Produce a grounded execution plan for the current workspace.

Return ONLY a JSON array of steps. Each step:
{
  "id": 1,
  "description": "Human-readable description",
  "type": "action" | "file_write" | "ai_task" | "ask_user",
  "action": "list_dir" | "read_file" | "run_tests" | "run_ruff" | "run_mypy" | "git_status" | "git_diff" | "mkdir" | "write_json" | "search_code" | "patch_file" | "patch_lines",
  "target": "relative path used by many actions",
  "path": "file path for file_write / write_json / patch actions",
  "content": "full file content for file_write",
  "query": "literal search text for search_code",
  "json_content": {"key": "value"},
  "old_text": "exact text to replace in patch_file",
  "new_text": "replacement text for patch_file",
  "replace_all": false,
  "start_line": 10,
  "end_line": 14,
  "old_block": "expected current block for patch_lines",
  "replacement": "replacement block for patch_lines",
  "prompt": "prompt for ai_task",
  "question": "question for ask_user",
  "risky": true | false
}

Rules:
- Ground the plan in the workspace context provided to you.
- Prefer actions to inspect the repo before reasoning.
- Prefer file_write for new files or full rewrites.
- Prefer patch_file or patch_lines for editing existing files.
- Prefer write_json for JSON config changes.
- Prefer mkdir before writing nested files into new directories.
- Prefer run_tests, run_ruff, and run_mypy for verification when relevant.
- Use ai_task only when reasoning is needed and no action or file change fits.
- Never use raw shell commands.
- All targets and paths must stay inside the current workspace.
- Keep steps atomic and small.
- Max 10 steps.
- Return ONLY the JSON array, nothing else.
"""


@dataclass
class JournalRecord:
    kind: str
    path: Path
    existed: bool
    content: str | None = None


@dataclass
class ChangeJournal:
    records: list[JournalRecord] = field(default_factory=list)

    def _has_record(self, kind: str, path: Path) -> bool:
        return any(record.kind == kind and record.path == path for record in self.records)

    def record_file(self, path: Path) -> None:
        if self._has_record("file", path):
            return
        existed = path.exists()
        content = path.read_text(encoding="utf-8", errors="replace") if existed else None
        self.records.append(JournalRecord("file", path, existed, content))

    def record_dir(self, path: Path) -> None:
        if self._has_record("dir", path):
            return
        self.records.append(JournalRecord("dir", path, path.exists(), None))

    def has_changes(self) -> bool:
        return bool(self.records)

    def rollback(self) -> list[str]:
        rolled_back: list[str] = []
        for record in reversed(self.records):
            if record.kind == "file":
                if record.existed:
                    record.path.parent.mkdir(parents=True, exist_ok=True)
                    record.path.write_text(record.content or "", encoding="utf-8")
                else:
                    record.path.unlink(missing_ok=True)
                rolled_back.append(str(record.path))
            elif record.kind == "dir" and not record.existed:
                try:
                    record.path.rmdir()
                    rolled_back.append(str(record.path) + "/")
                except OSError:
                    continue
        return rolled_back


def _resolve_agent_path(path: str, base_dir: Path) -> Path:
    candidate = Path(os.path.expanduser(path))
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def _resolve_action_target(target: str, base_dir: Path) -> tuple[bool, str, Path | None]:
    target = (target or ".").strip()
    try:
        resolved = _resolve_agent_path(target, base_dir)
    except OSError as exc:
        return False, f"Invalid target: {exc}", None
    if not resolved.is_relative_to(base_dir):
        return False, "Blocked: action targets must stay inside the current workspace", None
    return True, "", resolved


def _run_command(cmd: list[str], cwd: Path, timeout: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return False, f"Command timed out ({timeout}s)"
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output or "(no output)"


def _read_context_file(path: Path, base_dir: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"## {path.relative_to(base_dir)}\n[read failed: {exc}]"
    text = text[:MAX_CONTEXT_FILE_CHARS].rstrip()
    return f"## {path.relative_to(base_dir)}\n{text}"


def _task_keywords(task: str) -> list[str]:
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_.-]{2,}", task.lower())
    stop = {"the", "and", "for", "with", "into", "from", "that", "this", "add", "make", "build", "update"}
    return [word for word in words if word not in stop][:8]


def _search_relevant_paths(base_dir: Path, task: str) -> list[Path]:
    keywords = _task_keywords(task)
    if not keywords:
        return []
    matches: list[tuple[int, Path]] = []
    for path in base_dir.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__", "node_modules", "venv", ".venv"} for part in path.parts):
            continue
        score = 0
        lower_name = str(path.relative_to(base_dir)).lower()
        for word in keywords:
            if word in lower_name:
                score += 3
        if score == 0:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")[:4000].lower()
            except OSError:
                continue
            for word in keywords:
                if word in text:
                    score += 1
        if score:
            matches.append((score, path))
    matches.sort(key=lambda item: (-item[0], str(item[1])))
    return [path for _, path in matches[:MAX_CONTEXT_MATCHES]]


def collect_planning_context(task: str, base_dir: Path | None = None) -> str:
    """Gather lightweight repo facts before asking the model to plan."""
    base_dir = (base_dir or Path.cwd()).resolve()
    lines = [f"Workspace root: {base_dir}", ""]

    top_entries = sorted(base_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    if top_entries:
        lines.append("Top-level entries:")
        for entry in top_entries[:40]:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"- {entry.name}{suffix}")
        lines.append("")

    key_files = [
        "LUMI.md",
        "README.md",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "Cargo.toml",
        "go.mod",
    ]
    mentioned = sorted(set(re.findall(r"[\w./-]+\.\w+", task)))
    candidates = [base_dir / name for name in key_files + mentioned]
    readable = [path for path in candidates if path.exists() and path.is_file()]
    if readable:
        lines.append("Relevant workspace files:")
        for path in readable[:MAX_CONTEXT_FILES]:
            lines.append(_read_context_file(path, base_dir))
            lines.append("")

    relevant_paths = _search_relevant_paths(base_dir, task)
    if relevant_paths:
        lines.append("Likely relevant files:")
        for path in relevant_paths:
            lines.append(f"- {path.relative_to(base_dir)}")
        lines.append("")

    git_ok, git_status = _run_command(["git", "status", "--short"], base_dir, timeout=15)
    if git_ok or "not a git repository" not in git_status.lower():
        lines.append("Git status:")
        lines.append(git_status or "(clean)")

    return "\n".join(lines).strip()


def _append_verification_step(steps: list[dict], base_dir: Path) -> list[dict]:
    has_mutation = any(
        step.get("type") == "file_write"
        or (step.get("type") == "action" and step.get("action") in FILE_MUTATION_ACTIONS | DIR_MUTATION_ACTIONS)
        for step in steps
    )
    has_verification = any(
        step.get("type") == "action" and step.get("action") in VERIFY_ACTIONS
        for step in steps
    )
    if not has_mutation or has_verification:
        return steps

    verify_action = "run_tests" if (base_dir / "tests").exists() else "run_ruff"
    if verify_action == "run_ruff" and not (base_dir / "pyproject.toml").exists():
        return steps

    step = {
        "id": len(steps) + 1,
        "description": "Verify the workspace after changes",
        "type": "action",
        "action": verify_action,
        "target": ".",
        "risky": False,
    }
    return steps + [step]


def _infer_action_from_step(step: dict) -> str:
    text = " ".join(str(step.get(key, "")) for key in ("description", "prompt", "question", "command")).lower()
    for needle, action in ACTION_HINTS:
        if needle in text:
            return action
    return ""


def normalize_plan(steps: list[dict]) -> list[dict]:
    """Normalize model output toward structured execution and reject weak plans."""
    if not isinstance(steps, list):
        raise ValueError("Plan must be a JSON array of steps")

    normalized: list[dict] = []
    ai_task_count = 0

    for index, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Step {index} is not an object")

        step = dict(raw_step)
        step["id"] = index
        step["description"] = str(step.get("description", "")).strip() or f"Step {index}"
        stype = str(step.get("type", "")).strip() or "ai_task"

        if stype == "shell":
            inferred = _infer_action_from_step(step)
            if not inferred:
                raise ValueError(f"Step {index} uses legacy shell execution without a safe action mapping")
            step["action"] = inferred
            step.pop("command", None)
            stype = "action"

        if stype == "action":
            if not step.get("action"):
                inferred = _infer_action_from_step(step)
                if inferred:
                    step["action"] = inferred
            action = str(step.get("action", "")).strip()
            if action not in SAFE_ACTIONS:
                raise ValueError(f"Step {index} has unsupported action '{action}'")
            if action == "mkdir":
                step["target"] = str(step.get("target") or step.get("path") or "").strip()
                if not step["target"]:
                    raise ValueError(f"Step {index} mkdir is missing a target")
            if action == "write_json":
                if not str(step.get("path", "")).strip():
                    raise ValueError(f"Step {index} write_json is missing a file path")
                if "json_content" not in step:
                    raise ValueError(f"Step {index} write_json is missing json_content")
            if action == "search_code" and not str(step.get("query", "")).strip():
                raise ValueError(f"Step {index} search_code is missing a query")
            if action == "patch_file":
                if not str(step.get("path", "")).strip():
                    raise ValueError(f"Step {index} patch_file is missing a file path")
                if "old_text" not in step:
                    raise ValueError(f"Step {index} patch_file is missing old_text")
                if "new_text" not in step:
                    raise ValueError(f"Step {index} patch_file is missing new_text")
            if action == "patch_lines":
                if not str(step.get("path", "")).strip():
                    raise ValueError(f"Step {index} patch_lines is missing a file path")
                if step.get("start_line") is None or step.get("end_line") is None:
                    raise ValueError(f"Step {index} patch_lines is missing line bounds")
                if "replacement" not in step:
                    raise ValueError(f"Step {index} patch_lines is missing replacement")

        elif stype == "file_write":
            if not str(step.get("path", "")).strip():
                raise ValueError(f"Step {index} is missing a file path")
            step["path"] = str(step["path"]).strip()
            step["content"] = str(step.get("content", ""))

        elif stype == "ai_task":
            ai_task_count += 1
            prompt = str(step.get("prompt", "")).strip()
            if not prompt:
                inferred = _infer_action_from_step(step)
                if inferred:
                    step["action"] = inferred
                    stype = "action"
                else:
                    raise ValueError(f"Step {index} ai_task is missing a prompt")

        elif stype == "ask_user":
            if not str(step.get("question", "")).strip():
                raise ValueError(f"Step {index} ask_user is missing a question")

        else:
            raise ValueError(f"Step {index} has unsupported type '{stype}'")

        step["type"] = stype
        normalized.append(step)

    if normalized and ai_task_count == len(normalized) and len(normalized) > 1:
        raise ValueError("Plan is too vague: all steps were ai_task")

    return normalized


def make_plan(task: str, client: Any, model: str, base_dir: Path | None = None) -> list[dict]:
    """Ask AI to break task into grounded, normalized steps."""
    base_dir = (base_dir or Path.cwd()).resolve()
    workspace_context = collect_planning_context(task, base_dir)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Task:\n{task}\n\nWorkspace context:\n{workspace_context}",
                },
            ],
            max_tokens=1800,
            temperature=0.2,
            stream=False,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
        normalized = normalize_plan(json.loads(raw))
        normalized = _append_verification_step(normalized, base_dir)
        for index, step in enumerate(normalized, start=1):
            step["id"] = index
        return normalized
    except Exception as exc:
        raise RuntimeError(f"Could not generate plan: {exc}") from exc


def is_risky(step: dict) -> bool:
    if step.get("risky"):
        return True
    text = " ".join(
        str(step.get(key, ""))
        for key in ("description", "action", "path", "target", "prompt", "question")
    ).lower()
    return any(keyword in text for keyword in RISKY_KEYWORDS)


def validate_file_write_path(path: str, base_dir: Path) -> tuple[bool, str]:
    if not path:
        return False, "No path specified"
    try:
        resolved = _resolve_agent_path(path, base_dir)
    except OSError as exc:
        return False, f"Invalid path: {exc}"
    if not resolved.is_relative_to(base_dir):
        return False, "Blocked: file writes must stay inside the current workspace"
    return True, ""


def build_file_write_preview(path: Path, new_content: str) -> str:
    if not path.exists():
        return ""
    try:
        old_content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"[Could not read existing file for preview: {exc}]"
    if old_content == new_content:
        return "[No changes]"
    diff_lines = list(
        unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"{path.name} (current)",
            tofile=f"{path.name} (agent)",
            lineterm="",
        )
    )
    truncated = False
    if len(diff_lines) > MAX_DIFF_LINES:
        diff_lines = diff_lines[:MAX_DIFF_LINES]
        truncated = True
    preview = "\n".join(diff_lines)
    if len(preview) > MAX_DIFF_CHARS:
        preview = preview[:MAX_DIFF_CHARS].rstrip()
        truncated = True
    if truncated:
        preview += "\n... diff truncated ..."
    return preview


def print_diff_preview(path: Path, updated_content: str) -> None:
    preview = build_file_write_preview(path, updated_content)
    if not preview or preview == "[No changes]":
        return
    print(f"  {DG}diff preview for {path}:{R}")
    for line in preview.splitlines():
        color = GR
        if line.startswith("+") and not line.startswith("+++"):
            color = GN
        elif line.startswith("-") and not line.startswith("---"):
            color = RE
        elif line.startswith("@@"):
            color = CY
        print(f"  {color}{line}{R}")


def _compute_patch_file_update(step: dict, path: Path) -> tuple[bool, str]:
    old_text = str(step.get("old_text", ""))
    new_text = str(step.get("new_text", ""))
    replace_all = bool(step.get("replace_all", False))
    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)
    matches = current.count(old_text)
    if matches == 0:
        return False, "Blocked: patch_file old_text was not found"
    if matches > 1 and not replace_all:
        return False, "Blocked: patch_file old_text is ambiguous; set replace_all=true"
    updated = current.replace(old_text, new_text) if replace_all else current.replace(old_text, new_text, 1)
    return True, updated


def _compute_patch_lines_update(step: dict, path: Path) -> tuple[bool, str]:
    try:
        start_line = int(step.get("start_line"))
        end_line = int(step.get("end_line"))
    except (TypeError, ValueError):
        return False, "Blocked: patch_lines requires integer line bounds"
    if start_line < 1 or end_line < start_line:
        return False, "Blocked: patch_lines has invalid line bounds"

    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)

    lines = current.splitlines(keepends=True)
    if end_line > len(lines):
        return False, "Blocked: patch_lines line range is outside the file"

    current_block = "".join(lines[start_line - 1:end_line])
    old_block = step.get("old_block")
    if old_block is not None and str(old_block) != current_block:
        return False, "Blocked: patch_lines old_block does not match the current file"

    replacement = str(step.get("replacement", ""))
    new_lines = replacement.splitlines(keepends=True)
    if replacement and not replacement.endswith(("\n", "\r")) and current_block.endswith("\n"):
        new_lines.append("\n")
    updated_lines = lines[:start_line - 1] + new_lines + lines[end_line:]
    return True, "".join(updated_lines)


def compute_step_file_change(step: dict, base_dir: Path) -> tuple[bool, str, Path | None, str | None]:
    """Return a pending file mutation as (ok, message, path, new_content)."""
    stype = step.get("type", "")
    if stype == "file_write":
        ok, reason = validate_file_write_path(step.get("path", ""), base_dir)
        if not ok:
            return False, reason, None, None
        path = _resolve_agent_path(step["path"], base_dir)
        return True, "file_write", path, str(step.get("content", ""))

    if stype != "action":
        return False, "Not a file mutation step", None, None

    action = step.get("action", "")
    if action == "write_json":
        ok, reason = validate_file_write_path(step.get("path", ""), base_dir)
        if not ok:
            return False, reason, None, None
        path = _resolve_agent_path(step["path"], base_dir)
        try:
            content = json.dumps(step.get("json_content"), indent=2, ensure_ascii=False) + "\n"
        except (TypeError, ValueError) as exc:
            return False, f"Invalid json_content: {exc}", None, None
        return True, action, path, content

    if action == "patch_file":
        ok, reason = validate_action_step(step, base_dir)
        if not ok:
            return False, reason, None, None
        path = _resolve_agent_path(step["path"], base_dir)
        ok, updated = _compute_patch_file_update(step, path)
        return ok, ("patch_file" if ok else updated), path, (updated if ok else None)

    if action == "patch_lines":
        ok, reason = validate_action_step(step, base_dir)
        if not ok:
            return False, reason, None, None
        path = _resolve_agent_path(step["path"], base_dir)
        ok, updated = _compute_patch_lines_update(step, path)
        return ok, ("patch_lines" if ok else updated), path, (updated if ok else None)

    return False, "Not a file mutation step", None, None


def validate_action_step(step: dict, base_dir: Path) -> tuple[bool, str]:
    action = step.get("action", "").strip()
    if action not in SAFE_ACTIONS:
        return False, f"Unsupported action in agent mode: {action or '(missing)'}"

    target_value = step.get("target", ".")
    if action in {"write_json", "patch_file", "patch_lines"}:
        target_value = step.get("path", "")
    ok, reason, resolved = _resolve_action_target(target_value, base_dir)
    if not ok:
        return False, reason

    if action == "mkdir":
        if resolved == base_dir:
            return False, "Blocked: mkdir target must not be the workspace root"
        return True, ""

    if action == "list_dir":
        if not resolved.exists():
            return False, "Blocked: list_dir target does not exist"
        if not resolved.is_dir():
            return False, "Blocked: list_dir target must be a directory"
        return True, ""

    if action == "read_file":
        if not resolved.is_file():
            return False, "Blocked: read_file target must be an existing file"
        return True, ""

    if action in {"run_tests", "run_ruff", "run_mypy", "git_diff"}:
        return True, ""

    if action == "git_status":
        return True, ""

    if action == "write_json":
        if resolved.exists() and not resolved.is_file():
            return False, "Blocked: write_json target must be a file path"
        try:
            json.dumps(step.get("json_content"))
        except (TypeError, ValueError) as exc:
            return False, f"Invalid json_content: {exc}"
        return True, ""

    if action == "search_code":
        if not str(step.get("query", "")).strip():
            return False, "Blocked: search_code requires a query"
        return True, ""

    if action == "patch_file":
        if not resolved.is_file():
            return False, "Blocked: patch_file target must be an existing file"
        old_text = str(step.get("old_text", ""))
        if not old_text:
            return False, "Blocked: patch_file requires old_text"
        return _compute_patch_file_update(step, resolved)[:2]

    if action == "patch_lines":
        if not resolved.is_file():
            return False, "Blocked: patch_lines target must be an existing file"
        return _compute_patch_lines_update(step, resolved)[:2]

    return True, ""


def execute_action_step(step: dict, base_dir: Path) -> tuple[bool, str]:
    action = step.get("action", "").strip()
    target_value = step.get("target", ".")
    if action in {"write_json", "patch_file", "patch_lines"}:
        target_value = step.get("path", "")
    _, _, target = _resolve_action_target(target_value, base_dir)

    if action == "list_dir":
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for entry in entries[:200]:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.relative_to(base_dir)}{suffix}")
        return True, "\n".join(lines) if lines else "(empty directory)"

    if action == "read_file":
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return False, str(exc)
        if len(content) > MAX_READ_CHARS:
            content = content[:MAX_READ_CHARS].rstrip() + "\n... file truncated ..."
        return True, content or "(empty file)"

    if action == "run_tests":
        cmd = [sys.executable, "-m", "pytest"]
        if target != base_dir:
            cmd.append(str(target.relative_to(base_dir)))
        return _run_command(cmd, base_dir, timeout=60)

    if action == "run_ruff":
        if not shutil.which("ruff"):
            return False, "ruff is not installed"
        cmd = ["ruff", "check"]
        cmd.append(str(target.relative_to(base_dir)) if target != base_dir else ".")
        return _run_command(cmd, base_dir, timeout=60)

    if action == "run_mypy":
        if not shutil.which("mypy"):
            return False, "mypy is not installed"
        cmd = ["mypy"]
        cmd.append(str(target.relative_to(base_dir)) if target != base_dir else ".")
        return _run_command(cmd, base_dir, timeout=90)

    if action == "git_status":
        return _run_command(["git", "status", "--short"], base_dir, timeout=30)

    if action == "git_diff":
        cmd = ["git", "diff", "--"]
        if target != base_dir:
            cmd.append(str(target.relative_to(base_dir)))
        ok, output = _run_command(cmd, base_dir, timeout=30)
        if len(output) > MAX_DIFF_CHARS:
            output = output[:MAX_DIFF_CHARS].rstrip() + "\n... diff truncated ..."
        return ok, output or "(no diff)"

    if action == "mkdir":
        target.mkdir(parents=True, exist_ok=True)
        return True, f"Created directory: {target}"

    if action == "write_json":
        ok, _, path, content = compute_step_file_change(step, base_dir)
        if not ok or path is None or content is None:
            return False, "Could not prepare JSON write"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True, f"Written JSON: {path}"

    if action == "search_code":
        query = str(step.get("query", "")).strip()
        matches: list[str] = []
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    matches.append(f"{path.relative_to(base_dir)}:{lineno}: {line.strip()}")
                    if len(matches) >= 50:
                        return True, "\n".join(matches) + "\n... search truncated ..."
        return True, "\n".join(matches) if matches else "(no matches)"

    if action in {"patch_file", "patch_lines"}:
        ok, _, path, content = compute_step_file_change(step, base_dir)
        if not ok or path is None or content is None:
            return False, "Could not prepare file patch"
        path.write_text(content, encoding="utf-8")
        return True, f"Patched file: {path}"

    return False, f"Unsupported action in agent mode: {action}"


def confirm(prompt_text: str) -> bool:
    try:
        ans = input(f"  {YE}?{R}  {prompt_text}  {DG}[y/N]{R}  ").strip().lower()
        return ans in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


def _inspect_step(step: dict, base_dir: Path) -> dict[str, Any]:
    info: dict[str, Any] = {"type": step.get("type"), "step": step, "kind": "other", "risky": is_risky(step)}
    stype = step.get("type")
    if stype == "action":
        action = step.get("action")
        ok, reason = validate_action_step(step, base_dir)
        info["ok"] = ok
        info["reason"] = reason
        if action in READ_ACTIONS:
            info["kind"] = "read"
        elif action in VERIFY_ACTIONS:
            info["kind"] = "verify"
        elif action in DIR_MUTATION_ACTIONS:
            info["kind"] = "mkdir"
            if ok:
                info["path"] = _resolve_agent_path(step.get("target", ""), base_dir)
        elif action in FILE_MUTATION_ACTIONS:
            ok, reason, path, content = compute_step_file_change(step, base_dir)
            info["kind"] = "patch" if action in {"patch_file", "patch_lines"} else "file"
            info["ok"] = ok
            info["reason"] = reason
            info["path"] = path
            info["content"] = content
    elif stype == "file_write":
        ok, reason, path, content = compute_step_file_change(step, base_dir)
        info["kind"] = "file"
        info["ok"] = ok
        info["reason"] = reason
        info["path"] = path
        info["content"] = content
    else:
        info["ok"] = True
    return info


def _render_grouped_summary(steps: list[dict], base_dir: Path) -> list[dict[str, Any]]:
    inspected = [_inspect_step(step, base_dir) for step in steps]
    file_changes = sum(1 for item in inspected if item.get("kind") in {"file", "patch"})
    patches = sum(1 for item in inspected if item.get("kind") == "patch")
    directories = sum(1 for item in inspected if item.get("kind") == "mkdir")
    verifications = sum(1 for item in inspected if item.get("kind") == "verify")
    reads = sum(1 for item in inspected if item.get("kind") == "read")
    risky = sum(1 for item in inspected if item.get("risky"))
    print(
        f"  {B}{WH}Summary{R}  {file_changes} file changes  {patches} patches  "
        f"{directories} dirs  {verifications} checks  {reads} reads  {risky} risky"
    )
    for item in inspected:
        path = item.get("path")
        content = item.get("content")
        if path and content is not None:
            print_diff_preview(path, content)
    return inspected


def run_step(
    step: dict,
    client: Any,
    model: str,
    memory: Any,
    system_prompt: str,
    yolo: bool = False,
    journal: ChangeJournal | None = None,
    require_confirmation: bool = True,
    show_preview: bool = True,
) -> tuple[bool, str]:
    """Execute one step. Returns (success, output)."""
    stype = step.get("type", "ai_task")
    desc = step.get("description", "")
    base_dir = Path.cwd().resolve()

    if stype == "action":
        ok, reason = validate_action_step(step, base_dir)
        if not ok:
            return False, reason

        action = step.get("action", "")
        if action in FILE_MUTATION_ACTIONS:
            ok, _, path, content = compute_step_file_change(step, base_dir)
            if not ok or path is None or content is None:
                return False, "Could not prepare file change"
            if show_preview:
                print_diff_preview(path, content)
            if (require_confirmation and not yolo and (is_risky(step) or path.exists())):
                if not confirm(f"Run action: {CY}{action} {path}{R}"):
                    return False, "Skipped by user"
            if journal:
                journal.record_file(path)
            return execute_action_step(step, base_dir)

        if action in DIR_MUTATION_ACTIONS:
            path = _resolve_agent_path(step.get("target", ""), base_dir)
            if require_confirmation and not yolo and is_risky(step):
                if not confirm(f"Run action: {CY}{action} {path}{R}"):
                    return False, "Skipped by user"
            if journal:
                journal.record_dir(path)
            return execute_action_step(step, base_dir)

        if require_confirmation and not yolo and is_risky(step):
            target = step.get("target") or step.get("path", "")
            if not confirm(f"Run action: {CY}{action} {target}{R}"):
                return False, "Skipped by user"
        return execute_action_step(step, base_dir)

    if stype == "shell":
        return False, "Legacy shell steps are disabled in agent mode; use structured actions"

    if stype == "file_write":
        ok, _, path, content = compute_step_file_change(step, base_dir)
        if not ok or path is None or content is None:
            return False, "Could not prepare file write"
        if show_preview:
            print_diff_preview(path, content)
        if (require_confirmation and not yolo and (is_risky(step) or path.exists())):
            if not confirm(f"Write file: {CY}{path}{R}"):
                return False, "Skipped by user"
        if journal:
            journal.record_file(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True, f"Written: {path}"

    if stype == "ai_task":
        prompt = step.get("prompt", desc)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *memory.get(),
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.7,
                stream=False,
            )
            answer = resp.choices[0].message.content.strip()
            memory.add("user", prompt)
            memory.add("assistant", answer)
            return True, answer
        except Exception as exc:
            return False, str(exc)

    if stype == "ask_user":
        question = step.get("question", desc)
        try:
            answer = input(f"  {PU}›{R}  {question}  ").strip()
            return True, answer
        except (KeyboardInterrupt, EOFError):
            return False, "User cancelled"

    return False, f"Unknown step type: {stype}"


def run_agent(task: str, client: Any, model: str, memory: Any, system_prompt: str, yolo: bool = False) -> str:
    """Full agent loop: grounded plan → grouped approval → execute → optional rollback."""
    from src.utils.markdown import render as md_render

    base_dir = Path.cwd().resolve()
    journal = ChangeJournal()

    print(f"\n  {PU}agent{R}  {DG}planning...{R}\n")

    try:
        steps = make_plan(task, client, model, base_dir=base_dir)
    except RuntimeError as exc:
        return str(exc)

    if not steps:
        return "No steps generated."

    print(f"  {B}{WH}Plan  ({len(steps)} steps){R}\n")
    for step in steps:
        risky_badge = f"  {YE}risky{R}" if is_risky(step) else ""
        stype = step.get("type", "?")
        type_col = {"action": CY, "file_write": GN, "ai_task": PU, "ask_user": YE}.get(stype, GR)
        print(f"  {DG}{step['id']}.{R}  {type_col}[{stype}]{R}  {step['description']}{risky_badge}")
    print()

    inspected = _render_grouped_summary(steps, base_dir)
    invalid = [item for item in inspected if item.get("ok") is False]
    if invalid:
        reason = invalid[0].get("reason", "Plan preflight failed")
        return f"Plan rejected during preflight: {reason}"

    print()
    if not yolo and not confirm(f"Execute {len(steps)} preflighted steps?"):
        return "Agent cancelled."

    results = []
    rollback_note = ""
    stopped = False

    for step in steps:
        stype = step.get("type", "?")
        type_col = {"action": CY, "file_write": GN, "ai_task": PU, "ask_user": YE}.get(stype, GR)
        print(f"\n  {DG}step {step['id']}/{len(steps)}{R}  {type_col}{step['description']}{R}")

        success, output = run_step(
            step,
            client,
            model,
            memory,
            system_prompt,
            yolo=yolo,
            journal=journal,
            require_confirmation=False,
            show_preview=False,
        )

        if success:
            print(f"  {GN}✓{R}  ", end="")
            if output and len(output) < 300:
                print(output)
            elif output:
                print()
                for line in md_render(output[:800]).split("\n"):
                    print(f"  {GR}{line}{R}")
        else:
            print(f"  {RE}✗{R}  {output}")
            stopped = True

        results.append({"step": step["description"], "success": success, "output": output[:200]})

        if stopped:
            break

    if stopped and journal.has_changes() and not yolo:
        if confirm("Rollback changes from this run?"):
            rolled_back = journal.rollback()
            rollback_note = f" Rolled back {len(rolled_back)} change(s)."
            print(f"\n  {YE}↺{R}  rollback completed{R}")

    done = sum(1 for result in results if result["success"])
    failed = len(results) - done
    summary = f"Agent completed {done}/{len(steps)} steps"
    if failed:
        summary += f" ({failed} failed, stopped early)"
    if rollback_note:
        summary += rollback_note

    print(f"\n  {GN if not failed else YE}{'✓' if not failed else '▲'}{R}  {summary}\n")
    return summary
