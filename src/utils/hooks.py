"""Deterministic lifecycle hooks for Lumi."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.config import LUMI_HOME

HOOK_EVENTS: tuple[str, ...] = (
    "before_message",
    "after_response",
    "before_command",
    "after_command",
)


@dataclass(frozen=True)
class HookSpec:
    event: str
    name: str
    command: str
    source: Path
    timeout: int = 20
    required: bool = False
    enabled: bool = True
    cwd: str = ""


@dataclass(frozen=True)
class HookResult:
    spec: HookSpec
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    blocked: bool = False


def hook_config_paths(base_dir: Path | None = None) -> tuple[Path, ...]:
    root = (base_dir or Path.cwd()).resolve()
    return (
        (LUMI_HOME / "configs" / "hooks.json").resolve(),
        (root / "hooks.json").resolve(),
        (root / ".lumi" / "hooks.json").resolve(),
    )


def _read_hook_file(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    hooks = raw.get("hooks")
    if isinstance(hooks, dict):
        return hooks
    return raw


def _parse_hook_spec(event: str, raw_entry: object, *, source: Path, index: int) -> HookSpec | None:
    if isinstance(raw_entry, str):
        command = raw_entry.strip()
        if not command:
            return None
        return HookSpec(
            event=event,
            name=f"{source.stem}:{event}:{index}",
            command=command,
            source=source,
        )
    if not isinstance(raw_entry, dict):
        return None
    command = str(raw_entry.get("command") or "").strip()
    if not command:
        return None
    timeout = int(raw_entry.get("timeout") or 20)
    return HookSpec(
        event=event,
        name=str(raw_entry.get("name") or f"{source.stem}:{event}:{index}"),
        command=command,
        source=source,
        timeout=max(1, timeout),
        required=bool(raw_entry.get("required", False)),
        enabled=bool(raw_entry.get("enabled", True)),
        cwd=str(raw_entry.get("cwd") or ""),
    )


def load_hook_specs(base_dir: Path | None = None) -> list[HookSpec]:
    specs: list[HookSpec] = []
    for path in hook_config_paths(base_dir):
        if not path.exists():
            continue
        raw = _read_hook_file(path)
        for event in HOOK_EVENTS:
            entries = raw.get(event)
            if entries is None:
                continue
            if isinstance(entries, (str, dict)):
                entries = [entries]
            if not isinstance(entries, list):
                continue
            for idx, entry in enumerate(entries, start=1):
                spec = _parse_hook_spec(event, entry, source=path, index=idx)
                if spec is not None and spec.enabled:
                    specs.append(spec)
    return specs


def hooks_for_event(event: str, *, base_dir: Path | None = None) -> list[HookSpec]:
    normalized = (event or "").strip().lower()
    return [spec for spec in load_hook_specs(base_dir) if spec.event == normalized]


def render_hook_report(*, base_dir: Path | None = None, detail: bool = False) -> str:
    hooks = load_hook_specs(base_dir)
    lines = ["Hooks"]
    if not hooks:
        lines.append("  none configured")
        lines.append("  add hooks.json or .lumi/hooks.json to enable lifecycle automation")
        return "\n".join(lines)

    per_event = {event: hooks_for_event(event, base_dir=base_dir) for event in HOOK_EVENTS}
    lines.append(f"  discovered: {len(hooks)}")
    for event in HOOK_EVENTS:
        lines.append(f"  {event}: {len(per_event[event])}")
    lines.append("")
    if detail:
        for spec in hooks:
            lines.append(
                f"  {spec.event} · {spec.name}"
                f"  [timeout={spec.timeout}s{' required' if spec.required else ''}]"
            )
            lines.append(f"    {spec.command}")
            lines.append(f"    source: {spec.source}")
    else:
        lines.append("  next: /hooks inspect")
    return "\n".join(lines)


def run_hooks(
    event: str,
    *,
    base_dir: Path | None = None,
    command: str = "",
    args: str = "",
    user_input: str = "",
    response: str = "",
) -> list[HookResult]:
    root = (base_dir or Path.cwd()).resolve()
    env = os.environ.copy()
    env.update(
        {
            "LUMI_HOOK_EVENT": event,
            "LUMI_HOOK_COMMAND": command,
            "LUMI_HOOK_ARGS": args,
            "LUMI_HOOK_INPUT": user_input,
            "LUMI_HOOK_RESPONSE": response,
            "LUMI_HOOK_WORKSPACE": str(root),
        }
    )
    results: list[HookResult] = []
    for spec in hooks_for_event(event, base_dir=root):
        cwd = Path(spec.cwd).expanduser().resolve() if spec.cwd else root
        try:
            proc = subprocess.run(
                ["sh", "-lc", spec.command],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=spec.timeout,
                check=False,
            )
            ok = proc.returncode == 0
            results.append(
                HookResult(
                    spec=spec,
                    ok=ok,
                    stdout=proc.stdout.strip(),
                    stderr=proc.stderr.strip(),
                    returncode=proc.returncode,
                    blocked=spec.required and not ok,
                )
            )
        except Exception as exc:
            results.append(
                HookResult(
                    spec=spec,
                    ok=False,
                    stdout="",
                    stderr=str(exc),
                    returncode=1,
                    blocked=spec.required,
                )
            )
    return results
