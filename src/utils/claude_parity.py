"""Claude-style command/report surfaces and parity tracking for Lumi."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.agents.council import _get_available_agents
from src.agents.task_memory import get_active_run, get_recent_runs
from src.chat.providers import provider_label
from src.utils.repo_profile import inspect_workspace, render_workspace_overview
from src.utils.runtime_config import load_runtime_config
from src.utils.workbench import build_repo_intelligence, load_project_memory, load_workbench_jobs


@dataclass(frozen=True)
class CommandParityCategory:
    """Exact-token command parity snapshot for a Claude command category."""

    name: str
    commands: tuple[str, ...]
    present: tuple[str, ...]
    missing: tuple[str, ...]


@dataclass(frozen=True)
class BeaconWorkstream:
    """Major parity workstream for Lumi v0.7.5: Beacon."""

    key: str
    name: str
    description: str
    target: str
    rewrite_relevant: bool = False


CLAUDE_COMMAND_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Git & Version Control": ("/commit", "/commit-push-pr", "/branch", "/diff", "/pr_comments", "/rewind"),
    "Code Quality": ("/review", "/security-review", "/advisor", "/bughunter"),
    "Session & Context": ("/compact", "/context", "/resume", "/session", "/share", "/export", "/summary", "/clear"),
    "Configuration & Settings": (
        "/config",
        "/permissions",
        "/theme",
        "/output-style",
        "/color",
        "/keybindings",
        "/vim",
        "/effort",
        "/model",
        "/privacy-settings",
        "/fast",
        "/brief",
    ),
    "Memory & Knowledge": ("/memory", "/add-dir", "/files"),
    "MCP & Plugins": ("/mcp", "/plugin", "/reload-plugins", "/skills"),
    "Authentication": ("/login", "/logout", "/oauth-refresh"),
    "Tasks & Agents": ("/tasks", "/agents", "/ultraplan", "/plan"),
    "Diagnostics & Status": (
        "/doctor",
        "/status",
        "/stats",
        "/cost",
        "/version",
        "/usage",
        "/extra-usage",
        "/rate-limit-options",
    ),
    "Installation & Setup": ("/install", "/upgrade", "/init", "/init-verifiers", "/onboarding", "/terminalSetup"),
    "IDE & Desktop Integration": ("/bridge", "/bridge-kick", "/ide", "/desktop", "/mobile", "/teleport"),
    "Remote & Environment": ("/remote-env", "/remote-setup", "/env", "/sandbox-toggle"),
    "Misc": (
        "/help",
        "/exit",
        "/copy",
        "/feedback",
        "/release-notes",
        "/rename",
        "/tag",
        "/insights",
        "/stickers",
        "/good-claude",
        "/voice",
        "/chrome",
        "/issue",
        "/statusline",
        "/thinkback",
        "/thinkback-play",
        "/passes",
    ),
    "Internal / Debug Commands": (
        "/ant-trace",
        "/autofix-pr",
        "/backfill-sessions",
        "/break-cache",
        "/btw",
        "/ctx_viz",
        "/debug-tool-call",
        "/heapdump",
        "/hooks",
        "/mock-limits",
        "/perf-issue",
        "/reset-limits",
    ),
}

BEACON_WORKSTREAMS: tuple[BeaconWorkstream, ...] = (
    BeaconWorkstream("permissions", "Wildcard tool permission engine", "Claude-style tool approval rules, modes, logging, and plan-wide approvals.", "/permissions /sandbox-toggle", rewrite_relevant=True),
    BeaconWorkstream("tools", "Explicit tool registry", "Schema-driven tools with read-only flags, concurrency safety, and permission checks.", "core tool runtime", rewrite_relevant=True),
    BeaconWorkstream("git", "Git workflow suite", "Commit, branch, PR, rewind, and richer diff automation from the terminal.", "/commit /commit-push-pr /branch /pr_comments /rewind"),
    BeaconWorkstream("quality", "Code-quality command suite", "Dedicated security, architecture, and bug-hunting commands with structured output.", "/security-review /advisor /bughunter"),
    BeaconWorkstream("sessions", "Session and context parity", "Summary, share, tag, rename, compact, and stronger session lifecycle control.", "/summary /share /session /resume"),
    BeaconWorkstream("tasks", "Background task engine", "Persistent task lifecycle, output retrieval, retry, stop, and history.", "/tasks", rewrite_relevant=True),
    BeaconWorkstream("agents", "Sub-agent orchestration", "Spawned worker agents, plan mode, teams, and merge-back flows.", "/agents /plan /ultraplan", rewrite_relevant=True),
    BeaconWorkstream("lsp", "LSP repo intelligence", "Definitions, references, renames, symbol search, and semantic impact analysis.", "repo navigation", rewrite_relevant=True),
    BeaconWorkstream("bridge", "IDE bridge", "VS Code and JetBrains bridge with permission proxy, diff display, and session routing.", "/bridge /ide", rewrite_relevant=True),
    BeaconWorkstream("settings", "Full settings layer", "Privacy, output style, keybindings, vim mode, statusline, env, and sandbox controls.", "/config /privacy-settings /output-style /keybindings /vim /statusline"),
    BeaconWorkstream("usage", "Usage and telemetry surfaces", "Stats, usage, rate-limit views, and model/runtime accounting.", "/stats /usage /extra-usage /rate-limit-options"),
    BeaconWorkstream("setup", "Install, init, and upgrade flows", "Project bootstrap, verifier setup, onboarding, and release-note surfaces.", "/init /init-verifiers /upgrade /release-notes /onboarding"),
    BeaconWorkstream("plugins", "Plugin and skill lifecycle parity", "Install/update/remove marketplace flow, bundled skills, and safer hook boundaries.", "/plugin /reload-plugins /skills /hooks"),
    BeaconWorkstream("remote", "Remote and device handoff layer", "Remote env/setup and replaceable desktop/mobile handoff surfaces.", "/remote-env /remote-setup /desktop /mobile /teleport", rewrite_relevant=True),
    BeaconWorkstream("tui", "TUI control-density parity", "Statusline, keymaps, panes, permission prompts, and Claude-grade operator UX.", "terminal UI", rewrite_relevant=True),
    BeaconWorkstream("diagnostics", "Parity and regression audits", "Track command, subsystem, and workflow parity with machine-readable audits.", "claude parity audit"),
    BeaconWorkstream("rewrite", "1.0.0 native runtime rewrite", "Move Lumi to Bun/TypeScript/Ink after Beacon lands enough parity in Python.", "v1.0.0 Native", rewrite_relevant=True),
)


def _repo_source(base_dir: Path | None = None) -> str:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    parts: list[str] = []
    main_path = root / "main.py"
    if main_path.is_file():
        parts.append(main_path.read_text(encoding="utf-8", errors="ignore"))
    src_root = root / "src"
    if src_root.is_dir():
        for path in sorted(src_root.rglob("*.py")):
            if path.name == "claude_parity.py":
                continue
            parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def extract_lumi_command_tokens(base_dir: Path | None = None) -> set[str]:
    """Extract slash-command tokens currently present in Lumi source."""

    source = _repo_source(base_dir)
    tokens: set[str] = set()

    for pattern in (
        r'@registry\.register\("(/[a-zA-Z0-9_-]+)"',
        r'cmd\("(/[a-zA-Z0-9_-]+)"',
        r'if cmd == "(/[a-zA-Z0-9_-]+)"',
        r'cmd = "(/[a-zA-Z0-9_-]+)"',
    ):
        tokens.update(re.findall(pattern, source))

    for aliases in re.findall(r"aliases=\[([^\]]+)\]", source):
        tokens.update(re.findall(r"/[a-zA-Z0-9_-]+", aliases))

    for group in re.findall(r"if cmd in \{([^}]+)\}", source):
        tokens.update(re.findall(r"/[a-zA-Z0-9_-]+", group))

    return tokens


def collect_command_parity(base_dir: Path | None = None) -> list[CommandParityCategory]:
    """Compare Lumi's current command tokens against the Claude command catalog."""

    tokens = extract_lumi_command_tokens(base_dir)
    categories: list[CommandParityCategory] = []
    for name, commands in CLAUDE_COMMAND_CATEGORIES.items():
        present = tuple(command for command in commands if command in tokens)
        missing = tuple(command for command in commands if command not in tokens)
        categories.append(
            CommandParityCategory(
                name=name,
                commands=commands,
                present=present,
                missing=missing,
            )
        )
    return categories


