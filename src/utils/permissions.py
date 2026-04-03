"""General tool permission rules for Lumi."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

GLOBAL_PERMISSION_PATH = Path.home() / ".config" / "lumi" / "permissions.json"
PROJECT_PERMISSION_PATH = ".lumi/permissions.json"
PERMISSION_MODES = {"ask", "auto", "strict"}


@dataclass(frozen=True)
class PermissionConfig:
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    mode: str = "ask"
    source: str = ""


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str
    matched_rule: str = ""
    persist_hint: str = ""


@dataclass(frozen=True)
class PermissionRequest:
    tool_name: str
    value: str
    display: str


@dataclass(frozen=True)
class PermissionView:
    global_config: PermissionConfig
    project_config: PermissionConfig
    effective: PermissionConfig
    global_path: Path
    project_path: Path


@dataclass
class PermissionFilePayload:
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)
    mode: str = "ask"


class PermissionError(RuntimeError):
    """Raised when a tool invocation is denied by policy."""


class PermissionRequired(RuntimeError):  # noqa: N818
    """Raised when a tool invocation requires explicit user approval."""

    def __init__(self, request: PermissionRequest, reason: str = "requires approval") -> None:
        super().__init__(reason)
        self.request = request
        self.reason = reason


def _normalize_rule(rule: str) -> str:
    return str(rule or "").strip()


def _normalize_rules(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values or ():
        rule = _normalize_rule(raw)
        if not rule or rule in seen:
            continue
        seen.add(rule)
        ordered.append(rule)
    return tuple(ordered)


def _normalize_mode(value: str | None) -> str:
    mode = str(value or "ask").strip().lower()
    return mode if mode in PERMISSION_MODES else "ask"


def _read_permission_file(path: Path) -> PermissionConfig:
    if not path.exists():
        return PermissionConfig(source=str(path))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PermissionConfig(source=str(path))
    if not isinstance(payload, dict):
        return PermissionConfig(source=str(path))
    return PermissionConfig(
        allow=_normalize_rules(payload.get("allow")),
        deny=_normalize_rules(payload.get("deny")),
        mode=_normalize_mode(str(payload.get("mode") or "ask")),
        source=str(path),
    )


def _merge_configs(global_config: PermissionConfig, project_config: PermissionConfig) -> PermissionConfig:
    mode = project_config.mode if project_config.source and Path(project_config.source).exists() else global_config.mode
    if mode not in PERMISSION_MODES:
        mode = "ask"
    return PermissionConfig(
        allow=_normalize_rules([*global_config.allow, *project_config.allow]),
        deny=_normalize_rules([*global_config.deny, *project_config.deny]),
        mode=mode,
        source=project_config.source or global_config.source,
    )


def load_permission_view(base_dir: Path | None = None) -> PermissionView:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    global_path = GLOBAL_PERMISSION_PATH
    project_path = root / PROJECT_PERMISSION_PATH
    global_config = _read_permission_file(global_path)
    project_config = _read_permission_file(project_path)
    effective = _merge_configs(global_config, project_config)
    return PermissionView(
        global_config=global_config,
        project_config=project_config,
        effective=effective,
        global_path=global_path,
        project_path=project_path,
    )


def load_permission_config(base_dir: Path | None = None) -> PermissionConfig:
    return load_permission_view(base_dir).effective


def _write_permission_file(path: Path, config: PermissionConfig) -> PermissionConfig:
    payload = PermissionFilePayload(
        allow=list(_normalize_rules(config.allow)),
        deny=list(_normalize_rules(config.deny)),
        mode=_normalize_mode(config.mode),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(payload), indent=2, ensure_ascii=False), encoding="utf-8")
    return PermissionConfig(
        allow=tuple(payload.allow),
        deny=tuple(payload.deny),
        mode=payload.mode,
        source=str(path),
    )


def save_permission_config(
    config: PermissionConfig,
    *,
    base_dir: Path | None = None,
    project: bool = True,
) -> PermissionConfig:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    path = (root / PROJECT_PERMISSION_PATH) if project else GLOBAL_PERMISSION_PATH
    return _write_permission_file(path, config)


def add_permission_rule(
    kind: str,
    rule: str,
    *,
    base_dir: Path | None = None,
    project: bool = True,
) -> PermissionConfig:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in {"allow", "deny"}:
        raise ValueError("kind must be allow or deny")
    raw = _normalize_rule(rule)
    if not raw:
        raise ValueError("permission rule cannot be empty")
    current = _read_permission_file(((base_dir or Path.cwd()).resolve() / PROJECT_PERMISSION_PATH) if project else GLOBAL_PERMISSION_PATH)
    allow = list(current.allow)
    deny = list(current.deny)
    target = allow if normalized_kind == "allow" else deny
    if raw not in target:
        target.append(raw)
    return save_permission_config(
        PermissionConfig(allow=tuple(allow), deny=tuple(deny), mode=current.mode, source=current.source),
        base_dir=base_dir,
        project=project,
    )


def remove_permission_rule(
    kind: str,
    rule: str,
    *,
    base_dir: Path | None = None,
    project: bool = True,
) -> PermissionConfig:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in {"allow", "deny"}:
        raise ValueError("kind must be allow or deny")
    raw = _normalize_rule(rule)
    current = _read_permission_file(((base_dir or Path.cwd()).resolve() / PROJECT_PERMISSION_PATH) if project else GLOBAL_PERMISSION_PATH)
    allow = [item for item in current.allow if item != raw]
    deny = [item for item in current.deny if item != raw]
    return save_permission_config(
        PermissionConfig(allow=tuple(allow), deny=tuple(deny), mode=current.mode, source=current.source),
        base_dir=base_dir,
        project=project,
    )


def set_permission_mode(
    mode: str,
    *,
    base_dir: Path | None = None,
    project: bool = True,
) -> PermissionConfig:
    normalized_mode = _normalize_mode(mode)
    current = _read_permission_file(((base_dir or Path.cwd()).resolve() / PROJECT_PERMISSION_PATH) if project else GLOBAL_PERMISSION_PATH)
    return save_permission_config(
        PermissionConfig(allow=current.allow, deny=current.deny, mode=normalized_mode, source=current.source),
        base_dir=base_dir,
        project=project,
    )


def _matches_rule(rule: str, request: PermissionRequest) -> bool:
    normalized_rule = _normalize_rule(rule)
    if not normalized_rule:
        return False
    if ":" not in normalized_rule:
        return fnmatch.fnmatchcase(f"{request.tool_name}:{request.value}", normalized_rule)
    tool_pattern, value_pattern = normalized_rule.split(":", 1)
    if not fnmatch.fnmatchcase(request.tool_name, tool_pattern or "*"):
        return False
    return fnmatch.fnmatchcase(request.value, value_pattern or "*")


def evaluate_permission(
    tool_name: str,
    value: str,
    *,
    base_dir: Path | None = None,
    display: str | None = None,
) -> PermissionDecision:
    request = PermissionRequest(
        tool_name=str(tool_name or "").strip(),
        value=str(value or "").strip(),
        display=str(display or value or tool_name).strip(),
    )
    config = load_permission_config(base_dir)
    for rule in config.deny:
        if _matches_rule(rule, request):
            return PermissionDecision(False, "denied by rule", matched_rule=rule)
    for rule in config.allow:
        if _matches_rule(rule, request):
            return PermissionDecision(True, "allowed by rule", matched_rule=rule)
    match config.mode:
        case "auto":
            return PermissionDecision(True, "allowed by auto mode")
        case "strict":
            return PermissionDecision(False, "blocked by strict mode")
        case _:
            return PermissionDecision(False, "requires approval", persist_hint=f"{request.tool_name}:{request.value}")


def render_permission_report(
    *,
    base_dir: Path | None = None,
) -> str:
    view = load_permission_view(base_dir)
    effective = view.effective
    lines = [
        "Tool permissions",
        f"  Mode:    {effective.mode}",
        f"  Global:  {view.global_path}",
        f"  Project: {view.project_path}",
        "",
        "Effective allow rules",
    ]
    if effective.allow:
        lines.extend(f"  - {rule}" for rule in effective.allow)
    else:
        lines.append("  - none")
    lines.append("")
    lines.append("Effective deny rules")
    if effective.deny:
        lines.extend(f"  - {rule}" for rule in effective.deny)
    else:
        lines.append("  - none")
    lines.append("")
    lines.append("Commands")
    lines.append("  /permissions")
    lines.append("  /permissions mode <ask|auto|strict>")
    lines.append("  /permissions add <allow|deny> \"tool:pattern\"")
    lines.append("  /permissions rm <allow|deny> \"tool:pattern\"")
    lines.append("  /permissions plugins")
    return "\n".join(lines)


def permission_examples() -> tuple[str, ...]:
    return (
        'edit_file:**/src/**',
        'run_shell:pytest *',
        'run_shell:ruff *',
        'git_commit:*',
        'run_shell:rm -rf *',
        'write_file:**/.env',
    )


__all__ = [
    "GLOBAL_PERMISSION_PATH",
    "PROJECT_PERMISSION_PATH",
    "PERMISSION_MODES",
    "PermissionConfig",
    "PermissionDecision",
    "PermissionError",
    "PermissionRequired",
    "PermissionRequest",
    "add_permission_rule",
    "evaluate_permission",
    "load_permission_config",
    "load_permission_view",
    "permission_examples",
    "remove_permission_rule",
    "render_permission_report",
    "save_permission_config",
    "set_permission_mode",
]
