"""Shared session, workspace, and onboarding reports for Lumi."""

from __future__ import annotations

from pathlib import Path

from src.agents.task_memory import get_active_run, get_recent_runs
from src.chat.providers import provider_health_snapshot, provider_label
from src.config import CACHE_ROOT, LUMI_HOME, PLUGINS_DIR, STATE_ROOT, UI_STATE_DIR
from src.memory.longterm import memory_stats
from src.utils.git_tools import summarize_git_state
from src.utils.plugins import audit_plugins, describe_plugins
from src.utils.rebirth import rebirth_status_summary
from src.utils.repo_profile import (
    build_onboarding_hints,
    inspect_workspace,
    render_workspace_overview,
)


def _env_candidates(base_dir: Path) -> list[Path]:
    return [
        (base_dir / ".env").resolve(),
        (LUMI_HOME / ".env").resolve(),
    ]


def _find_env_file(base_dir: Path) -> Path | None:
    for candidate in _env_candidates(base_dir):
        if candidate.exists():
            return candidate
    return None


def _capability_ready_labels(provider_health: list, capability: str) -> list[str]:
    return [
        item.label
        for item in provider_health
        if item.configured and capability in item.capabilities
    ]


def build_status_report(
    *,
    base_dir: Path | None = None,
    provider: str = "",
    model: str = "",
    session_turns: int = 0,
    short_term_stats: dict | None = None,
    recent_commands: list[str] | None = None,
) -> str:
    root = (base_dir or Path.cwd()).resolve()
    profile = inspect_workspace(root)
    longterm = memory_stats()
    git_summary = summarize_git_state(root)
    plugins = describe_plugins()
    active_run = get_active_run(root)
    provider_health = provider_health_snapshot(has_ollama=provider == "ollama")
    vision_ready = _capability_ready_labels(provider_health, "vision")
    voice_ready = _capability_ready_labels(provider_health, "audio_transcription")

    lines = ["Lumi status", f"  Workspace: {root}"]
    if provider or model:
        active_provider = provider_label(provider) if provider else "Unknown"
        lines.append(f"  Model:     {active_provider} · {model or 'unknown'}")
    lines.append(f"  Turns:     {session_turns}")

    if short_term_stats:
        lines.append(
            "  Session:   "
            f"{short_term_stats.get('total_messages', 0)} messages "
            f"({short_term_stats.get('user_messages', 0)} user / "
            f"{short_term_stats.get('assistant_messages', 0)} assistant)"
        )

    lines.append(
        "  Memory:    "
        f"{longterm['facts']} fact(s), {longterm['episodes']} episode(s), "
        f"{longterm['persona_override_keys']} persona override key(s)"
    )
    lines.append(f"  Rebirth:   {rebirth_status_summary()}")
    lines.append(f"  Runtime:   state {STATE_ROOT} · cache {CACHE_ROOT}")
    if vision_ready or voice_ready:
        lines.append(
            "  Media:     "
            f"vision {', '.join(vision_ready) if vision_ready else 'none'} · "
            f"voice {', '.join(voice_ready) if voice_ready else 'none'}"
        )

    if active_run:
        lines.append(
            "  Agent:     "
            f"{active_run.get('status', '?')} · {active_run.get('objective', '')}"
        )
    else:
        recent_runs = get_recent_runs(limit=1, base_dir=root)
        if recent_runs:
            last = recent_runs[0]
            lines.append(
                "  Agent:     "
                f"last {last.get('status', '?')} · {last.get('objective', '')}"
            )

    if profile.frameworks:
        lines.append(f"  Stack:     {', '.join(profile.frameworks)}")
    if profile.languages:
        lines.append(f"  Languages: {', '.join(profile.languages)}")
    if profile.package_manager:
        lines.append(f"  Packages:  {profile.package_manager}")
    if profile.source_directories:
        lines.append(f"  Source:    {', '.join(profile.source_directories)}")
    if profile.test_directories:
        lines.append(f"  Tests:     {', '.join(profile.test_directories)}")
    if profile.verification_commands:
        checks = ", ".join(sorted(profile.verification_commands))
        lines.append(f"  Checks:    {checks}")
    else:
        lines.append("  Checks:    none detected")

    if recent_commands:
        commands = ", ".join(recent_commands[:3]) if recent_commands else "none"
        lines.append(f"  Commands:  {commands}")

    lines.append(f"  Plugins:   {len(plugins)} loaded")

    lines.append("")
    lines.append("Git")
    git_lines = git_summary.splitlines() or ["  unavailable"]
    for line in git_lines[:8]:
        lines.append(f"  {line}")

    return "\n".join(lines)