def claude_parity_summary(base_dir: Path | None = None) -> tuple[int, int, float]:
    """Return exact-token Claude command parity summary for Lumi."""

    categories = collect_command_parity(base_dir)
    total = sum(len(item.commands) for item in categories)
    present = sum(len(item.present) for item in categories)
    ratio = (present / total) if total else 0.0
    return present, total, ratio


def collect_beacon_workstreams() -> tuple[BeaconWorkstream, ...]:
    """Return the authoritative Beacon workstream list."""

    return BEACON_WORKSTREAMS


def render_claude_parity_report(base_dir: Path | None = None) -> str:
    """Render a readable parity audit against the Claude command catalog."""

    present, total, ratio = claude_parity_summary(base_dir)
    categories = collect_command_parity(base_dir)
    workstreams = collect_beacon_workstreams()

    lines = [
        "Claude parity audit",
        f"  Exact-token command parity: {present}/{total} ({ratio:.0%})",
        "",
        "Command categories",
    ]
    for item in categories:
        lines.append(
            f"  - {item.name}: {len(item.present)}/{len(item.commands)}"
        )
        if item.missing:
            preview = ", ".join(item.missing[:6])
            if len(item.missing) > 6:
                preview += ", ..."
            lines.append(f"      missing: {preview}")
    lines.extend(["", "Beacon workstreams"])
    for index, item in enumerate(workstreams, 1):
        rewrite_note = " [rewrite]" if item.rewrite_relevant else ""
        lines.append(f"  {index}. {item.name}{rewrite_note}")
        lines.append(f"      target: {item.target}")
        lines.append(f"      scope: {item.description}")
    lines.extend(
        [
            "",
            "Release path",
            "  - v0.7.5: Beacon — Python execution release focused on the 17 workstreams.",
            "  - v1.0.0: Native — Bun/TypeScript/Ink rewrite after Beacon lands enough workflow parity.",
        ]
    )
    return "\n".join(lines)


