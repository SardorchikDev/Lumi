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
import tempfile
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path
from typing import Any

import yaml

from src.agents.task_memory import (
    clear_active_run,
    record_run,
    render_task_memory_context,
    start_active_run,
    update_active_run,
)

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
MAX_SAFE_STEPS = 12
MAX_SAFE_FILE_CHANGES = 8
MAX_SAFE_COMMANDS = 5
MAX_RECOVERY_STEPS = 3

SAFE_ACTIONS = {
    "list_dir",
    "read_file",
    "inspect_repo",
    "run_tests",
    "run_ruff",
    "run_mypy",
    "run_verify",
    "git_status",
    "git_diff",
    "inspect_changed_files",
    "mkdir",
    "rename_path",
    "write_json",
    "write_yaml",
    "search_code",
    "search_symbols",
    "patch_file",
    "patch_lines",
    "patch_context",
    "patch_apply",
}
READ_ACTIONS = {"list_dir", "read_file", "search_code", "search_symbols", "git_status", "git_diff", "inspect_repo", "inspect_changed_files"}
VERIFY_ACTIONS = {"run_tests", "run_ruff", "run_mypy", "run_verify"}
FILE_MUTATION_ACTIONS = {"write_json", "write_yaml", "patch_file", "patch_lines", "patch_context", "patch_apply"}
DIR_MUTATION_ACTIONS = {"mkdir", "rename_path"}

ACTION_HINTS = (
    ("inspect repo", "inspect_repo"),
    ("repo map", "inspect_repo"),
    ("git status", "git_status"),
    ("status of repo", "git_status"),
    ("git diff", "git_diff"),
    ("diff", "git_diff"),
    ("changed files", "inspect_changed_files"),
    ("run tests", "run_tests"),
    ("run pytest", "run_tests"),
    ("pytest", "run_tests"),
    ("verify repo", "run_verify"),
    ("run verification", "run_verify"),
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
    ("rename file", "rename_path"),
    ("move file", "rename_path"),
    ("write json", "write_json"),
    ("json file", "write_json"),
    ("json config", "write_json"),
    ("write yaml", "write_yaml"),
    ("yaml file", "write_yaml"),
    ("search code", "search_code"),
    ("search the codebase", "search_code"),
    ("find usages", "search_code"),
    ("find references", "search_code"),
    ("search symbols", "search_symbols"),
    ("find symbol", "search_symbols"),
    ("patch file", "patch_file"),
    ("edit file", "patch_file"),
    ("update file", "patch_file"),
    ("replace text", "patch_file"),
    ("replace lines", "patch_lines"),
    ("update lines", "patch_lines"),
    ("replace block", "patch_context"),
    ("patch context", "patch_context"),
    ("apply patch", "patch_apply"),
    ("multi patch", "patch_apply"),
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
  "action": "list_dir" | "read_file" | "inspect_repo" | "run_tests" | "run_ruff" | "run_mypy" | "run_verify" | "git_status" | "git_diff" | "inspect_changed_files" | "mkdir" | "rename_path" | "write_json" | "write_yaml" | "search_code" | "search_symbols" | "patch_file" | "patch_lines" | "patch_context" | "patch_apply",
  "target": "relative path used by many actions",
  "path": "file path for file_write / write_json / patch actions",
  "destination": "new path for rename_path",
  "content": "full file content for file_write",
  "query": "literal search text for search_code",
  "symbol": "symbol to search for",
  "symbol_kind": "optional filter like function | class | test",
  "verify_kind": "tests | lint | types | all",
  "json_content": {"key": "value"},
  "yaml_content": {"key": "value"},
  "old_text": "exact text to replace in patch_file",
  "new_text": "replacement text for patch_file",
  "replace_all": false,
  "start_line": 10,
  "end_line": 14,
  "old_block": "expected current block for patch_lines",
  "replacement": "replacement block for patch_lines",
  "before_context": "stable text immediately before the block to replace",
  "after_context": "stable text immediately after the block to replace",
  "hunks": [{"old_text": "foo", "new_text": "bar"}],
  "prompt": "prompt for ai_task",
  "question": "question for ask_user",
  "risky": true | false
}

Rules:
- Ground the plan in the workspace context provided to you.
- Use the repo profile and recent task memory provided to you.
- Prefer actions to inspect the repo before reasoning.
- Prefer inspect_repo early if the task is broad or the repo shape matters.
- Prefer run_verify over guessing which check command the repo uses.
- Prefer file_write for new files or full rewrites.
- Prefer patch_context when you can anchor an edit with surrounding context.
- Prefer patch_file or patch_lines for editing existing files when the match is exact.
- Prefer patch_apply for multiple related edits in the same file.
- Prefer write_json for JSON config changes.
- Prefer write_yaml for YAML config changes.
- Prefer search_symbols for finding definitions and tests.
- Prefer inspect_changed_files when git state matters.
- Prefer mkdir before writing nested files into new directories.
- Prefer run_tests, run_ruff, run_mypy, and run_verify for verification when relevant.
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


