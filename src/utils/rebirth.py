"""Lumi - rebirth capability profiling helpers."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REBIRTH_PROFILE_PATH = PROJECT_ROOT / "configs" / "rebirth_profile.json"


@dataclass(frozen=True)
class RebirthCapability:
    key: str
    name: str
    command: str
    detail: str
    ready: bool


def _module_ready(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _file_ready(path: Path) -> bool:
    return path.exists()


def load_rebirth_profile() -> dict[str, Any]:
    default_profile: dict[str, Any] = {
        "name": "Lumi - rebirth",
        "version": 1,
        "defaults": {
            "response_mode": "detailed",
            "compact": False,
            "guardian_enabled": True,
        },
        "quickstart": ["/doctor", "/benchmark", "/rebirth", "/mode vessel codex"],
    }
    try:
        if not REBIRTH_PROFILE_PATH.exists():
            return default_profile
        payload = json.loads(REBIRTH_PROFILE_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return default_profile
        merged = dict(default_profile)
        merged.update(payload)
        defaults = dict(default_profile["defaults"])
        incoming_defaults = payload.get("defaults")
        if isinstance(incoming_defaults, dict):
            defaults.update(incoming_defaults)
        merged["defaults"] = defaults
        quickstart = payload.get("quickstart")
        if not isinstance(quickstart, list) or not quickstart:
            merged["quickstart"] = default_profile["quickstart"]
        return merged
    except Exception:
        return default_profile


def collect_rebirth_capabilities() -> list[RebirthCapability]:
    mode_count = 0
    try:
        from src.tui.mode_registry import MODE_CLI_REGISTRY

        mode_count = len(MODE_CLI_REGISTRY)
    except Exception:
        mode_count = 0

    capabilities = [
        RebirthCapability(
            key="agent",
            name="Grounded Agent Execution",
            command="/agent",
            detail="Structured multi-step planning with rollback guards",
            ready=_module_ready("src.agents.agent"),
        ),
        RebirthCapability(
            key="council",
            name="Parallel Council Reasoning",
            command="/council",
            detail="5-agent synthesis workflow for hard coding tasks",
            ready=_module_ready("src.agents.council"),
        ),
        RebirthCapability(
            key="actions",
            name="Deterministic Action Schema",
            command="/agent",
            detail="Typed action contracts for safe planner execution",
            ready=_module_ready("src.agents.action_schema"),
        ),
        RebirthCapability(
            key="files",
            name="Filesystem Autopilot + Undo",
            command="/fs, /undo",
            detail="Natural-language file operations with undo records",
            ready=_module_ready("src.utils.filesystem"),
        ),
        RebirthCapability(
            key="plugins",
            name="Trusted Plugin Runtime",
            command="/plugins, /permissions",
            detail="Manifest-based trust and permission audit pipeline",
            ready=_module_ready("src.utils.plugins") and _file_ready(PROJECT_ROOT / "plugins"),
        ),
        RebirthCapability(
            key="vessel",
            name="External CLI Vessel Handoff",
            command="/mode vessel <name>",
            detail=f"{mode_count} external coding CLIs registered",
            ready=mode_count >= 5,
        ),
        RebirthCapability(
            key="rag",
            name="Local Codebase RAG",
            command="/index, /rag",
            detail="Local semantic indexing and retrieval over repo files",
            ready=_module_ready("src.tools.rag"),
        ),
        RebirthCapability(
            key="mcp",
            name="MCP Tool Bridge",
            command="/mcp ...",
            detail="Model Context Protocol client integration",
            ready=_module_ready("src.tools.mcp"),
        ),
        RebirthCapability(
            key="benchmark",
            name="Benchmark + Gate",
            command="/benchmark",
            detail="Scenario benchmark suite plus CI regression gate",
            ready=_file_ready(PROJECT_ROOT / "scripts" / "benchmark_gate.py")
            and _file_ready(PROJECT_ROOT / "configs" / "benchmark_gate.json"),
        ),
        RebirthCapability(
            key="health",
            name="Health Diagnostics",
            command="/status, /doctor, /onboard",
            detail="Workspace and provider diagnostics with onboarding hints",
            ready=_module_ready("src.utils.system_reports"),
        ),
        RebirthCapability(
            key="memory",
            name="Persistent Memory Stack",
            command="/remember, /memory, /todo, /note",
            detail="Short-term, long-term, notes, and task memory support",
            ready=_module_ready("src.memory.longterm") and _module_ready("src.agents.task_memory"),
        ),
        RebirthCapability(
            key="media",
            name="Multi-Modal Context",
            command="/image, /voice, /web, /pdf, /data",
            detail="Image, voice, web, PDF, and structured data ingest",
            ready=_module_ready("src.tui.media") and _module_ready("src.utils.web"),
        ),
    ]
    return capabilities


def rebirth_readiness() -> tuple[int, int, float]:
    capabilities = collect_rebirth_capabilities()
    total = len(capabilities)
    ready = sum(1 for item in capabilities if item.ready)
    ratio = (ready / total) if total else 0.0
    return ready, total, ratio


def rebirth_status_summary() -> str:
    ready, total, ratio = rebirth_readiness()
    tier = "parity-ready" if ratio >= 0.95 else "in-progress"
    return f"{ready}/{total} capabilities ready ({ratio:.0%}) · {tier}"


def render_rebirth_report() -> str:
    profile = load_rebirth_profile()
    capabilities = collect_rebirth_capabilities()
    ready, total, ratio = rebirth_readiness()

    lines = [
        f"{profile.get('name', 'Lumi - rebirth')} capability matrix",
        f"  Readiness: {ready}/{total} ({ratio:.0%})",
        "",
    ]
    for capability in capabilities:
        state = "ok" if capability.ready else "missing"
        lines.append(
            f"  [{state}] {capability.name:<32} {capability.command:<24} {capability.detail}"
        )

    quickstart = profile.get("quickstart", [])
    if isinstance(quickstart, list) and quickstart:
        lines.append("")
        lines.append("Quickstart")
        for step in quickstart[:6]:
            lines.append(f"  - {step}")

    return "\n".join(lines)