def render_files_report(base_dir: Path | None = None, *, task: str = "") -> str:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    profile = inspect_workspace(root)
    intelligence = build_repo_intelligence(root, task=task)
    config = load_runtime_config(root)

    lines = ["Lumi files", "", render_workspace_overview(profile), ""]
    if config.extra_dirs:
        lines.append("Extra context directories")
        for item in config.extra_dirs:
            lines.append(f"  - {item}")
        lines.append("")
    lines.append("Changed files")
    if intelligence.changed_files:
        for item in intelligence.changed_files[:10]:
            lines.append(f"  - {item}")
    else:
        lines.append("  - none")
    lines.append("")
    lines.append("Relevant files")
    if intelligence.relevant_files:
        for item in intelligence.relevant_files[:10]:
            lines.append(f"  - {item}")
    else:
        lines.append("  - none")
    lines.append("")
    lines.append("Hotspots")
    if intelligence.hotspots:
        for item in intelligence.hotspots[:8]:
            lines.append(f"  - {item}")
    else:
        lines.append("  - none")
    return "\n".join(lines)


def render_tasks_report(base_dir: Path | None = None) -> str:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    active = get_active_run(root)
    recent = get_recent_runs(limit=6, base_dir=root)
    memory = load_project_memory(root)
    jobs = load_workbench_jobs(root, limit=4)

    lines = ["Lumi tasks"]
    if active:
        lines.extend(
            [
                "",
                "Active",
                f"  - status: {active.get('status', '?')}",
                f"  - objective: {active.get('objective', '')}",
                f"  - touched: {', '.join(active.get('touched_files', [])[:6]) or 'none'}",
                f"  - failed checks: {', '.join(active.get('failed_checks', [])[:4]) or 'none'}",
            ]
        )
    lines.append("")
    lines.append("Recent runs")
    if recent:
        for item in recent:
            lines.append(f"  - [{item.get('status', '?')}] {item.get('objective', '')}")
    else:
        lines.append("  - none")
    lines.append("")
    lines.append("Workbench memory")
    if memory.recent_runs:
        for item in memory.recent_runs[:4]:
            lines.append(f"  - [{item.get('mode', '?')}] {item.get('objective', '')}")
    else:
        lines.append("  - none")
    lines.append("")
    lines.append("Recent workbench jobs")
    if jobs:
        for item in jobs:
            lines.append(f"  - [{item.status}] {item.mode} · {item.objective}")
    else:
        lines.append("  - none")
    return "\n".join(lines)


def render_agents_report(
    *,
    base_dir: Path | None = None,
    active_objective: str = "",
    active_tasks: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
) -> str:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    available = _get_available_agents()
    lines = ["Lumi agents", f"  Workspace: {root}"]
    lines.append("")
    lines.append("Active")
    if active_objective:
        lines.append(f"  - objective: {active_objective}")
        if active_tasks:
            for item in list(active_tasks)[:8]:
                lines.append(f"  - {item.get('status', '?')}: {item.get('text', '')}")
    else:
        lines.append("  - idle")
    lines.append("")
    lines.append("Available council agents")
    if available:
        for item in available:
            provider = provider_label(str(item.get('provider', '')))
            role = str(item.get('role', 'agent'))
            strength = ", ".join(str(s) for s in item.get('strengths', [])[:3]) or "general"
            lines.append(f"  - {item.get('name', item.get('id', 'agent'))} · {provider} · {role} · {strength}")
    else:
        lines.append("  - none configured")
    return "\n".join(lines)


def render_version_report(*, version: str, provider: str = "", model: str = "") -> str:
    label = provider_label(provider) if provider else "Unknown"
    lines = [f"Lumi version {version}"]
    if provider or model:
        lines.append(f"  Runtime: {label} · {model or 'unknown'}")
    lines.append(f"  CWD:     {Path.cwd().resolve()}")
    lines.append("  Workbench: Beacon")
    lines.append("  Parity layer: Claude-style config, tasks, agents, files, and sessions")
    return "\n".join(lines)
