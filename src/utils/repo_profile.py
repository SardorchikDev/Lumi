"""Shared workspace profiling helpers for Lumi."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceProfile:
    base_dir: Path
    package_manager: str | None
    frameworks: tuple[str, ...]
    entrypoints: tuple[str, ...]
    config_files: tuple[str, ...]
    verification_commands: dict[str, tuple[str, ...]]
    project_context_path: str | None
    notes: tuple[str, ...] = ()


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


def detect_config_files(base_dir: Path) -> tuple[str, ...]:
    candidates = (
        "LUMI.md",
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


def inspect_workspace(base_dir: Path | None = None) -> WorkspaceProfile:
    root = (base_dir or Path.cwd()).resolve()
    verification = detect_verification_commands(root)
    notes: list[str] = []
    if not verification:
        notes.append("no verification commands detected")
    project_context_path = "LUMI.md" if (root / "LUMI.md").exists() else None
    return WorkspaceProfile(
        base_dir=root,
        package_manager=detect_package_manager(root),
        frameworks=detect_frameworks(root),
        entrypoints=detect_entrypoints(root),
        config_files=detect_config_files(root),
        verification_commands=verification,
        project_context_path=project_context_path,
        notes=tuple(notes),
    )
