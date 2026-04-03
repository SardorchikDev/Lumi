"""Persistent per-workspace runtime configuration for Lumi."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.chat.inference_controls import normalize_reasoning_effort
from src.config import DATA_DIR

RUNTIME_CONFIG_DIR = DATA_DIR / "runtime"
_TRUE_VALUES = {"1", "true", "yes", "on", "enable", "enabled"}
_FALSE_VALUES = {"0", "false", "no", "off", "disable", "disabled"}
_ALLOWED_PERMISSION_MODES = {"default", "plan", "auto", "bypass"}
_ALLOWED_PRIVACY_MODES = {"standard", "strict", "offline"}


@dataclass(frozen=True)
class RuntimeConfig:
    workspace: str
    updated_at: str
    extra_dirs: tuple[str, ...] = ()
    fast_mode: bool = False
    brief_mode: bool = False
    compact_mode: bool = False
    multiline: bool = False
    reasoning_effort: str = "medium"
    permission_mode: str = "default"
    privacy_mode: str = "standard"


_DEFAULTS = RuntimeConfig(workspace="", updated_at="")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _workspace_key(base_dir: Path | None = None) -> str:
    return str((base_dir or Path.cwd()).expanduser().resolve())


def _config_path(base_dir: Path | None = None) -> Path:
    root = _workspace_key(base_dir)
    digest = hashlib.sha1(root.encode("utf-8")).hexdigest()[:12]
    RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return RUNTIME_CONFIG_DIR / f"{digest}.json"


def _coerce_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ValueError(f"Expected one of: {', '.join(sorted(_TRUE_VALUES | _FALSE_VALUES))}")


def _normalize_extra_dirs(base_dir: Path, values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or ():
        candidate = Path(str(raw)).expanduser()
        if not candidate.is_absolute():
            candidate = (base_dir / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if candidate == base_dir:
            continue
        if not candidate.exists() or not candidate.is_dir():
            continue
        text = str(candidate)
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def load_runtime_config(base_dir: Path | None = None) -> RuntimeConfig:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    path = _config_path(root)
    if not path.exists():
        return RuntimeConfig(workspace=str(root), updated_at=_now())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RuntimeConfig(workspace=str(root), updated_at=_now())
    if not isinstance(payload, dict):
        return RuntimeConfig(workspace=str(root), updated_at=_now())
    return RuntimeConfig(
        workspace=str(payload.get("workspace") or str(root)),
        updated_at=str(payload.get("updated_at") or _now()),
        extra_dirs=_normalize_extra_dirs(root, payload.get("extra_dirs", [])),
        fast_mode=bool(payload.get("fast_mode", False)),
        brief_mode=bool(payload.get("brief_mode", False)),
        compact_mode=bool(payload.get("compact_mode", False)),
        multiline=bool(payload.get("multiline", False)),
        reasoning_effort=normalize_reasoning_effort(str(payload.get("reasoning_effort") or "medium")),
        permission_mode=str(payload.get("permission_mode") or "default"),
        privacy_mode=str(payload.get("privacy_mode") or "standard"),
    )


def save_runtime_config(config: RuntimeConfig, base_dir: Path | None = None) -> RuntimeConfig:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    normalized = RuntimeConfig(
        workspace=str(root),
        updated_at=_now(),
        extra_dirs=_normalize_extra_dirs(root, config.extra_dirs),
        fast_mode=bool(config.fast_mode),
        brief_mode=bool(config.brief_mode),
        compact_mode=bool(config.compact_mode),
        multiline=bool(config.multiline),
        reasoning_effort=normalize_reasoning_effort(config.reasoning_effort),
        permission_mode=config.permission_mode if config.permission_mode in _ALLOWED_PERMISSION_MODES else "default",
        privacy_mode=config.privacy_mode if config.privacy_mode in _ALLOWED_PRIVACY_MODES else "standard",
    )
    _config_path(root).write_text(json.dumps(asdict(normalized), indent=2, ensure_ascii=False), encoding="utf-8")
    return normalized


def reset_runtime_config(base_dir: Path | None = None) -> RuntimeConfig:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    return save_runtime_config(RuntimeConfig(workspace=str(root), updated_at=_now()), root)


def update_runtime_config(base_dir: Path | None = None, **updates: Any) -> RuntimeConfig:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    current = load_runtime_config(root)
    payload = asdict(current)
    payload.update(updates)
    if "reasoning_effort" in payload:
        payload["reasoning_effort"] = normalize_reasoning_effort(str(payload["reasoning_effort"] or "medium"))
    if "permission_mode" in payload and payload["permission_mode"] not in _ALLOWED_PERMISSION_MODES:
        raise ValueError(f"permission mode must be one of: {', '.join(sorted(_ALLOWED_PERMISSION_MODES))}")
    if "privacy_mode" in payload and payload["privacy_mode"] not in _ALLOWED_PRIVACY_MODES:
        raise ValueError(f"privacy mode must be one of: {', '.join(sorted(_ALLOWED_PRIVACY_MODES))}")
    return save_runtime_config(RuntimeConfig(**payload), root)


def add_context_directory(path_str: str, *, base_dir: Path | None = None) -> tuple[RuntimeConfig, Path]:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    candidate = Path(path_str).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError(f"Not a directory: {candidate}")
    current = load_runtime_config(root)
    extra_dirs = tuple(dict.fromkeys([*current.extra_dirs, str(candidate)]))
    updated = update_runtime_config(root, extra_dirs=extra_dirs)
    return updated, candidate


def remove_context_directory(path_str: str, *, base_dir: Path | None = None) -> tuple[RuntimeConfig, Path]:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    candidate = Path(path_str).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    current = load_runtime_config(root)
    extra_dirs = tuple(path for path in current.extra_dirs if path != str(candidate))
    updated = update_runtime_config(root, extra_dirs=extra_dirs)
    return updated, candidate


def iter_context_roots(base_dir: Path | None = None) -> tuple[Path, ...]:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    current = load_runtime_config(root)
    roots: list[Path] = [root]
    seen = {str(root)}
    for item in current.extra_dirs:
        path = Path(item).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            continue
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        roots.append(path)
    return tuple(roots)


def display_context_path(path: Path, *, base_dir: Path | None = None) -> str:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def parse_runtime_config_update(key: str, value: str) -> dict[str, Any]:
    normalized_key = key.strip().lower().replace("-", "_")
    raw = value.strip()
    if normalized_key in {"effort", "reasoning_effort"}:
        return {"reasoning_effort": normalize_reasoning_effort(raw)}
    if normalized_key in {"compact", "compact_mode"}:
        return {"compact_mode": _coerce_bool(raw)}
    if normalized_key == "multiline":
        return {"multiline": _coerce_bool(raw)}
    if normalized_key in {"brief", "brief_mode"}:
        return {"brief_mode": _coerce_bool(raw)}
    if normalized_key in {"fast", "fast_mode"}:
        return {"fast_mode": _coerce_bool(raw)}
    if normalized_key in {"permissions", "permission_mode"}:
        lowered = raw.lower()
        if lowered not in _ALLOWED_PERMISSION_MODES:
            raise ValueError(f"permission mode must be one of: {', '.join(sorted(_ALLOWED_PERMISSION_MODES))}")
        return {"permission_mode": lowered}
    if normalized_key in {"privacy", "privacy_mode"}:
        lowered = raw.lower()
        if lowered not in _ALLOWED_PRIVACY_MODES:
            raise ValueError(f"privacy mode must be one of: {', '.join(sorted(_ALLOWED_PRIVACY_MODES))}")
        return {"privacy_mode": lowered}
    raise ValueError(
        "Unknown setting. Use one of: effort, compact, multiline, brief, fast, permissions, privacy"
    )


def render_runtime_config_report(
    *,
    base_dir: Path | None = None,
    provider: str = "",
    model: str = "",
    compact_mode: bool | None = None,
    multiline: bool | None = None,
    reasoning_effort: str | None = None,
    brief_mode: bool | None = None,
    fast_mode: bool | None = None,
) -> str:
    root = (base_dir or Path.cwd()).expanduser().resolve()
    config = load_runtime_config(root)
    effective_compact = config.compact_mode if compact_mode is None else bool(compact_mode)
    effective_multiline = config.multiline if multiline is None else bool(multiline)
    effective_effort = normalize_reasoning_effort(reasoning_effort or config.reasoning_effort)
    effective_brief = config.brief_mode if brief_mode is None else bool(brief_mode)
    effective_fast = config.fast_mode if fast_mode is None else bool(fast_mode)

    lines = ["Lumi config", f"  Workspace: {root}"]
    if provider or model:
        lines.append(f"  Model:     {provider or 'unknown'} · {model or 'unknown'}")
    lines.append(f"  Effort:    {effective_effort}")
    lines.append(f"  Compact:   {'on' if effective_compact else 'off'}")
    lines.append(f"  Multiline: {'on' if effective_multiline else 'off'}")
    lines.append(f"  Brief:     {'on' if effective_brief else 'off'}")
    lines.append(f"  Fast:      {'on' if effective_fast else 'off'}")
    lines.append(f"  Perms:     {config.permission_mode}")
    lines.append(f"  Privacy:   {config.privacy_mode}")
    lines.append(f"  Updated:   {config.updated_at}")
    lines.append("")
    lines.append("Context directories")
    if config.extra_dirs:
        for item in config.extra_dirs:
            lines.append(f"  - {item}")
    else:
        lines.append("  - none")
    lines.append("")
    lines.append("Next")
    lines.append("  - /config set effort high")
    lines.append("  - /add-dir ../shared-lib")
    lines.append("  - /files")
    return "\n".join(lines)