@dataclass(frozen=True)
class RepoProfile:
    base_dir: Path
    package_manager: str | None
    frameworks: tuple[str, ...]
    entrypoints: tuple[str, ...]
    config_files: tuple[str, ...]
    relevant_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    verification_commands: dict[str, tuple[str, ...]]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionPolicy:
    max_steps: int = MAX_SAFE_STEPS
    max_file_changes: int = MAX_SAFE_FILE_CHANGES
    max_command_actions: int = MAX_SAFE_COMMANDS
    max_recovery_attempts: int = 1
    review_only: bool = False


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


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _normalize_filesystem_name(value: str) -> str:
    cleaned = _strip_wrapping_quotes(value.strip().rstrip(".,;:"))
    cleaned = re.sub(r"^(?:the\s+)?(?:folder|directory|file)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:named|called)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _looks_like_filesystem_scaffold_task(task: str) -> bool:
    lowered = task.lower()
    if not re.search(r"\b(?:create|make|add)\b", lowered):
        return False
    if not re.search(r"\b(?:folder|directory|file)\b", lowered):
        return False
    blocked = (
        "fix ",
        "patch ",
        "update ",
        "modify ",
        "edit ",
        "refactor ",
        "debug ",
        "search ",
        "read ",
        "inspect ",
        "run tests",
        "run ruff",
        "run mypy",
        "verify ",
    )
    return not any(token in lowered for token in blocked)


def _split_filesystem_clauses(task: str) -> list[str]:
    text = re.sub(r"\s+", " ", task.replace("\n", " ")).strip()
    if not text:
        return []
    text = re.sub(
        r"(?<!^)\s+(?=(?:create|make|add)\s+(?:a|an)?\s*(?:new\s+)?(?:file|folder|directory)\b)",
        " | ",
        text,
        flags=re.IGNORECASE,
    )
    parts = re.split(
        r"\s*(?:\||,|;|\bthen\b|\band then\b|\band\b(?=\s+(?:create|make|add|inside|in|under)\b))\s*",
        text,
        flags=re.IGNORECASE,
    )
    return [part.strip() for part in parts if part.strip()]


def _extract_named_object(clause: str, kind_words: str) -> str:
    token_pattern = r'"[^"]+"|\'[^\']+\'|[A-Za-z0-9][A-Za-z0-9._/-]*'
    patterns = (
        rf"\b(?:create|make|add)\s+(?:a|an)?\s*(?:new\s+)?(?:{kind_words})\s+(?:named|called)\s*(?P<name>{token_pattern})",
        rf"\b(?:create|make|add)\s+(?:a|an)?\s*(?:new\s+)?(?:{kind_words})\s+(?P<name>{token_pattern})(?=$|\s+(?:inside|in|under)\b)",
        rf"\b(?:create|make|add)\s+(?:a|an)?\s*(?:new\s+)?(?:{kind_words})\b.*?\b(?:named|called)\s*(?P<name>{token_pattern})",
    )
    for pattern in patterns:
        match = re.search(pattern, clause, flags=re.IGNORECASE)
        if match:
            return _normalize_filesystem_name(match.group("name"))
    return ""


def _extract_location_reference(clause: str, last_dir: Path | None) -> tuple[bool, Path | None]:
    match = re.search(
        r"\b(?:inside|in|under)\s+(?P<loc>that folder|that directory|it|there|(?:the\s+)?(?:folder|directory)\s+(?:named|called)\s+(?:\"[^\"]+\"|'[^']+'|[A-Za-z0-9][A-Za-z0-9._/-]*)|(?:\"[^\"]+\"|'[^']+'|[A-Za-z0-9][A-Za-z0-9._/-]*))",
        clause,
        flags=re.IGNORECASE,
    )
    if not match:
        return False, None
    raw = _normalize_filesystem_name(match.group("loc"))
    if raw.lower() in {"that folder", "that directory", "it", "there"}:
        return True, last_dir
    return True, Path(raw) if raw else None


def _append_missing_dir_steps(path: Path, *, steps: list[dict], planned_dirs: set[str], base_dir: Path) -> None:
    current = Path()
    for part in path.parts:
        current /= part
        rel_path = current.as_posix()
        if rel_path in {"", "."}:
            continue
        if rel_path in planned_dirs or (base_dir / current).exists():
            continue
        steps.append(
            {
                "id": len(steps) + 1,
                "type": "action",
                "action": "mkdir",
                "target": rel_path,
                "description": f"Create folder {rel_path}",
                "risky": False,
            }
        )
        planned_dirs.add(rel_path)


def _build_filesystem_scaffold_plan(task: str, base_dir: Path) -> list[dict] | None:
    if not _looks_like_filesystem_scaffold_task(task):
        return None

    steps: list[dict] = []
    planned_dirs: set[str] = set()
    last_dir: Path | None = None
    parsed_any = False

    for raw_clause in _split_filesystem_clauses(task):
        clause = re.sub(
            r"^(?:please|pls|can you|could you|would you|lumi|hey lumi|bro|hey|yo)\s+",
            "",
            raw_clause.strip(),
            flags=re.IGNORECASE,
        )
        if not clause:
            continue

        has_action = bool(re.search(r"\b(?:create|make|add)\b", clause, flags=re.IGNORECASE))
        folder_name = _extract_named_object(clause, "folder|directory")
        file_name = _extract_named_object(clause, "file")
        location_mentioned, location = _extract_location_reference(clause, last_dir)

        if folder_name and file_name:
            return None
        if location_mentioned and location is None:
            return None

        if folder_name:
            parsed_any = True
            full_path = (location / folder_name) if location is not None else Path(folder_name)
            if full_path == Path("."):
                return None
            _append_missing_dir_steps(full_path, steps=steps, planned_dirs=planned_dirs, base_dir=base_dir)
            last_dir = full_path
            continue

        if file_name:
            parsed_any = True
            full_path = (location / file_name) if location is not None else Path(file_name)
            parent = full_path.parent
            if str(parent) not in {"", "."}:
                _append_missing_dir_steps(parent, steps=steps, planned_dirs=planned_dirs, base_dir=base_dir)
                last_dir = parent
            steps.append(
                {
                    "id": len(steps) + 1,
                    "type": "file_write",
                    "path": full_path.as_posix(),
                    "content": "",
                    "description": f"Create file {full_path.as_posix()}",
                    "risky": False,
                }
            )
            continue

        if has_action:
            return None

    return steps if parsed_any else None


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


def _command_available(cmd: str) -> bool:
    return bool(shutil.which(cmd))


def _detect_package_manager(base_dir: Path) -> str | None:
    if (base_dir / "pnpm-lock.yaml").exists() and _command_available("pnpm"):
        return "pnpm"
    if (base_dir / "yarn.lock").exists() and _command_available("yarn"):
        return "yarn"
    if (base_dir / "bun.lockb").exists() and _command_available("bun"):
        return "bun"
    if (base_dir / "package-lock.json").exists() and _command_available("npm"):
        return "npm"
    if (base_dir / "package.json").exists():
        for candidate in ("pnpm", "yarn", "bun", "npm"):
            if _command_available(candidate):
                return candidate
    return None


def _load_package_scripts(base_dir: Path) -> dict[str, str]:
    package_json = base_dir / "package.json"
    if not package_json.exists():
        return {}
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = data.get("scripts", {})
    if not isinstance(scripts, dict):
        return {}
    return {
        key: value
        for key, value in scripts.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _has_test_targets(base_dir: Path) -> bool:
    tests_dir = base_dir / "tests"
    if tests_dir.exists():
        for path in tests_dir.rglob("*"):
            if path.is_file() and path.name.startswith("test"):
                return True
    return any(base_dir.glob("test_*.py"))


def _detect_verification_commands(base_dir: Path) -> dict[str, tuple[str, ...]]:
    commands: dict[str, tuple[str, ...]] = {}
    scripts = _load_package_scripts(base_dir)
    package_manager = _detect_package_manager(base_dir)

    if _has_test_targets(base_dir):
        commands["tests"] = (sys.executable, "-m", "pytest")
    if (base_dir / "pyproject.toml").exists() and _command_available(sys.executable):
        pyproject_text = (base_dir / "pyproject.toml").read_text(encoding="utf-8", errors="replace").lower()
        if "[tool.ruff" in pyproject_text or "ruff" in pyproject_text:
            commands["lint"] = (sys.executable, "-m", "ruff", "check", ".")
        if "mypy" in pyproject_text:
            commands["types"] = (sys.executable, "-m", "mypy", ".")

    if package_manager and scripts:
        if "test" in scripts:
            commands["tests"] = (package_manager, "test")
        elif "check" in scripts:
            commands.setdefault("tests", (package_manager, "run", "check"))
        if "lint" in scripts:
            commands["lint"] = (package_manager, "run", "lint")
        if "typecheck" in scripts:
            commands["types"] = (package_manager, "run", "typecheck")
        elif "types" in scripts:
            commands["types"] = (package_manager, "run", "types")

    if (base_dir / "Cargo.toml").exists() and _command_available("cargo"):
        commands.setdefault("tests", ("cargo", "test"))
        commands.setdefault("lint", ("cargo", "fmt", "--", "--check"))
        commands.setdefault("types", ("cargo", "check"))

    if (base_dir / "go.mod").exists() and _command_available("go"):
        commands.setdefault("tests", ("go", "test", "./..."))
        commands.setdefault("types", ("go", "test", "./..."))

    if not commands and (base_dir / "pyproject.toml").exists():
        commands["tests"] = (sys.executable, "-m", "pytest")

    return commands


def _detect_entrypoints(base_dir: Path) -> tuple[str, ...]:
    candidates = (
        "main.py",
        "app.py",
        "manage.py",
        "src/main.py",
        "src/app.py",
        "package.json",
        "Cargo.toml",
        "go.mod",
    )
    found = [candidate for candidate in candidates if (base_dir / candidate).exists()]
    return tuple(found[:6])


def _detect_frameworks(base_dir: Path) -> tuple[str, ...]:
    found: list[str] = []
    pyproject = (base_dir / "pyproject.toml").read_text(encoding="utf-8", errors="replace").lower() if (base_dir / "pyproject.toml").exists() else ""
    requirements = (base_dir / "requirements.txt").read_text(encoding="utf-8", errors="replace").lower() if (base_dir / "requirements.txt").exists() else ""
    package_json = (base_dir / "package.json").read_text(encoding="utf-8", errors="replace").lower() if (base_dir / "package.json").exists() else ""
    cargo = (base_dir / "Cargo.toml").read_text(encoding="utf-8", errors="replace").lower() if (base_dir / "Cargo.toml").exists() else ""

    def has_token(*tokens: str) -> bool:
        haystacks = (pyproject, requirements, package_json, cargo)
        return any(token in haystack for haystack in haystacks for token in tokens)

    framework_rules = (
        ("fastapi", ("fastapi",)),
        ("django", ("django",)),
        ("flask", ("flask",)),
        ("pytest", ("pytest",)),
        ("react", ('"react"', '"next"', '"vite"', "react-dom")),
        ("vue", ('"vue"', "nuxt")),
        ("svelte", ('"svelte"',)),
        ("node", ('"express"', '"nestjs"', '"koa"', '"hono"')),
        ("rust", ("[package]", "tokio", "axum", "actix")),
        ("go", ("module ",)),
    )
    for label, tokens in framework_rules:
        if has_token(*tokens):
            found.append(label)
    return tuple(found[:6])


def _detect_config_files(base_dir: Path) -> tuple[str, ...]:
    candidates = (
        ".env.example",
        ".env",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "tsconfig.json",
        "Cargo.toml",
        "go.mod",
        "ruff.toml",
        "mypy.ini",
        ".github/workflows",
    )
    found: list[str] = []
    for candidate in candidates:
        path = base_dir / candidate
        if path.exists():
            found.append(candidate)
    return tuple(found[:8])


def inspect_repo(base_dir: Path | None = None, task: str = "") -> RepoProfile:
    base_dir = (base_dir or Path.cwd()).resolve()
    relevant_paths = tuple(str(path.relative_to(base_dir)) for path in _search_relevant_paths(base_dir, task))
    git_ok, git_status = _run_command(["git", "status", "--short"], base_dir, timeout=15)
    changed_files: list[str] = []
    notes: list[str] = []
    if git_ok:
        for line in git_status.splitlines():
            trimmed = line.strip()
            if not trimmed:
                continue
            path_text = trimmed[3:] if len(trimmed) > 3 else trimmed
            changed_files.append(path_text)
    elif "not a git repository" not in git_status.lower():
        notes.append("git status unavailable")

    verification = _detect_verification_commands(base_dir)
    if not verification:
        notes.append("no verification commands detected")

    return RepoProfile(
        base_dir=base_dir,
        package_manager=_detect_package_manager(base_dir),
        frameworks=_detect_frameworks(base_dir),
        entrypoints=_detect_entrypoints(base_dir),
        config_files=_detect_config_files(base_dir),
        relevant_files=relevant_paths,
        changed_files=tuple(changed_files[:12]),
        verification_commands=verification,
        notes=tuple(notes),
    )


def collect_planning_context(task: str, base_dir: Path | None = None) -> str:
    """Gather lightweight repo facts before asking the model to plan."""
    base_dir = (base_dir or Path.cwd()).resolve()
    profile = inspect_repo(base_dir, task)
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

    if profile.entrypoints:
        lines.append("Likely entrypoints:")
        for entry in profile.entrypoints:
            lines.append(f"- {entry}")
        lines.append("")

    if profile.frameworks:
        lines.append("Detected frameworks and tools:")
        for framework in profile.frameworks:
            lines.append(f"- {framework}")
        lines.append("")

    if profile.config_files:
        lines.append("Key config files:")
        for config_path in profile.config_files:
            lines.append(f"- {config_path}")
        lines.append("")

    if profile.package_manager:
        lines.append(f"Detected package manager: {profile.package_manager}")
        lines.append("")

    if profile.relevant_files:
        lines.append("Likely relevant files:")
        for rel_path in profile.relevant_files:
            lines.append(f"- {rel_path}")
        lines.append("")

    if profile.changed_files:
        lines.append("Changed files:")
        for rel_path in profile.changed_files:
            lines.append(f"- {rel_path}")
        lines.append("")

    if profile.verification_commands:
        lines.append("Verification commands detected:")
        for kind, command in sorted(profile.verification_commands.items()):
            lines.append(f"- {kind}: {' '.join(command)}")
        lines.append("")

    task_memory = render_task_memory_context(task)
    if task_memory:
        lines.append(task_memory)
        lines.append("")

    git_ok, git_status = _run_command(["git", "status", "--short"], base_dir, timeout=15)
    if git_ok or "not a git repository" not in git_status.lower():
        lines.append("Git status:")
        lines.append(git_status or "(clean)")

    return "\n".join(lines).strip()


def _default_execution_policy(task: str) -> ExecutionPolicy:
    lower = task.lower()
    review_only = any(phrase in lower for phrase in ("review only", "dry run", "plan only", "preview only"))
    return ExecutionPolicy(review_only=review_only)


def _verification_steps_for_profile(profile: RepoProfile, start_id: int) -> list[dict]:
    steps: list[dict] = []
    wanted: list[str] = []
    if "tests" in profile.verification_commands:
        wanted.append("tests")
    if "lint" in profile.verification_commands:
        wanted.append("lint")
    if "types" in profile.verification_commands:
        wanted.append("types")
    for offset, kind in enumerate(wanted[:3], start=0):
        steps.append(
            {
                "id": start_id + offset,
                "description": f"Verify the workspace after changes ({kind})",
                "type": "action",
                "action": "run_verify",
                "verify_kind": kind,
                "target": ".",
                "risky": False,
            }
        )
    return steps


def _append_verification_step(steps: list[dict], base_dir: Path, task: str = "") -> list[dict]:
    scaffold_only = _looks_like_filesystem_scaffold_task(task) and all(
        step.get("type") == "file_write"
        or (step.get("type") == "action" and step.get("action") == "mkdir")
        for step in steps
    )
    if scaffold_only:
        return steps

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

    profile = inspect_repo(base_dir)
    verify_steps = _verification_steps_for_profile(profile, len(steps) + 1)
    return steps + verify_steps if verify_steps else steps


def _enforce_execution_policy(steps: list[dict], policy: ExecutionPolicy, base_dir: Path) -> tuple[bool, str]:
    if len(steps) > policy.max_steps:
        return False, f"Plan exceeds step budget ({len(steps)} > {policy.max_steps})"
    file_changes = 0
    command_actions = 0
    for step in steps:
        if step.get("type") == "file_write":
            file_changes += 1
        if step.get("type") == "action":
            action = step.get("action")
            if action in FILE_MUTATION_ACTIONS | DIR_MUTATION_ACTIONS:
                file_changes += 1
            if action in VERIFY_ACTIONS | {"git_status", "git_diff", "inspect_changed_files"}:
                command_actions += 1
    if file_changes > policy.max_file_changes:
        return False, f"Plan exceeds file-change budget ({file_changes} > {policy.max_file_changes})"
    if command_actions > policy.max_command_actions:
        return False, f"Plan exceeds command budget ({command_actions} > {policy.max_command_actions})"
    return True, ""


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
            if action == "rename_path":
                step["target"] = str(step.get("target") or step.get("path") or "").strip()
                step["destination"] = str(step.get("destination", "")).strip()
                if not step["target"] or not step["destination"]:
                    raise ValueError(f"Step {index} rename_path requires target and destination")
            if action == "write_json":
                if not str(step.get("path", "")).strip():
                    raise ValueError(f"Step {index} write_json is missing a file path")
                if "json_content" not in step:
                    raise ValueError(f"Step {index} write_json is missing json_content")
            if action == "write_yaml":
                if not str(step.get("path", "")).strip():
                    raise ValueError(f"Step {index} write_yaml is missing a file path")
                if "yaml_content" not in step:
                    raise ValueError(f"Step {index} write_yaml is missing yaml_content")
            if action == "search_code" and not str(step.get("query", "")).strip():
                raise ValueError(f"Step {index} search_code is missing a query")
            if action == "search_symbols" and not str(step.get("symbol", "")).strip():
                raise ValueError(f"Step {index} search_symbols is missing a symbol")
            if action == "run_verify" and str(step.get("verify_kind", "")).strip() not in {"tests", "lint", "types", "all"}:
                raise ValueError(f"Step {index} run_verify requires verify_kind")
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
            if action == "patch_context":
                if not str(step.get("path", "")).strip():
                    raise ValueError(f"Step {index} patch_context is missing a file path")
                if not str(step.get("before_context", "")).strip() and not str(step.get("after_context", "")).strip():
                    raise ValueError(f"Step {index} patch_context needs before_context or after_context")
                if "replacement" not in step:
                    raise ValueError(f"Step {index} patch_context is missing replacement")
            if action == "patch_apply":
                if not str(step.get("path", "")).strip():
                    raise ValueError(f"Step {index} patch_apply is missing a file path")
                hunks = step.get("hunks")
                if not isinstance(hunks, list) or not hunks:
                    raise ValueError(f"Step {index} patch_apply requires hunks")

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


def make_plan(
    task: str,
    client: Any,
    model: str,
    base_dir: Path | None = None,
    policy: ExecutionPolicy | None = None,
) -> list[dict]:
    """Ask AI to break task into grounded, normalized steps."""
    base_dir = (base_dir or Path.cwd()).resolve()
    policy = policy or _default_execution_policy(task)
    scaffold_steps = _build_filesystem_scaffold_plan(task, base_dir)
    if scaffold_steps:
        ok, reason = _enforce_execution_policy(scaffold_steps, policy, base_dir)
        if not ok:
            raise RuntimeError(reason)
        return scaffold_steps

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
        normalized = _append_verification_step(normalized, base_dir, task)
        ok, reason = _enforce_execution_policy(normalized, policy, base_dir)
        if not ok:
            raise RuntimeError(reason)
        for index, step in enumerate(normalized, start=1):
            step["id"] = index
        return normalized
    except Exception as exc:
        raise RuntimeError(f"Could not generate plan: {exc}") from exc


def make_recovery_plan(
    task: str,
    failed_step: dict,
    failure_output: str,
    client: Any,
    model: str,
    base_dir: Path,
    policy: ExecutionPolicy,
) -> list[dict]:
    """Ask AI for a bounded recovery plan after a step fails."""
    workspace_context = collect_planning_context(task, base_dir)
    failure_context = (
        f"Original objective:\n{task}\n\n"
        f"Failed step:\n{json.dumps(failed_step, indent=2, ensure_ascii=False)}\n\n"
        f"Failure output:\n{failure_output[:1200]}\n\n"
        "Return a JSON array of up to 3 recovery steps that could fix or diagnose the failure. "
        "Prefer structured actions and safe file patches. Do not repeat the failed verification command unless a fix step comes first."
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                {"role": "user", "content": f"{failure_context}\n\nWorkspace context:\n{workspace_context}"},
            ],
            max_tokens=1200,
            temperature=0.2,
            stream=False,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
        normalized = normalize_plan(json.loads(raw))
        if len(normalized) > MAX_RECOVERY_STEPS:
            normalized = normalized[:MAX_RECOVERY_STEPS]
        ok, reason = _enforce_execution_policy(normalized, policy, base_dir)
        if not ok:
            raise RuntimeError(reason)
        for index, step in enumerate(normalized, start=1):
            step["id"] = index
        return normalized
    except Exception as exc:
        raise RuntimeError(f"Could not generate recovery plan: {exc}") from exc


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


def _compute_patch_context_update(step: dict, path: Path) -> tuple[bool, str]:
    before_context = str(step.get("before_context", ""))
    after_context = str(step.get("after_context", ""))
    old_block = step.get("old_block")
    replacement = str(step.get("replacement", ""))

    if not before_context and not after_context:
        return False, "Blocked: patch_context requires before_context or after_context"
    if old_block is None and not (before_context and after_context):
        return False, "Blocked: patch_context requires old_block when only one context anchor is provided"

    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)

    matches: list[tuple[int, int]] = []
    expected = str(old_block) if old_block is not None else None

    if before_context and after_context:
        search_from = 0
        while True:
            before_index = current.find(before_context, search_from)
            if before_index == -1:
                break
            start = before_index + len(before_context)
            end = current.find(after_context, start)
            if end != -1:
                matches.append((start, end))
            search_from = before_index + 1
    elif before_context:
        token = before_context + expected
        search_from = 0
        while True:
            match_index = current.find(token, search_from)
            if match_index == -1:
                break
            start = match_index + len(before_context)
            end = start + len(expected)
            matches.append((start, end))
            search_from = match_index + 1
    else:
        token = expected + after_context
        search_from = 0
        while True:
            match_index = current.find(token, search_from)
            if match_index == -1:
                break
            start = match_index
            end = start + len(expected)
            matches.append((start, end))
            search_from = match_index + 1

    if not matches:
        return False, "Blocked: patch_context could not find a matching anchored block"
    if len(matches) > 1:
        return False, "Blocked: patch_context matched multiple regions"

    start, end = matches[0]
    current_block = current[start:end]
    if expected is not None and current_block != expected:
        return False, "Blocked: patch_context old_block does not match the current file"
    if replacement and not replacement.endswith(("\n", "\r")) and current_block.endswith("\n"):
        replacement += "\n"
    updated = current[:start] + replacement + current[end:]
    return True, updated


def _compute_patch_apply_update(step: dict, path: Path) -> tuple[bool, str]:
    hunks = step.get("hunks", [])
    if not isinstance(hunks, list) or not hunks:
        return False, "Blocked: patch_apply requires a non-empty hunks list"
    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)

    updated = current
    for index, raw_hunk in enumerate(hunks, start=1):
        if not isinstance(raw_hunk, dict):
            return False, f"Blocked: patch_apply hunk {index} is not an object"
        temp_step = dict(raw_hunk)
        temp_step.setdefault("path", str(path))
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write(updated)
            temp_path = Path(handle.name)
        try:
            if "old_text" in temp_step:
                ok, updated = _compute_patch_file_update(temp_step, temp_path)
            elif temp_step.get("start_line") is not None or temp_step.get("end_line") is not None:
                ok, updated = _compute_patch_lines_update(temp_step, temp_path)
            elif temp_step.get("before_context") or temp_step.get("after_context"):
                ok, updated = _compute_patch_context_update(temp_step, temp_path)
            else:
                return False, f"Blocked: patch_apply hunk {index} has no supported patch shape"
        finally:
            temp_path.unlink(missing_ok=True)
        if not ok:
            return False, f"Blocked: patch_apply hunk {index} failed: {updated}"
        if updated == current:
            return False, f"Blocked: patch_apply hunk {index} made no changes"
        current = updated
    return True, updated