def build_doctor_report(
    *,
    base_dir: Path | None = None,
    provider: str = "",
    model: str = "",
    configured_providers: list[str] | None = None,
) -> str:
    root = (base_dir or Path.cwd()).resolve()
    profile = inspect_workspace(root)
    plugins = describe_plugins()
    plugin_audit = audit_plugins()
    env_file = _find_env_file(root)
    configured = configured_providers or []
    provider_health = provider_health_snapshot(has_ollama="ollama" in configured)

    lines = ["Lumi doctor", f"  Workspace: {root}"]
    if provider or model:
        lines.append(f"  Current:   {provider_label(provider) if provider else 'Unknown'} · {model or 'unknown'}")
    lines.append(f"  Env file:  {env_file if env_file else 'missing'}")
    lines.append(
        "  Providers: "
        + (", ".join(provider_label(name) for name in configured) if configured else "none configured")
    )
    lines.append(f"  Plugins:   {len(plugins)} loaded")
    lines.append(f"  Runtime:   state {STATE_ROOT} · cache {CACHE_ROOT}")
    lines.append(f"  UI state:  {UI_STATE_DIR}")
    lines.append(f"  Plugins:   {PLUGINS_DIR}")
    lines.append(f"  Rebirth:   {rebirth_status_summary()}")
    suspicious_plugins = sum(1 for item in plugin_audit if item["warnings"])
    if suspicious_plugins:
        lines.append(f"  Plugin audit: {suspicious_plugins} plugin(s) need attention")
    lines.append("")
    lines.append("Checks")

    warnings: list[str] = []
    suggestions: list[str] = []

    if env_file is None:
        warnings.append("No .env file found in the repo or Lumi home.")
        suggestions.append("Create ~/Lumi/.env and add at least one provider API key.")
    if not configured:
        warnings.append("No configured providers detected.")
        suggestions.append("Add a provider key and run /model to verify routing.")
    if not profile.project_context_path:
        warnings.append("No LUMI.md project context file found.")
        suggestions.append("Add LUMI.md so Lumi can pick up project conventions.")
    if not profile.verification_commands:
        warnings.append("No verification commands detected for this repo.")
        suggestions.append("Add tests or lint/typecheck config so agent runs can verify changes.")
    if not plugins:
        suggestions.append("Use ~/Lumi/plugins for safe custom commands if you extend Lumi often.")
    elif suspicious_plugins:
        warnings.append("Some plugins use risky APIs without matching declared permissions.")
        suggestions.append("Run /plugins audit and align plugin metadata with actual capabilities.")

    if profile.frameworks:
        lines.append(f"  Detected stack: {', '.join(profile.frameworks)}")
    if profile.languages:
        lines.append(f"  Detected languages: {', '.join(profile.languages)}")
    if profile.package_manager:
        lines.append(f"  Package manager: {profile.package_manager}")
    if profile.source_directories:
        lines.append(f"  Source dirs: {', '.join(profile.source_directories)}")
    if profile.test_directories:
        lines.append(f"  Test dirs: {', '.join(profile.test_directories)}")
    if profile.entrypoints:
        lines.append(f"  Entrypoints: {', '.join(profile.entrypoints)}")
    if profile.config_files:
        lines.append(f"  Config files: {', '.join(profile.config_files)}")
    configured_labels = [item.label for item in provider_health if item.configured]
    if configured_labels:
        lines.append(f"  Ready providers: {', '.join(configured_labels)}")
    vision_ready = _capability_ready_labels(provider_health, "vision")
    voice_ready = _capability_ready_labels(provider_health, "audio_transcription")
    if vision_ready:
        lines.append(f"  Vision-ready: {', '.join(vision_ready)}")
    if voice_ready:
        lines.append(f"  Voice-ready: {', '.join(voice_ready)}")

    lines.append("")
    lines.append("Warnings")
    if warnings:
        for warning in warnings:
            lines.append(f"  - {warning}")
    else:
        lines.append("  - none")

    lines.append("")
    lines.append("Next steps")
    if suggestions:
        for suggestion in suggestions[:5]:
            lines.append(f"  - {suggestion}")
    else:
        lines.append("  - Lumi looks healthy for this workspace.")

    return "\n".join(lines)


def build_onboarding_report(
    *,
    base_dir: Path | None = None,
    configured_providers: list[str] | None = None,
) -> str:
    root = (base_dir or Path.cwd()).resolve()
    profile = inspect_workspace(root)
    configured = configured_providers or []
    provider_health = provider_health_snapshot(has_ollama="ollama" in configured)
    ready = [item.label for item in provider_health if item.configured]
    vision_ready = _capability_ready_labels(provider_health, "vision")
    voice_ready = _capability_ready_labels(provider_health, "audio_transcription")
    hints = build_onboarding_hints(profile)

    lines = ["Lumi onboarding", ""]
    lines.append(render_workspace_overview(profile))
    lines.append("")
    lines.append("Ready now")
    lines.append("  Providers: " + (", ".join(ready) if ready else "none configured"))
    lines.append("  Env file:  " + (str(_find_env_file(root)) if _find_env_file(root) else "missing"))
    lines.append("  Runtime:   state " + str(STATE_ROOT))
    lines.append("  Cache:     " + str(CACHE_ROOT))
    lines.append("  Commands:  /status, /doctor, /rebirth, /model, /agent, /git review")
    lines.append(
        "  Media:     vision "
        + (", ".join(vision_ready) if vision_ready else "none")
        + " · voice "
        + (", ".join(voice_ready) if voice_ready else "none")
    )
    lines.append("")
    lines.append("Next steps")
    if hints:
        for hint in hints:
            lines.append(f"  - {hint}")
    else:
        lines.append("  - Workspace shape looks healthy for Lumi.")
    lines.append("")
    lines.append("Shortcuts")
    lines.append("  - Ctrl+N opens the provider/model picker")
    lines.append("  - Ctrl+G toggles the starter panel")
    lines.append("  - Esc cancels pending UI and review states")
    lines.append("")
    lines.append("Useful commands")
    lines.append("  - /image <path> [question]")
    lines.append("  - /voice [seconds]")
    lines.append("  - /plugins inspect")
    lines.append("")
    lines.append("Starter prompts")
    lines.append("  - review the repo and tell me where to start")
    lines.append("  - inspect the changed files and summarize risks")
    lines.append("  - create a folder named api and add main.py inside it")
    return "\n".join(lines)
