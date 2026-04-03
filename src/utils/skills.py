"""Markdown-backed Lumi skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.config import LUMI_HOME

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass(frozen=True)
class SkillSpec:
    name: str
    command: str
    description: str
    body: str
    path: Path
    scope: str
    mode: str = "chat"

    @property
    def identifier(self) -> str:
        return self.path.stem.lower()


def skill_roots(base_dir: Path | None = None) -> tuple[Path, ...]:
    root = (base_dir or Path.cwd()).resolve()
    candidates = (
        root / ".lumi" / "skills",
        root / "skills",
        LUMI_HOME / "skills",
    )
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return tuple(roots)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    data: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        data[key.strip().lower()] = value.strip().strip("\"'")
    return data, text[match.end() :]


def _normalize_command(value: str, *, fallback: str) -> str:
    raw = (value or fallback).strip().lower()
    raw = re.sub(r"\s+", "-", raw)
    raw = re.sub(r"[^a-z0-9/_-]", "", raw)
    raw = raw.strip() or fallback.lower()
    return raw if raw.startswith("/") else "/" + raw


def _derive_description(name: str, body: str) -> str:
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        if line:
            return line[:120]
    return f"Run the {name} skill"


def _discover_markdown_files(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    return sorted(
        path for path in root.rglob("*.md") if path.is_file()
    )


def scan_skills(base_dir: Path | None = None) -> list[SkillSpec]:
    found: dict[str, SkillSpec] = {}
    root = (base_dir or Path.cwd()).resolve()
    for directory in skill_roots(root):
        scope = "workspace" if root in directory.parents or directory == root / "skills" else "global"
        for path in _discover_markdown_files(directory):
            text = path.read_text(encoding="utf-8", errors="replace")
            meta, body = _parse_frontmatter(text)
            name = (meta.get("name") or path.stem.replace("-", " ").replace("_", " ").title()).strip()
            command = _normalize_command(meta.get("command", ""), fallback=path.stem)
            if command in found:
                continue
            description = (meta.get("description") or _derive_description(name, body)).strip()
            mode = (meta.get("mode") or "chat").strip().lower() or "chat"
            found[command] = SkillSpec(
                name=name,
                command=command,
                description=description,
                body=body.strip(),
                path=path,
                scope=scope,
                mode=mode,
            )
    return sorted(found.values(), key=lambda item: (item.scope != "workspace", item.command))


def find_skill(identifier: str, *, base_dir: Path | None = None) -> SkillSpec | None:
    needle = (identifier or "").strip().lower()
    if not needle:
        return None
    for skill in scan_skills(base_dir):
        if needle in {skill.command.lower(), skill.identifier, skill.name.lower()}:
            return skill
    return None


def skill_hits(
    query: str,
    *,
    base_dir: Path | None = None,
    exclude_commands: set[str] | None = None,
    limit: int = 8,
) -> list[tuple[str, str, str, str]]:
    needle = (query or "").strip().lower()
    if needle.startswith("/"):
        needle = needle[1:]
    excluded = {item.lower() for item in (exclude_commands or set())}
    hits: list[tuple[str, str, str, str, tuple[int, int, str]]] = []
    for skill in scan_skills(base_dir):
        if skill.command.lower() in excluded:
            continue
        haystack = " ".join(
            [
                skill.command.lower(),
                skill.command.lower().lstrip("/"),
                skill.name.lower(),
                skill.description.lower(),
            ]
        )
        if not needle or skill.command.lower().lstrip("/").startswith(needle):
            score = (0, len(skill.command), skill.command)
        elif needle in haystack:
            score = (1, len(skill.command), skill.command)
        else:
            continue
        hits.append((skill.command, skill.description, "skills", skill.command, score))
    hits.sort(key=lambda item: item[-1])
    return [(cmd, desc, category, example) for cmd, desc, category, example, _score in hits[:limit]]


def render_skill_inventory_report(*, base_dir: Path | None = None) -> str:
    skills = scan_skills(base_dir)
    lines = ["Skills"]
    if not skills:
        lines.append("  none discovered")
        lines.append("  add markdown files to ./skills, ./.lumi/skills, or ~/Lumi/skills")
        return "\n".join(lines)

    lines.append(f"  discovered: {len(skills)}")
    lines.append("  roots:")
    for root in skill_roots(base_dir):
        lines.append(f"    {root}")
    lines.append("")
    for skill in skills:
        lines.append(f"  {skill.command}  [{skill.scope}; {skill.mode}]")
        lines.append(f"    {skill.description}")
    lines.append("")
    lines.append("  next: /skills inspect <name>")
    return "\n".join(lines)


def render_skill_detail(identifier: str, *, base_dir: Path | None = None) -> str:
    skill = find_skill(identifier, base_dir=base_dir)
    if skill is None:
        return f"Skill not found: {identifier}"
    lines = [
        f"Skill {skill.command}",
        f"  Name:        {skill.name}",
        f"  Scope:       {skill.scope}",
        f"  Mode:        {skill.mode}",
        f"  Path:        {skill.path}",
        f"  Description: {skill.description}",
        "",
        "Instructions",
    ]
    body_lines = skill.body.splitlines() or ["(empty)"]
    lines.extend(f"  {line}" if line else "" for line in body_lines[:24])
    if len(body_lines) > 24:
        lines.append("  ...")
    return "\n".join(lines)


def build_skill_prompt(
    skill: SkillSpec,
    args: str,
    *,
    workspace: Path | None = None,
) -> str:
    root = (workspace or Path.cwd()).resolve()
    payload = {
        "args": args.strip(),
        "workspace": str(root),
        "command": skill.command,
        "name": skill.name,
        "description": skill.description,
    }
    body = skill.body
    used_template = False
    for key, value in payload.items():
        token = "{{" + key + "}}"
        if token in body:
            body = body.replace(token, value)
            used_template = True
    if used_template:
        return body.strip()
    request = payload["args"] or "Use this skill with its built-in default behavior."
    return (
        f"You are executing the Lumi skill `{skill.command}` ({skill.name}).\n\n"
        f"Skill instructions:\n{skill.body.strip()}\n\n"
        f"Invocation context:\n"
        f"- command: {skill.command}\n"
        f"- workspace: {root}\n"
        f"- user request: {request}\n\n"
        "Follow the skill instructions exactly and produce the best possible result."
    )