def _detect_symbol_pattern(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return r"^\s*(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"
    if suffix in {".js", ".ts", ".jsx", ".tsx"}:
        return r"^\s*(export\s+)?(async\s+)?(function|class|const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)"
    if suffix == ".go":
        return r"^\s*func\s+([A-Za-z_][A-Za-z0-9_]*)"
    if suffix == ".rs":
        return r"^\s*(pub\s+)?(fn|struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)"
    return ""


def _search_symbols(base_dir: Path, target: Path, symbol: str, symbol_kind: str = "") -> str:
    matches: list[str] = []
    for path in sorted(target.rglob("*")) if target.is_dir() else [target]:
        if not path.is_file():
            continue
        pattern = _detect_symbol_pattern(path)
        if not pattern:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        regex = re.compile(pattern)
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = regex.search(line)
            if not match:
                continue
            groups = match.groups()
            name = next((group for group in reversed(groups) if group and re.match(r"[A-Za-z_$]", group)), "")
            kind = next((group for group in groups if group in {"def", "class", "function", "const", "let", "var", "fn", "struct", "enum", "trait"}), "")
            if symbol and symbol.lower() not in name.lower():
                continue
            if symbol_kind and kind and symbol_kind.lower() != kind.lower():
                continue
            matches.append(f"{path.relative_to(base_dir)}:{lineno}: {kind or 'symbol'} {name}".strip())
            if len(matches) >= 50:
                return "\n".join(matches) + "\n... symbol search truncated ..."
    return "\n".join(matches) if matches else "(no symbols found)"


def _run_verification_command(command: tuple[str, ...], base_dir: Path, timeout: int = 90) -> tuple[bool, str]:
    ok, output = _run_command(list(command), base_dir, timeout=timeout)
    return ok, _summarize_verification_output(command, output)


def _summarize_verification_output(command: tuple[str, ...], output: str) -> str:
    lowered = output.lower()
    summary_bits = [" ".join(command)]
    match = re.search(r"(\d+)\s+passed", lowered)
    if match:
        summary_bits.append(f"{match.group(1)} passed")
    match = re.search(r"(\d+)\s+failed", lowered)
    if match:
        summary_bits.append(f"{match.group(1)} failed")
    match = re.search(r"found\s+(\d+)\s+error", lowered)
    if match:
        summary_bits.append(f"{match.group(1)} errors")
    if "success" in lowered and len(summary_bits) == 1:
        summary_bits.append("success")
    preview = output[:600].rstrip()
    if preview:
        summary_bits.append(preview)
    return " | ".join(summary_bits)


def compute_step_file_change(step: dict, base_dir: Path) -> tuple[bool, str, Path | None, str | None]:
    """Return a pending file mutation as (ok, message, path, new_content)."""
    stype = step.get("type", "") or ("action" if step.get("action") else "")
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

    if action == "write_yaml":
        ok, reason = validate_file_write_path(step.get("path", ""), base_dir)
        if not ok:
            return False, reason, None, None
        path = _resolve_agent_path(step["path"], base_dir)
        try:
            content = yaml.safe_dump(step.get("yaml_content"), sort_keys=False, allow_unicode=True)
        except yaml.YAMLError as exc:
            return False, f"Invalid yaml_content: {exc}", None, None
        if not content.endswith("\n"):
            content += "\n"
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

    if action == "patch_context":
        ok, reason = validate_action_step(step, base_dir)
        if not ok:
            return False, reason, None, None
        path = _resolve_agent_path(step["path"], base_dir)
        ok, updated = _compute_patch_context_update(step, path)
        return ok, ("patch_context" if ok else updated), path, (updated if ok else None)

    if action == "patch_apply":
        ok, reason = validate_action_step(step, base_dir)
        if not ok:
            return False, reason, None, None
        path = _resolve_agent_path(step["path"], base_dir)
        ok, updated = _compute_patch_apply_update(step, path)
        return ok, ("patch_apply" if ok else updated), path, (updated if ok else None)

    return False, "Not a file mutation step", None, None


def validate_action_step(step: dict, base_dir: Path) -> tuple[bool, str]:
    action = step.get("action", "").strip()
    if action not in SAFE_ACTIONS:
        return False, f"Unsupported action in agent mode: {action or '(missing)'}"

    target_value = step.get("target", ".")
    if action in {"write_json", "write_yaml", "patch_file", "patch_lines", "patch_context", "patch_apply"}:
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

    if action == "inspect_repo":
        return True, ""

    if action == "read_file":
        if not resolved.is_file():
            return False, "Blocked: read_file target must be an existing file"
        return True, ""

    if action in {"run_tests", "run_ruff", "run_mypy", "git_diff", "inspect_changed_files"}:
        return True, ""

    if action == "run_verify":
        verify_kind = str(step.get("verify_kind", "")).strip()
        if verify_kind not in {"tests", "lint", "types", "all"}:
            return False, "Blocked: run_verify requires verify_kind of tests, lint, types, or all"
        profile = inspect_repo(base_dir)
        if verify_kind != "all" and verify_kind not in profile.verification_commands:
            return False, f"Blocked: repo does not expose a '{verify_kind}' verification command"
        if verify_kind == "all" and not profile.verification_commands:
            return False, "Blocked: repo does not expose verification commands"
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

    if action == "write_yaml":
        if resolved.exists() and not resolved.is_file():
            return False, "Blocked: write_yaml target must be a file path"
        try:
            yaml.safe_dump(step.get("yaml_content"), sort_keys=False, allow_unicode=True)
        except yaml.YAMLError as exc:
            return False, f"Invalid yaml_content: {exc}"
        return True, ""

    if action == "search_code":
        if not resolved.exists():
            return False, "Blocked: search_code target does not exist"
        if not str(step.get("query", "")).strip():
            return False, "Blocked: search_code requires a query"
        return True, ""

    if action == "search_symbols":
        if not resolved.exists():
            return False, "Blocked: search_symbols target does not exist"
        if not str(step.get("symbol", "")).strip():
            return False, "Blocked: search_symbols requires a symbol"
        return True, ""

    if action == "rename_path":
        destination = str(step.get("destination", "")).strip()
        if not destination:
            return False, "Blocked: rename_path requires a destination"
        ok, reason, destination_path = _resolve_action_target(destination, base_dir)
        if not ok:
            return False, reason
        if not resolved.exists():
            return False, "Blocked: rename_path target must exist"
        if destination_path.exists():
            return False, "Blocked: rename_path destination already exists"
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

    if action == "patch_context":
        if not resolved.is_file():
            return False, "Blocked: patch_context target must be an existing file"
        return _compute_patch_context_update(step, resolved)[:2]

    if action == "patch_apply":
        if not resolved.is_file():
            return False, "Blocked: patch_apply target must be an existing file"
        return _compute_patch_apply_update(step, resolved)[:2]

    return True, ""


def execute_action_step(step: dict, base_dir: Path) -> tuple[bool, str]:
    action = step.get("action", "").strip()
    target_value = step.get("target", ".")
    if action in {"write_json", "write_yaml", "patch_file", "patch_lines", "patch_context", "patch_apply"}:
        target_value = step.get("path", "")
    _, _, target = _resolve_action_target(target_value, base_dir)

    if action == "list_dir":
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for entry in entries[:200]:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.relative_to(base_dir)}{suffix}")
        return True, "\n".join(lines) if lines else "(empty directory)"

    if action == "inspect_repo":
        profile = inspect_repo(base_dir, step.get("description", ""))
        lines = [
            f"workspace: {profile.base_dir}",
            f"package manager: {profile.package_manager or '(none)'}",
            "entrypoints: " + (", ".join(profile.entrypoints) if profile.entrypoints else "(none)"),
            "changed files: " + (", ".join(profile.changed_files) if profile.changed_files else "(clean)"),
            "verification: " + (
                ", ".join(f"{kind}={' '.join(command)}" for kind, command in sorted(profile.verification_commands.items()))
                if profile.verification_commands else "(none)"
            ),
        ]
        if profile.relevant_files:
            lines.append("relevant: " + ", ".join(profile.relevant_files))
        return True, "\n".join(lines)

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
        ok, output = _run_command(cmd, base_dir, timeout=60)
        return ok, _summarize_verification_output(tuple(cmd), output)

    if action == "run_ruff":
        if not shutil.which("ruff"):
            return False, "ruff is not installed"
        cmd = ["ruff", "check"]
        cmd.append(str(target.relative_to(base_dir)) if target != base_dir else ".")
        ok, output = _run_command(cmd, base_dir, timeout=60)
        return ok, _summarize_verification_output(tuple(cmd), output)

    if action == "run_mypy":
        if not shutil.which("mypy"):
            return False, "mypy is not installed"
        cmd = ["mypy"]
        cmd.append(str(target.relative_to(base_dir)) if target != base_dir else ".")
        ok, output = _run_command(cmd, base_dir, timeout=90)
        return ok, _summarize_verification_output(tuple(cmd), output)

    if action == "run_verify":
        profile = inspect_repo(base_dir)
        verify_kind = str(step.get("verify_kind", "all")).strip()
        kinds = [verify_kind] if verify_kind != "all" else [kind for kind in ("tests", "lint", "types") if kind in profile.verification_commands]
        outputs: list[str] = []
        overall_ok = True
        for kind in kinds:
            command = profile.verification_commands.get(kind)
            if not command:
                continue
            ok, output = _run_verification_command(command, base_dir)
            overall_ok = overall_ok and ok
            outputs.append(f"{kind}: {output}")
        return overall_ok, "\n".join(outputs) if outputs else "No verification commands ran"

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

    if action == "inspect_changed_files":
        ok, output = _run_command(["git", "diff", "--name-only"], base_dir, timeout=30)
        if not ok and "not a git repository" in output.lower():
            return True, "(not a git repository)"
        return ok, output or "(no changed files)"

    if action == "mkdir":
        target.mkdir(parents=True, exist_ok=True)
        return True, f"Created directory: {target}"

    if action == "rename_path":
        destination = _resolve_agent_path(str(step.get("destination", "")).strip(), base_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        target.rename(destination)
        return True, f"Renamed: {target} -> {destination}"

    if action == "write_json":
        ok, _, path, content = compute_step_file_change(step, base_dir)
        if not ok or path is None or content is None:
            return False, "Could not prepare JSON write"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True, f"Written JSON: {path}"

    if action == "write_yaml":
        ok, _, path, content = compute_step_file_change(step, base_dir)
        if not ok or path is None or content is None:
            return False, "Could not prepare YAML write"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True, f"Written YAML: {path}"

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

    if action == "search_symbols":
        return True, _search_symbols(base_dir, target, str(step.get("symbol", "")).strip(), str(step.get("symbol_kind", "")).strip())

    if action in {"patch_file", "patch_lines", "patch_context", "patch_apply"}:
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
            info["kind"] = "patch" if action in {"patch_file", "patch_lines", "patch_context"} else "file"
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
    read_targets = []
    change_targets = []
    verify_targets = []
    rollback_targets = []
    for item in inspected:
        step = item.get("step", {})
        if item.get("kind") == "read":
            read_targets.append(step.get("target") or step.get("path") or step.get("action"))
        if item.get("kind") in {"file", "patch", "mkdir"}:
            path = item.get("path")
            if path:
                rendered_path = str(path.relative_to(base_dir)) if path.is_relative_to(base_dir) else str(path)
                change_targets.append(rendered_path)
                rollback_targets.append(rendered_path)
        if item.get("kind") == "verify":
            verify_targets.append(step.get("verify_kind") or step.get("action"))
    risk_level = "low"
    if risky >= 2 or file_changes >= 4:
        risk_level = "high"
    elif risky or file_changes >= 2:
        risk_level = "medium"
    if read_targets:
        print(f"  {DG}reads:{R}  " + ", ".join(str(target) for target in read_targets[:6]))
    if change_targets:
        print(f"  {DG}changes:{R}  " + ", ".join(change_targets[:6]))
    if verify_targets:
        print(f"  {DG}checks:{R}  " + ", ".join(str(target) for target in verify_targets[:6]))
    print(f"  {DG}risk:{R}  {risk_level}")
    if rollback_targets:
        print(f"  {DG}rollback scope:{R}  " + ", ".join(rollback_targets[:6]))
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


def _should_retry_failed_step(step: dict) -> bool:
    if step.get("type") == "file_write":
        return True
    return step.get("type") == "action" and step.get("action") in FILE_MUTATION_ACTIONS | VERIFY_ACTIONS


def _run_recovery_steps(
    recovery_steps: list[dict],
    *,
    client: Any,
    model: str,
    memory: Any,
    system_prompt: str,
    yolo: bool,
    journal: ChangeJournal,
) -> tuple[bool, list[dict[str, Any]]]:
    outputs: list[dict[str, Any]] = []
    for step in recovery_steps:
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
        outputs.append({"step": step["description"], "success": success, "output": output})
        if not success:
            return False, outputs
    return True, outputs


def run_agent(
    task: str,
    client: Any,
    model: str,
    memory: Any,
    system_prompt: str,
    yolo: bool = False,
    review_only: bool = False,
) -> str:
    """Full agent loop: grounded plan → grouped approval → execute → optional rollback."""
    from src.utils.markdown import render as md_render

    base_dir = Path.cwd().resolve()
    journal = ChangeJournal()
    start_active_run(task)
    policy = _default_execution_policy(task)
    if review_only:
        policy = ExecutionPolicy(
            max_steps=policy.max_steps,
            max_file_changes=policy.max_file_changes,
            max_command_actions=policy.max_command_actions,
            max_recovery_attempts=policy.max_recovery_attempts,
            review_only=True,
        )

    print(f"\n  {PU}agent{R}  {DG}planning...{R}\n")

    try:
        steps = make_plan(task, client, model, base_dir=base_dir, policy=policy)
    except RuntimeError as exc:
        clear_active_run()
        record_run(task, status="planning_failed", summary=str(exc))
        return str(exc)

    if not steps:
        clear_active_run()
        record_run(task, status="planning_failed", summary="No steps generated.")
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
        update_active_run(status="preflight_failed", summary=reason)
        record_run(task, status="preflight_failed", summary=reason)
        return f"Plan rejected during preflight: {reason}"

    if policy.review_only:
        summary = f"Review-only plan generated with {len(steps)} steps; no changes executed."
        update_active_run(status="review_only", summary=summary)
        record_run(task, status="review_only", summary=summary)
        return summary

    print()
    if not yolo and not confirm(f"Execute {len(steps)} preflighted steps?"):
        update_active_run(status="cancelled", summary="Agent cancelled before execution.")
        record_run(task, status="cancelled", summary="Agent cancelled before execution.")
        return "Agent cancelled."

    results = []
    rollback_note = ""
    stopped = False
    recovery_used = False
    failed_checks: list[str] = []
    completed_plan_steps = 0
    failed_plan_steps = 0

    update_active_run(status="running", summary=f"Planned {len(steps)} steps")

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
            completed_plan_steps += 1
            touched_files = [
                str(record.path.relative_to(base_dir)) if record.path.is_relative_to(base_dir) else str(record.path)
                for record in journal.records
                if record.kind == "file"
            ]
            update_active_run(
                status="running",
                summary=f"Completed step {step['id']}/{len(steps)}: {step['description']}",
                touched_files=touched_files,
                failed_checks=failed_checks,
            )
            print(f"  {GN}✓{R}  ", end="")
            if output and len(output) < 300:
                print(output)
            elif output:
                print()
                for line in md_render(output[:800]).split("\n"):
                    print(f"  {GR}{line}{R}")
        else:
            update_active_run(
                status="recovering" if not recovery_used else "failed",
                summary=f"Failed step: {step['description']}",
                failed_checks=failed_checks,
                touched_files=[
                    str(record.path.relative_to(base_dir)) if record.path.is_relative_to(base_dir) else str(record.path)
                    for record in journal.records
                    if record.kind == "file"
                ],
            )
            print(f"  {RE}✗{R}  {output}")
            if step.get("type") == "action" and step.get("action") in VERIFY_ACTIONS | {"run_verify"}:
                failed_checks.append(step.get("verify_kind") or step.get("action", "verify"))
            if (
                not recovery_used
                and policy.max_recovery_attempts > 0
                and _should_retry_failed_step(step)
            ):
                try:
                    recovery_steps = make_recovery_plan(task, step, output, client, model, base_dir, policy)
                except RuntimeError as exc:
                    print(f"  {YE}▲{R}  {exc}")
                    stopped = True
                else:
                    if recovery_steps:
                        recovery_used = True
                        print(f"\n  {PU}recovery{R}  {DG}{len(recovery_steps)} bounded step(s){R}")
                        recovery_inspected = _render_grouped_summary(recovery_steps, base_dir)
                        invalid_recovery = [item for item in recovery_inspected if item.get('ok') is False]
                        if invalid_recovery:
                            print(f"  {YE}▲{R}  recovery preflight failed: {invalid_recovery[0].get('reason', 'invalid')}")
                            failed_plan_steps += 1
                            stopped = True
                        else:
                            if not yolo and not confirm(f"Execute recovery plan ({len(recovery_steps)} steps)?"):
                                failed_plan_steps += 1
                                stopped = True
                            else:
                                recovery_ok, recovery_outputs = _run_recovery_steps(
                                    recovery_steps,
                                    client=client,
                                    model=model,
                                    memory=memory,
                                    system_prompt=system_prompt,
                                    yolo=yolo,
                                    journal=journal,
                                )
                                results.extend(recovery_outputs)
                                if recovery_ok:
                                    print(f"  {GN}✓{R}  recovery steps completed")
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
                                        print(f"  {GN}✓{R}  retry succeeded")
                                        completed_plan_steps += 1
                                        results.append({"step": f"retry {step['description']}", "success": True, "output": output[:200]})
                                        continue
                                    print(f"  {RE}✗{R}  retry failed: {output}")
                                    failed_plan_steps += 1
                                    results.append({"step": f"retry {step['description']}", "success": False, "output": output[:200]})
                                else:
                                    failed_plan_steps += 1
                                stopped = True
                    else:
                        failed_plan_steps += 1
                        stopped = True
            else:
                failed_plan_steps += 1
                stopped = True

        results.append({"step": step["description"], "success": success, "output": output[:200]})

        if stopped:
            break

    if stopped and journal.has_changes() and not yolo:
        if confirm("Rollback changes from this run?"):
            rolled_back = journal.rollback()
            rollback_note = f" Rolled back {len(rolled_back)} change(s)."
            print(f"\n  {YE}↺{R}  rollback completed{R}")

    done = completed_plan_steps
    failed = failed_plan_steps
    summary = f"Agent completed {done}/{len(steps)} steps"
    if failed:
        summary += f" ({failed} failed, stopped early)"
    if rollback_note:
        summary += rollback_note
    if recovery_used:
        summary += " Recovery used."

    print(f"\n  {GN if not failed else YE}{'✓' if not failed else '▲'}{R}  {summary}\n")
    touched_files = [str(record.path.relative_to(base_dir)) if record.path.is_relative_to(base_dir) else str(record.path) for record in journal.records if record.kind == "file"]
    record_run(
        task,
        status="failed" if failed else "completed",
        summary=summary,
        touched_files=touched_files,
        failed_checks=failed_checks,
        recovery_used=recovery_used,
    )
    return summary
