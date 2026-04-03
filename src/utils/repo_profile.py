"""Shared workspace profiling helpers for Lumi."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.utils.project_context import find_project_context_file
from src.utils.runtime_config import display_context_path, iter_context_roots, load_runtime_config


@dataclass(frozen=True)
class WorkspaceProfile:
    base_dir: Path
    package_manager: str | None
    languages: tuple[str, ...]
    frameworks: tuple[str, ...]
    source_directories: tuple[str, ...]
    test_directories: tuple[str, ...]
    entrypoints: tuple[str, ...]
    config_files: tuple[str, ...]
    verification_commands: dict[str, tuple[str, ...]]
    readme_path: str | None
    project_context_path: str | None
    notes: tuple[str, ...] = ()
    git_branch: str | None = None
    changed_files: tuple[str, ...] = ()
    context_directories: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskWorkspaceProfile:
    workspace: WorkspaceProfile
    relevant_files: tuple[str, ...]
    task: str = ""

    @property
    def base_dir(self) -> Path:
        return self.workspace.base_dir

    @property
    def package_manager(self) -> str | None:
        return self.workspace.package_manager

    @property
    def frameworks(self) -> tuple[str, ...]:
        return self.workspace.frameworks

    @property
    def entrypoints(self) -> tuple[str, ...]:
        return self.workspace.entrypoints

    @property
    def config_files(self) -> tuple[str, ...]:
        return self.workspace.config_files

    @property
    def changed_files(self) -> tuple[str, ...]:
        return self.workspace.changed_files

    @property
    def verification_commands(self) -> dict[str, tuple[str, ...]]:
        return self.workspace.verification_commands

    @property
    def notes(self) -> tuple[str, ...]:
        return self.workspace.notes


def command_available(command: str) -> bool:
    return bool(shutil.which(command))


def detect_package_manager(base_dir: Path) -> str | None:
    if (base_dir / "pnpm-lock.yaml").exists() and command_available("pnpm"):
        return "pnpm"
    if (base_dir / "yarn.lock").exists() and command_available("yarn"):
        return "yarn"
    if (base_dir / "bun.lockb").exists() and command_available("bun"):
        return "bun"
    if (base_dir / "package-lock.json").exists() and command_available("npm"):
        return "npm"
    if (base_dir / "package.json").exists():
        for candidate in ("pnpm", "yarn", "bun", "npm"):
            if command_available(candidate):
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


def _has_python_tests(base_dir: Path) -> bool:
    tests_dir = base_dir / "tests"
    if tests_dir.exists():
        for path in tests_dir.rglob("*"):
            if path.is_file() and path.name.startswith("test"):
                return True
    return any(base_dir.glob("test_*.py"))


def detect_verification_commands(base_dir: Path) -> dict[str, tuple[str, ...]]:
    commands: dict[str, tuple[str, ...]] = {}
    scripts = _load_package_scripts(base_dir)
    package_manager = detect_package_manager(base_dir)

    if _has_python_tests(base_dir):
        commands["tests"] = (sys.executable, "-m", "pytest")

    pyproject = base_dir / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="replace").lower()
        if "[tool.ruff" in text or "ruff" in text:
            commands["lint"] = (sys.executable, "-m", "ruff", "check", ".")
        if "mypy" in text:
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

    if (base_dir / "Cargo.toml").exists() and command_available("cargo"):
        commands.setdefault("tests", ("cargo", "test"))
        commands.setdefault("lint", ("cargo", "fmt", "--", "--check"))
        commands.setdefault("types", ("cargo", "check"))

    if (base_dir / "go.mod").exists() and command_available("go"):
        commands.setdefault("tests", ("go", "test", "./..."))
        commands.setdefault("types", ("go", "test", "./..."))

    if not commands and pyproject.exists():
        commands["tests"] = (sys.executable, "-m", "pytest")

    return commands


def detect_entrypoints(base_dir: Path) -> tuple[str, ...]:
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


def detect_frameworks(base_dir: Path) -> tuple[str, ...]:
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


def detect_languages(base_dir: Path) -> tuple[str, ...]:
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
    }
    counts: dict[str, int] = {}
    for root in iter_context_roots(base_dir):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {".git", "node_modules", "__pycache__", "venv", ".venv"} for part in path.parts):
                continue
            language = mapping.get(path.suffix.lower())
            if language:
                counts[language] = counts.get(language, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(language for language, _ in ranked[:5])


def _discover_named_dirs(base_dir: Path, candidates: tuple[str, ...]) -> tuple[str, ...]:
    found: list[str] = []
    for candidate in candidates:
        path = base_dir / candidate
        if path.exists() and path.is_dir():
            found.append(candidate)
    return tuple(found)


def detect_source_directories(base_dir: Path) -> tuple[str, ...]:
    return _discover_named_dirs(base_dir, ("src", "app", "lib", "server", "client", "backend", "frontend"))


def detect_test_directories(base_dir: Path) -> tuple[str, ...]:
    return _discover_named_dirs(base_dir, ("tests", "test", "spec", "__tests__"))


def detect_config_files(base_dir: Path) -> tuple[str, ...]:
    candidates = (
        "LUMI.md",
        "lumi.md",
        "CLAUDE.md",
        "claude.md",
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
    found = [candidate for candidate in candidates if (base_dir / candidate).exists()]
    return tuple(found[:8])


def detect_git_branch(base_dir: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=base_dir,
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


def detect_changed_files(base_dir: Path, limit: int = 12) -> tuple[str, ...]:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()
    changed: list[str] = []
    for line in result.stdout.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue
        changed.append(trimmed[3:] if len(trimmed) > 3 else trimmed)
    return tuple(changed[:limit])


def detect_context_directories(base_dir: Path) -> tuple[str, ...]:
    config = load_runtime_config(base_dir)
    return tuple(config.extra_dirs)


def _task_keywords(task: str) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_./-]{2,}", task.lower())
    stop = {"the", "and", "for", "with", "this", "that", "into", "from", "then", "file", "folder"}
    return [word for word in words if word not in stop][:16]


def find_relevant_paths(base_dir: Path, task: str, limit: int = 8) -> tuple[str, ...]:
    keywords = _task_keywords(task)
    if not keywords:
        return ()
    matches: list[tuple[int, str]] = []
    seen: set[str] = set()
    for root in iter_context_roots(base_dir):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in {".git", "__pycache__", "node_modules", "venv", ".venv"} for part in path.parts):
                continue
            relative = display_context_path(path, base_dir=base_dir)
            if relative in seen:
                continue
            seen.add(relative)
            lower_name = relative.lower()
            score = 0
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
                matches.append((score, relative))
    matches.sort(key=lambda item: (-item[0], item[1]))
    return tuple(relative for _, relative in matches[:limit])


def _read_context_file(path: Path, base_dir: Path, max_chars: int = 1200) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"## {path.relative_to(base_dir)}\n(unreadable: {exc})"
    snippet = text[:max_chars]
    if len(text) > max_chars:
        snippet += "\n... [truncated]"
    return f"## {path.relative_to(base_dir)}\n{snippet}"


def inspect_workspace(base_dir: Path | None = None) -> WorkspaceProfile:
    root = (base_dir or Path.cwd()).resolve()
    verification = detect_verification_commands(root)
    notes: list[str] = []
    if not verification:
        notes.append("no verification commands detected")
    context_path = find_project_context_file(root)
    project_context_path = context_path.name if context_path is not None else None
    readme_path = next(
        (name for name in ("README.md", "readme.md", "README.rst") if (root / name).exists()),
        None,
    )
    return WorkspaceProfile(
        base_dir=root,
        package_manager=detect_package_manager(root),
        languages=detect_languages(root),
        frameworks=detect_frameworks(root),
        source_directories=detect_source_directories(root),
        test_directories=detect_test_directories(root),
        entrypoints=detect_entrypoints(root),
        config_files=detect_config_files(root),
        verification_commands=verification,
        readme_path=readme_path,
        project_context_path=project_context_path,
        notes=tuple(notes),
        git_branch=detect_git_branch(root),
        changed_files=detect_changed_files(root),
        context_directories=detect_context_directories(root),
    )


def inspect_task_workspace(
    base_dir: Path | None = None,
    *,
    task: str = "",
    relevant_limit: int = 8,
) -> TaskWorkspaceProfile:
    root = (base_dir or Path.cwd()).resolve()
    workspace = inspect_workspace(root)
    relevant = find_relevant_paths(root, task, limit=relevant_limit)
    return TaskWorkspaceProfile(
        workspace=workspace,
        relevant_files=relevant,
        task=task,
    )


def render_workspace_overview(profile: WorkspaceProfile) -> str:
    lines = [f"Workspace: {profile.base_dir}"]
    if profile.context_directories:
        lines.append(f"  Context:   {', '.join(profile.context_directories[:4])}")
    if profile.languages:
        lines.append(f"  Languages: {', '.join(profile.languages)}")
    if profile.frameworks:
        lines.append(f"  Stack:     {', '.join(profile.frameworks)}")
    if profile.package_manager:
        lines.append(f"  Packages:  {profile.package_manager}")
    if profile.source_directories:
        lines.append(f"  Source:    {', '.join(profile.source_directories)}")
    if profile.test_directories:
        lines.append(f"  Tests:     {', '.join(profile.test_directories)}")
    if profile.entrypoints:
        lines.append(f"  Entrypoints: {', '.join(profile.entrypoints)}")
    if profile.config_files:
        lines.append(f"  Config:    {', '.join(profile.config_files[:6])}")
    if profile.verification_commands:
        lines.append(f"  Checks:    {', '.join(sorted(profile.verification_commands))}")
    else:
        lines.append("  Checks:    none detected")
    return "\n".join(lines)


def build_onboarding_hints(profile: WorkspaceProfile) -> list[str]:
    hints: list[str] = []
    if not profile.project_context_path:
        hints.append("Create LUMI.md or CLAUDE.md so Lumi can learn project conventions.")
    if not profile.readme_path:
        hints.append("Add a README.md with setup and verification commands for better repo grounding.")
    if not profile.verification_commands:
        hints.append("Add tests or lint/typecheck config so agent runs can verify changes.")
    if not profile.source_directories:
        hints.append("Keep source files in a clear top-level directory like src/ or app/ for better retrieval.")
    if not profile.test_directories:
        hints.append("Use a standard test directory like tests/ so Lumi can find verification targets.")
    if profile.languages and "python" in profile.languages and "python" not in profile.frameworks:
        hints.append("If this is a Python repo, declaring tools in pyproject.toml will improve repo detection.")
    return hints[:5]


def build_planning_context(
    base_dir: Path | None = None,
    *,
    task: str = "",
    max_context_files: int = 6,
    max_context_file_chars: int = 1200,
    max_top_entries: int = 40,
    task_memory: str = "",
) -> str:
    root = (base_dir or Path.cwd()).resolve()
    profile = inspect_workspace(root)
    relevant_paths = find_relevant_paths(root, task)
    lines = [f"Workspace root: {root}", ""]

    top_entries = sorted(root.iterdir(), key=lambda path: (not path.is_dir(), path.name.lower()))
    if top_entries:
        lines.append("Top-level entries:")
        for entry in top_entries[:max_top_entries]:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"- {entry.name}{suffix}")
        lines.append("")

    key_files = [
        "LUMI.md",
        "lumi.md",
        "CLAUDE.md",
        "claude.md",
        "README.md",
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "Cargo.toml",
        "go.mod",
    ]
    mentioned = sorted(set(re.findall(r"[\w./-]+\.\w+", task)))
    candidate_rel_paths = key_files + mentioned + list(relevant_paths[:max_context_files])
    seen: set[Path] = set()
    readable: list[Path] = []
    for rel_path in candidate_rel_paths:
        path = root / rel_path
        if not path.exists() or not path.is_file() or path in seen:
            continue
        seen.add(path)
        readable.append(path)
    if readable:
        lines.append("Relevant workspace files:")
        for path in readable[:max_context_files]:
            lines.append(_read_context_file(path, root, max_chars=max_context_file_chars))
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

    if profile.languages:
        lines.append("Detected languages:")
        for language in profile.languages:
            lines.append(f"- {language}")
        lines.append("")

    if profile.source_directories:
        lines.append("Source directories:")
        for source_dir in profile.source_directories:
            lines.append(f"- {source_dir}")
        lines.append("")

    if profile.test_directories:
        lines.append("Test directories:")
        for test_dir in profile.test_directories:
            lines.append(f"- {test_dir}")
        lines.append("")

    if profile.config_files:
        lines.append("Key config files:")
        for config_path in profile.config_files:
            lines.append(f"- {config_path}")
        lines.append("")

    if profile.package_manager:
        lines.append(f"Detected package manager: {profile.package_manager}")
        lines.append("")

    if relevant_paths:
        lines.append("Likely relevant files:")
        for rel_path in relevant_paths:
            lines.append(f"- {rel_path}")
        lines.append("")

    if profile.git_branch:
        lines.append(f"Git branch: {profile.git_branch}")
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

    if task_memory.strip():
        lines.append(task_memory.strip())
        lines.append("")

    if profile.changed_files or profile.git_branch:
        lines.append("Git status:")
        lines.extend(f"- {path}" for path in profile.changed_files or ("(clean)",))

    return "\n".join(lines).strip()
