"""Workbench orchestration for Lumi v0.7.5: Beacon."""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import re
import subprocess
import tempfile
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import CACHE_ROOT, DATA_DIR
from src.memory.short_term import ShortTermMemory
from src.utils.git_tools import run_git_subcommand
from src.utils.project_context import find_project_context_file
from src.utils.repo_profile import find_relevant_paths, inspect_workspace, render_workspace_overview
from src.utils.runtime_config import display_context_path, iter_context_roots

WORKBENCH_NAME = "Beacon"
WORKBENCH_VERSION = "0.7.5"
WORKBENCH_TITLE = f"Lumi v{WORKBENCH_VERSION}: {WORKBENCH_NAME}"
WORKBENCH_STATE_DIR = DATA_DIR / "workbench"
WORKBENCH_CACHE_DIR = CACHE_ROOT / "workbench"
PROJECT_MEMORY_PATH = WORKBENCH_STATE_DIR / "project_memory.json"
MAX_JOB_HISTORY = 24
MAX_JOB_LOG_LINES = 5
MAX_JOB_LOG_CHARS = 1600
MAX_INDEX_FILES = 220
MAX_SYMBOLS = 600
MAX_IMPORTS_PER_FILE = 12
MAX_HOTSPOTS = 10
MAX_CONTEXT_SNIPPETS = 4
MAX_CONTEXT_CHARS = 700
MAX_REFERENCE_RESULTS = 40
MAX_IMPACT_RESULTS = 12

_SYMBOL_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    ".py": (
        ("class", r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)"),
    ),
    ".js": (
        ("class", r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\("),
    ),
    ".ts": (
        ("class", r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("interface", r"^\s*(?:export\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("type", r"^\s*(?:export\s+)?type\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\("),
    ),
    ".tsx": (
        ("component", r"^\s*(?:export\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("component", r"^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\("),
    ),
    ".jsx": (
        ("component", r"^\s*(?:export\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("component", r"^\s*(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\("),
    ),
    ".go": (
        ("type", r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)"),
    ),
    ".rs": (
        ("struct", r"^\s*(?:pub\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("enum", r"^\s*(?:pub\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)"),
    ),
    ".sh": (
        ("function", r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{"),
    ),
}

_IMPORT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*from\s+([A-Za-z0-9_./-]+)\s+import\s+", re.MULTILINE),
    re.compile(r"^\s*import\s+([A-Za-z0-9_.,\s/-]+)$", re.MULTILINE),
    re.compile(r"from\s+[\"']([^\"']+)[\"']", re.MULTILINE),
    re.compile(r"require\([\"']([^\"']+)[\"']\)", re.MULTILINE),
    re.compile(r"^\s*use\s+([A-Za-z0-9_:]+)", re.MULTILINE),
)

_RISK_KEYWORDS = {
    "delete": 3,
    "remove": 3,
    "drop": 3,
    "overwrite": 3,
    "rewrite": 2,
    "rename": 2,
    "migrate": 2,
    "release": 2,
    "ship": 2,
    "deploy": 3,
    "workflow": 2,
    "ci": 2,
    "auth": 2,
    "billing": 2,
    "security": 2,
}


@dataclass(frozen=True)
class SymbolRecord:
    name: str
    kind: str
    path: str
    line: int


@dataclass(frozen=True)
class ReferenceRecord:
    path: str
    line: int
    snippet: str


@dataclass(frozen=True)
class RepoIntelligence:
    workspace: str
    generated_at: str
    languages: tuple[str, ...]
    frameworks: tuple[str, ...]
    entrypoints: tuple[str, ...]
    config_files: tuple[str, ...]
    verification_commands: tuple[str, ...]
    changed_files: tuple[str, ...]
    relevant_files: tuple[str, ...]
    hotspots: tuple[str, ...]
    impact_files: tuple[str, ...]
    suggested_tests: tuple[str, ...]
    warnings: tuple[str, ...]
    context_digest: str
    symbol_index: tuple[SymbolRecord, ...] = ()
    dependency_graph: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def symbol_count(self) -> int:
        return len(self.symbol_index)


@dataclass(frozen=True)
class ProjectMemoryProfile:
    workspace: str
    updated_at: str
    conventions: tuple[str, ...]
    decisions: tuple[str, ...]
    recent_runs: tuple[dict[str, Any], ...]
    artifact_history: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ArtifactBundle:
    commit_title: str
    pr_description: str
    release_notes: str
    changelog: str
    test_summary: str
    architecture_summary: str


@dataclass(frozen=True)
class WorkbenchPlan:
    mode: str
    objective: str
    dry_run: bool
    risk_level: str
    safety_warnings: tuple[str, ...]
    suggested_steps: tuple[str, ...]
    recommended_checks: tuple[str, ...]
    intelligence: RepoIntelligence
    project_memory: ProjectMemoryProfile
    artifacts: tuple[str, ...]


@dataclass(frozen=True)
class WorkbenchRunResult:
    mode: str
    objective: str
    dry_run: bool
    summary: str
    risk_level: str
    touched_files: tuple[str, ...]
    failed_checks: tuple[str, ...]
    intelligence: RepoIntelligence
    project_memory: ProjectMemoryProfile
    artifacts: ArtifactBundle
    execution_log: str = ""


@dataclass(frozen=True)
class WorkbenchJobRecord:
    id: str
    workspace: str
    mode: str
    objective: str
    dry_run: bool
    status: str
    stage: str
    risk: str
    summary: str
    created_at: str
    updated_at: str
    finished_at: str = ""
    touched_files: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()
    log_excerpt: str = ""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _workspace_key(base_dir: Path | None = None) -> str:
    return str((base_dir or Path.cwd()).expanduser().resolve())


def _workspace_hash(base_dir: Path | None = None) -> str:
    return hashlib.sha1(_workspace_key(base_dir).encode("utf-8")).hexdigest()[:12]


def _cache_path(base_dir: Path | None = None) -> Path:
    WORKBENCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return WORKBENCH_CACHE_DIR / f"{_workspace_hash(base_dir)}.json"


def _jobs_path(base_dir: Path | None = None) -> Path:
    jobs_dir = WORKBENCH_STATE_DIR / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    return jobs_dir / f"{_workspace_hash(base_dir)}.json"


def _read_text(path: Path, limit: int | None = None) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if limit is not None:
        return text[:limit]
    return text


def _compact_job_log(text: str) -> str:
    cleaned_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not cleaned_lines:
        return ""
    excerpt = "\n".join(cleaned_lines[:MAX_JOB_LOG_LINES])
    return excerpt[:MAX_JOB_LOG_CHARS]


def create_workbench_job(
    mode: str,
    objective: str,
    *,
    base_dir: Path | None = None,
    dry_run: bool = False,
    job_id: str = "",
) -> WorkbenchJobRecord:
    now = _now()
    normalized_mode = (mode or "build").strip().lower() or "build"
    return WorkbenchJobRecord(
        id=job_id or f"wb-{_workspace_hash(base_dir)}-{int(datetime.now().timestamp())}",
        workspace=_workspace_key(base_dir),
        mode=normalized_mode,
        objective=" ".join((objective or normalized_mode).split())[:220],
        dry_run=bool(dry_run),
        status="queued",
        stage="queued",
        risk="",
        summary="",
        created_at=now,
        updated_at=now,
    )


def update_workbench_job(
    job: WorkbenchJobRecord,
    *,
    status: str | None = None,
    stage: str | None = None,
    risk: str | None = None,
    summary: str | None = None,
    touched_files: tuple[str, ...] | list[str] | None = None,
    failed_checks: tuple[str, ...] | list[str] | None = None,
    log_excerpt: str | None = None,
) -> WorkbenchJobRecord:
    now = _now()
    next_status = status or job.status
    finished_at = job.finished_at
    if next_status in {"done", "failed", "cancelled"}:
        finished_at = finished_at or now
    return WorkbenchJobRecord(
        id=job.id,
        workspace=job.workspace,
        mode=job.mode,
        objective=job.objective,
        dry_run=job.dry_run,
        status=next_status,
        stage=stage if stage is not None else job.stage,
        risk=risk if risk is not None else job.risk,
        summary=(summary if summary is not None else job.summary)[:320],
        created_at=job.created_at,
        updated_at=now,
        finished_at=finished_at,
        touched_files=tuple(dict.fromkeys(str(item) for item in (touched_files if touched_files is not None else job.touched_files)))[:16],
        failed_checks=tuple(dict.fromkeys(str(item) for item in (failed_checks if failed_checks is not None else job.failed_checks)))[:8],
        log_excerpt=_compact_job_log(log_excerpt if log_excerpt is not None else job.log_excerpt),
    )


def workbench_job_to_dict(job: WorkbenchJobRecord) -> dict[str, object]:
    return {
        "id": job.id,
        "workspace": job.workspace,
        "mode": job.mode,
        "objective": job.objective,
        "dry_run": job.dry_run,
        "status": job.status,
        "stage": job.stage,
        "risk": job.risk,
        "summary": job.summary,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "finished_at": job.finished_at,
        "touched_files": list(job.touched_files),
        "failed_checks": list(job.failed_checks),
        "log_excerpt": job.log_excerpt,
    }


def coerce_workbench_job(item: WorkbenchJobRecord | dict[str, Any] | None, *, base_dir: Path | None = None) -> WorkbenchJobRecord | None:
    if item is None:
        return None
    if isinstance(item, WorkbenchJobRecord):
        return item
    if not isinstance(item, dict):
        return None
    created_at = str(item.get("created_at") or item.get("updated_at") or _now())
    updated_at = str(item.get("updated_at") or created_at)
    finished_at = str(item.get("finished_at") or "")
    return WorkbenchJobRecord(
        id=str(item.get("id") or f"wb-{_workspace_hash(base_dir)}-{int(datetime.now().timestamp())}"),
        workspace=str(item.get("workspace") or _workspace_key(base_dir)),
        mode=str(item.get("mode") or "build"),
        objective=" ".join(str(item.get("objective") or "").split())[:220],
        dry_run=bool(item.get("dry_run", False)),
        status=str(item.get("status") or "queued"),
        stage=str(item.get("stage") or "queued"),
        risk=str(item.get("risk") or ""),
        summary=str(item.get("summary") or "")[:320],
        created_at=created_at,
        updated_at=updated_at,
        finished_at=finished_at,
        touched_files=tuple(str(entry) for entry in item.get("touched_files", []) if str(entry).strip())[:16],
        failed_checks=tuple(str(entry) for entry in item.get("failed_checks", []) if str(entry).strip())[:8],
        log_excerpt=_compact_job_log(str(item.get("log_excerpt") or "")),
    )


def load_workbench_jobs(base_dir: Path | None = None, *, limit: int = MAX_JOB_HISTORY) -> tuple[WorkbenchJobRecord, ...]:
    path = _jobs_path(base_dir)
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    jobs: list[WorkbenchJobRecord] = []
    for entry in payload:
        job = coerce_workbench_job(entry, base_dir=base_dir)
        if job is not None:
            jobs.append(job)
    jobs.sort(key=lambda item: item.updated_at, reverse=True)
    return tuple(jobs[:limit])


def save_workbench_job(job: WorkbenchJobRecord, *, base_dir: Path | None = None) -> tuple[WorkbenchJobRecord, ...]:
    root = Path(job.workspace) if job.workspace else (base_dir or Path.cwd()).resolve()
    existing = list(load_workbench_jobs(root, limit=MAX_JOB_HISTORY))
    updated: list[WorkbenchJobRecord] = []
    replaced = False
    for record in existing:
        if record.id == job.id:
            updated.append(job)
            replaced = True
        else:
            updated.append(record)
    if not replaced:
        updated.insert(0, job)
    updated.sort(key=lambda item: item.updated_at, reverse=True)
    updated = updated[:MAX_JOB_HISTORY]
    path = _jobs_path(root)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        json.dump([workbench_job_to_dict(record) for record in updated], handle, indent=2, ensure_ascii=False)
        temp_name = handle.name
    Path(temp_name).replace(path)
    return tuple(updated)


def workbench_jobs_lines(
    base_dir: Path | None = None,
    *,
    live_jobs: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
    limit: int = 8,
) -> list[str]:
    root = (base_dir or Path.cwd()).resolve()
    records: list[WorkbenchJobRecord] = []
    seen: set[str] = set()
    for entry in list(live_jobs or []):
        record = coerce_workbench_job(entry, base_dir=root)
        if record is None or record.id in seen:
            continue
        seen.add(record.id)
        records.append(record)
    for record in load_workbench_jobs(root, limit=MAX_JOB_HISTORY):
        if record.id in seen:
            continue
        seen.add(record.id)
        records.append(record)
    records.sort(key=lambda item: item.updated_at, reverse=True)
    records = records[:limit]

    if not records:
        return ["No workbench jobs yet.", "", "Run /build, /review, /ship, /learn, or /fixci."]

    lines: list[str] = [f"Workspace: {root}"]
    for record in records:
        lines.append("")
        lines.append(f"[{record.status}] {record.mode} · {record.objective}")
        meta: list[str] = [record.updated_at.replace('T', ' ')]
        if record.stage and record.stage != record.status:
            meta.append(record.stage)
        if record.risk:
            meta.append(f"risk {record.risk}")
        if record.dry_run:
            meta.append("dry-run")
        lines.append("  " + " · ".join(meta))
        if record.summary:
            lines.append(f"  summary: {record.summary[:160]}")
        if record.touched_files:
            lines.append(f"  touched: {', '.join(record.touched_files[:5])}")
        if record.failed_checks:
            lines.append(f"  failed: {', '.join(record.failed_checks[:4])}")
        if record.log_excerpt:
            log_line = record.log_excerpt.splitlines()[0]
            lines.append(f"  log: {log_line[:160]}")
    return lines


def render_workbench_jobs_report(
    base_dir: Path | None = None,
    *,
    live_jobs: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
    limit: int = 8,
) -> str:
    return "\n".join([WORKBENCH_TITLE, *workbench_jobs_lines(base_dir, live_jobs=live_jobs, limit=limit)])


def _iter_repo_files(base_dir: Path) -> list[Path]:
    allowed = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".md", ".toml", ".json", ".yaml", ".yml", ".sh"}
    ignored = {".git", "node_modules", "__pycache__", "venv", ".venv", ".pytest_cache", ".ruff_cache"}
    files: list[Path] = []
    seen: set[str] = set()
    for root in iter_context_roots(base_dir):
        for path in root.rglob("*"):
            if any(part in ignored for part in path.parts):
                continue
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue
            try:
                if path.stat().st_size > 300_000:
                    continue
            except OSError:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
            if len(files) >= MAX_INDEX_FILES:
                break
        if len(files) >= MAX_INDEX_FILES:
            break
    return sorted(files)


def _extract_symbols(path: Path, text: str, base_dir: Path) -> list[SymbolRecord]:
    patterns = _SYMBOL_PATTERNS.get(path.suffix.lower(), ())
    symbols: list[SymbolRecord] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in patterns:
            match = re.search(pattern, line)
            if match:
                symbols.append(SymbolRecord(match.group(1), kind, display_context_path(path, base_dir=base_dir), lineno))
    return symbols


def _extract_imports(text: str) -> list[str]:
    imports: list[str] = []
    for pattern in _IMPORT_PATTERNS:
        for match in pattern.findall(text):
            if isinstance(match, tuple):
                value = " ".join(str(part) for part in match if part)
            else:
                value = str(match)
            normalized = value.strip()
            if not normalized:
                continue
            imports.append(normalized.split()[0].strip(","))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in imports:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped[:MAX_IMPORTS_PER_FILE]


def _local_hotspots(files: list[Path], base_dir: Path, symbol_map: dict[str, int], changed: tuple[str, ...]) -> tuple[str, ...]:
    path_scores: list[tuple[int, str]] = []
    changed_set = set(changed)
    for path in files:
        rel = str(path.relative_to(base_dir))
        score = symbol_map.get(rel, 0)
        if rel in changed_set:
            score += 3
        if score:
            path_scores.append((score, rel))
    path_scores.sort(key=lambda item: (-item[0], item[1]))
    return tuple(path for _score, path in path_scores[:MAX_HOTSPOTS])


def _read_context_snippets(base_dir: Path, paths: tuple[str, ...]) -> list[str]:
    snippets: list[str] = []
    for rel in paths[:MAX_CONTEXT_SNIPPETS]:
        candidate = Path(rel).expanduser()
        path = candidate if candidate.is_absolute() else (base_dir / rel)
        text = _read_text(path, MAX_CONTEXT_CHARS)
        if not text:
            continue
        snippets.append(f"## {rel}\n{text.rstrip()}")
    return snippets


def _find_suggested_tests(base_dir: Path, profile, relevant: tuple[str, ...], changed: tuple[str, ...]) -> tuple[str, ...]:
    candidates = list(dict.fromkeys([*changed, *relevant]))
    tests: list[str] = []
    test_dirs = profile.test_directories or ("tests",)
    for candidate in candidates:
        stem = Path(candidate).stem.lower().replace("test_", "")
        if not stem:
            continue
        for test_dir in test_dirs:
            root = base_dir / test_dir
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                rel = str(path.relative_to(base_dir))
                if stem in path.name.lower() and rel not in tests:
                    tests.append(rel)
                    if len(tests) >= 8:
                        return tuple(tests)
    if not tests:
        checks = sorted(profile.verification_commands)
        if checks:
            return tuple(f"run {check}" for check in checks)
    return tuple(tests)


def _extract_conventions_from_context(base_dir: Path) -> tuple[str, ...]:
    conventions: list[str] = []
    context_path = find_project_context_file(base_dir)
    if context_path is None:
        return ()
    for raw in _read_text(context_path).splitlines():
        line = raw.strip().lstrip("-*").strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if len(line) < 8:
            continue
        conventions.append(line[:180])
        if len(conventions) >= 8:
            break
    return tuple(conventions)


def _load_project_memory_state() -> dict[str, Any]:
    if not PROJECT_MEMORY_PATH.exists():
        return {"workspaces": {}}
    try:
        data = json.loads(PROJECT_MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"workspaces": {}}
    if not isinstance(data, dict):
        return {"workspaces": {}}
    workspaces = data.get("workspaces")
    if not isinstance(workspaces, dict):
        workspaces = {}
    return {"workspaces": workspaces}


def _save_project_memory_state(data: dict[str, Any]) -> None:
    WORKBENCH_STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_MEMORY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_project_memory(base_dir: Path | None = None) -> ProjectMemoryProfile:
    root = (base_dir or Path.cwd()).resolve()
    state = _load_project_memory_state()
    workspace = _workspace_key(root)
    raw = state["workspaces"].get(workspace, {}) if isinstance(state.get("workspaces"), dict) else {}
    saved_conventions = [str(item) for item in raw.get("conventions", []) if str(item).strip()]
    extracted_conventions = list(_extract_conventions_from_context(root))
    conventions = tuple(dict.fromkeys([*saved_conventions, *extracted_conventions]))[:12]
    decisions = tuple(str(item)[:220] for item in raw.get("decisions", []) if str(item).strip())[:12]
    recent_runs = tuple(item for item in raw.get("recent_runs", []) if isinstance(item, dict))[:8]
    artifact_history = tuple(item for item in raw.get("artifact_history", []) if isinstance(item, dict))[:8]
    updated_at = str(raw.get("updated_at") or _now())
    return ProjectMemoryProfile(
        workspace=workspace,
        updated_at=updated_at,
        conventions=conventions,
        decisions=decisions,
        recent_runs=recent_runs,
        artifact_history=artifact_history,
    )


def _persist_project_memory(profile: ProjectMemoryProfile) -> None:
    state = _load_project_memory_state()
    state.setdefault("workspaces", {})[profile.workspace] = {
        "updated_at": profile.updated_at,
        "conventions": list(profile.conventions),
        "decisions": list(profile.decisions),
        "recent_runs": list(profile.recent_runs),
        "artifact_history": list(profile.artifact_history),
    }
    _save_project_memory_state(state)


def remember_project_decision(base_dir: Path | None, decision: str) -> ProjectMemoryProfile:
    profile = load_project_memory(base_dir)
    decisions = tuple(dict.fromkeys([decision[:220], *profile.decisions]))[:12]
    updated = ProjectMemoryProfile(
        workspace=profile.workspace,
        updated_at=_now(),
        conventions=profile.conventions,
        decisions=decisions,
        recent_runs=profile.recent_runs,
        artifact_history=profile.artifact_history,
    )
    _persist_project_memory(updated)
    return updated


def _save_intelligence_snapshot(intelligence: RepoIntelligence, base_dir: Path) -> None:
    payload = {
        "workspace": intelligence.workspace,
        "generated_at": intelligence.generated_at,
        "languages": list(intelligence.languages),
        "frameworks": list(intelligence.frameworks),
        "entrypoints": list(intelligence.entrypoints),
        "config_files": list(intelligence.config_files),
        "verification_commands": list(intelligence.verification_commands),
        "changed_files": list(intelligence.changed_files),
        "relevant_files": list(intelligence.relevant_files),
        "hotspots": list(intelligence.hotspots),
        "impact_files": list(intelligence.impact_files),
        "suggested_tests": list(intelligence.suggested_tests),
        "warnings": list(intelligence.warnings),
        "context_digest": intelligence.context_digest,
        "symbol_index": [asdict(item) for item in intelligence.symbol_index],
        "dependency_graph": {key: list(value) for key, value in intelligence.dependency_graph.items()},
    }
    _cache_path(base_dir).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_cached_repo_intelligence(base_dir: Path | None = None) -> RepoIntelligence | None:
    path = _cache_path(base_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return RepoIntelligence(
            workspace=str(payload.get("workspace") or _workspace_key(base_dir)),
            generated_at=str(payload.get("generated_at") or _now()),
            languages=tuple(str(item) for item in payload.get("languages", [])),
            frameworks=tuple(str(item) for item in payload.get("frameworks", [])),
            entrypoints=tuple(str(item) for item in payload.get("entrypoints", [])),
            config_files=tuple(str(item) for item in payload.get("config_files", [])),
            verification_commands=tuple(str(item) for item in payload.get("verification_commands", [])),
            changed_files=tuple(str(item) for item in payload.get("changed_files", [])),
            relevant_files=tuple(str(item) for item in payload.get("relevant_files", [])),
            hotspots=tuple(str(item) for item in payload.get("hotspots", [])),
            impact_files=tuple(str(item) for item in payload.get("impact_files", [])),
            suggested_tests=tuple(str(item) for item in payload.get("suggested_tests", [])),
            warnings=tuple(str(item) for item in payload.get("warnings", [])),
            context_digest=str(payload.get("context_digest") or ""),
            symbol_index=tuple(SymbolRecord(**item) for item in payload.get("symbol_index", []) if isinstance(item, dict)),
            dependency_graph={key: tuple(value) for key, value in payload.get("dependency_graph", {}).items()},
        )
    except Exception:
        return None


def build_repo_intelligence(base_dir: Path | None = None, *, task: str = "") -> RepoIntelligence:
    root = (base_dir or Path.cwd()).resolve()
    profile = inspect_workspace(root)
    relevant = find_relevant_paths(root, task, limit=8)
    files = _iter_repo_files(root)
    symbols: list[SymbolRecord] = []
    dependency_graph: dict[str, tuple[str, ...]] = {}
    symbol_counts: dict[str, int] = {}
    warnings: list[str] = list(profile.notes)

    for path in files:
        rel = display_context_path(path, base_dir=root)
        text = _read_text(path, limit=20_000)
        file_symbols = _extract_symbols(path, text, root)
        if file_symbols:
            symbols.extend(file_symbols)
            symbol_counts[rel] = len(file_symbols)
        imports = _extract_imports(text)
        if imports:
            dependency_graph[rel] = tuple(imports)

    if len(files) >= MAX_INDEX_FILES:
        warnings.append("repo scan capped for responsiveness")
    if not symbols:
        warnings.append("symbol index is sparse; repo may be config-heavy or generated")

    hotspots = _local_hotspots(files, root, symbol_counts, profile.changed_files)
    impact_files = tuple(dict.fromkeys([*profile.changed_files, *relevant, *hotspots]))[:10]
    suggested_tests = _find_suggested_tests(root, profile, relevant, profile.changed_files)
    snippets = _read_context_snippets(root, impact_files or relevant)
    digest_lines = [render_workspace_overview(profile)]
    if relevant:
        digest_lines.append("Relevant files: " + ", ".join(relevant[:6]))
    if hotspots:
        digest_lines.append("Hotspots: " + ", ".join(hotspots[:5]))
    if suggested_tests:
        digest_lines.append("Suggested tests: " + ", ".join(suggested_tests[:5]))
    if snippets:
        digest_lines.append("")
        digest_lines.extend(snippets)

    intelligence = RepoIntelligence(
        workspace=_workspace_key(root),
        generated_at=_now(),
        languages=profile.languages,
        frameworks=profile.frameworks,
        entrypoints=profile.entrypoints,
        config_files=profile.config_files,
        verification_commands=tuple(sorted(profile.verification_commands)),
        changed_files=profile.changed_files,
        relevant_files=relevant,
        hotspots=hotspots,
        impact_files=impact_files,
        suggested_tests=suggested_tests,
        warnings=tuple(dict.fromkeys(warnings))[:10],
        context_digest="\n".join(digest_lines).strip(),
        symbol_index=tuple(symbols[:MAX_SYMBOLS]),
        dependency_graph=dependency_graph,
    )
    _save_intelligence_snapshot(intelligence, root)
    return intelligence


def find_symbols(
    intelligence: RepoIntelligence,
    query: str,
    *,
    kind: str = "",
    limit: int = 20,
) -> tuple[SymbolRecord, ...]:
    needle = (query or "").strip().lower()
    wanted_kind = (kind or "").strip().lower()
    if not needle:
        return ()
    matches = [
        symbol
        for symbol in intelligence.symbol_index
        if needle in symbol.name.lower()
        and (not wanted_kind or wanted_kind == symbol.kind.lower())
    ]
    return tuple(matches[:limit])


def find_references(
    base_dir: Path | None,
    symbol: str,
    *,
    intelligence: RepoIntelligence | None = None,
    limit: int = MAX_REFERENCE_RESULTS,
) -> tuple[ReferenceRecord, ...]:
    root = (base_dir or Path.cwd()).resolve()
    indexed = intelligence or build_repo_intelligence(root, task=symbol)
    needle = (symbol or "").strip()
    if not needle:
        return ()
    pattern = re.compile(rf"\b{re.escape(needle)}\b")
    references: list[ReferenceRecord] = []
    candidate_files = list(dict.fromkeys([
        *indexed.impact_files,
        *indexed.relevant_files,
        *indexed.hotspots,
        *tuple(indexed.dependency_graph.keys()),
    ]))
    if not candidate_files:
        candidate_files = [record.path for record in indexed.symbol_index[:MAX_INDEX_FILES]]
    for rel in candidate_files:
        path = root / rel
        if not path.exists() or not path.is_file():
            continue
        text = _read_text(path, limit=80_000)
        if not text:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not pattern.search(line):
                continue
            references.append(
                ReferenceRecord(
                    path=display_context_path(path, base_dir=root),
                    line=lineno,
                    snippet=line.strip()[:220],
                )
            )
            if len(references) >= limit:
                return tuple(references)
    return tuple(references)


def analyze_impact(
    base_dir: Path | None,
    target: str,
    *,
    intelligence: RepoIntelligence | None = None,
    limit: int = MAX_IMPACT_RESULTS,
) -> tuple[str, ...]:
    root = (base_dir or Path.cwd()).resolve()
    indexed = intelligence or build_repo_intelligence(root, task=target)
    target_text = (target or "").strip()
    if not target_text:
        return ()
    seeds: list[str] = []
    raw_target = Path(target_text)
    if raw_target.suffix:
        candidate = raw_target if raw_target.is_absolute() else root / raw_target
        if candidate.exists():
            seeds.append(display_context_path(candidate.resolve(), base_dir=root))
    if not seeds:
        matches = find_symbols(indexed, target_text, limit=8)
        seeds.extend(symbol.path for symbol in matches)
    if not seeds:
        for rel in indexed.impact_files:
            if target_text.lower() in rel.lower():
                seeds.append(rel)
    if not seeds:
        return ()

    seed_tokens: set[str] = set()
    for seed in seeds:
        path = Path(seed)
        stem = path.stem
        suffixless = str(path.with_suffix("")).replace("/", ".")
        seed_tokens.update({seed, stem, suffixless})

    impacted: list[str] = []
    seen: set[str] = set()
    for item in seeds:
        if item not in seen:
            seen.add(item)
            impacted.append(item)
    for dependent, imports in indexed.dependency_graph.items():
        haystack = " ".join(imports).lower()
        if any(token.lower() in haystack for token in seed_tokens) and dependent not in seen:
            seen.add(dependent)
            impacted.append(dependent)
        if len(impacted) >= limit:
            break
    return tuple(impacted[:limit])


def render_symbol_report(intelligence: RepoIntelligence, query: str) -> str:
    matches = find_symbols(intelligence, query)
    lines = [WORKBENCH_TITLE, f"Symbol search: {query}"]
    if not matches:
        lines.append("  no matching symbols")
        return "\n".join(lines)
    for symbol in matches:
        lines.append(f"  {symbol.kind:10} {symbol.name}  {symbol.path}:{symbol.line}")
    return "\n".join(lines)


def render_reference_report(base_dir: Path | None, query: str, *, intelligence: RepoIntelligence | None = None) -> str:
    indexed = intelligence or build_repo_intelligence(base_dir, task=query)
    refs = find_references(base_dir, query, intelligence=indexed)
    lines = [WORKBENCH_TITLE, f"References: {query}"]
    if not refs:
        lines.append("  no references found")
        return "\n".join(lines)
    for ref in refs:
        lines.append(f"  {ref.path}:{ref.line}  {ref.snippet}")
    return "\n".join(lines)


def render_impact_report(base_dir: Path | None, target: str, *, intelligence: RepoIntelligence | None = None) -> str:
    indexed = intelligence or build_repo_intelligence(base_dir, task=target)
    impacted = analyze_impact(base_dir, target, intelligence=indexed)
    lines = [WORKBENCH_TITLE, f"Impact analysis: {target}"]
    if not impacted:
        lines.append("  no impact candidates found")
        return "\n".join(lines)
    for item in impacted:
        lines.append(f"  {item}")
    suggested_tests = [test for test in indexed.suggested_tests if any(Path(item).stem in test for item in impacted)]
    if suggested_tests:
        lines.append("")
        lines.append("Suggested tests")
        lines.extend(f"  {test}" for test in suggested_tests[:6])
    return "\n".join(lines)


def _risk_details(mode: str, objective: str, intelligence: RepoIntelligence) -> tuple[str, tuple[str, ...]]:
    score = 0
    warnings: list[str] = []
    lowered = objective.lower()
    for keyword, weight in _RISK_KEYWORDS.items():
        if keyword in lowered:
            score += weight
            warnings.append(f"objective includes '{keyword}'")
    if mode in {"build", "fixci"}:
        score += 1
    if len(intelligence.changed_files) >= 6:
        score += 2
        warnings.append("workspace already has many changed files")
    if not intelligence.verification_commands and mode in {"build", "ship", "fixci"}:
        score += 2
        warnings.append("no detected verification commands")
    if len(intelligence.impact_files) >= 6:
        score += 1
        warnings.append("task touches a broad slice of the repo")
    level = "low"
    if score >= 6:
        level = "high"
    elif score >= 3:
        level = "medium"
    return level, tuple(dict.fromkeys(warnings))[:8]


def prepare_workbench_plan(mode: str, objective: str, *, base_dir: Path | None = None, dry_run: bool = False) -> WorkbenchPlan:
    normalized_mode = (mode or "build").strip().lower()
    if normalized_mode not in {"build", "review", "ship", "learn", "fixci"}:
        raise ValueError(f"Unsupported workbench mode: {mode}")
    root = (base_dir or Path.cwd()).resolve()
    intelligence = build_repo_intelligence(root, task=objective)
    project_memory = load_project_memory(root)
    risk_level, safety_warnings = _risk_details(normalized_mode, objective, intelligence)

    suggested_steps_map = {
        "build": (
            "inspect repo profile and impact map",
            "plan safe edits against relevant files",
            "apply changes and run detected checks",
            "review resulting diff and summarize risk",
            "capture artifacts and update project memory",
        ),
        "review": (
            "inspect changed files and relevant hotspots",
            "run review-only agent planning",
            "surface bugs, regressions, and missing tests",
            "capture risk summary and follow-up actions",
        ),
        "ship": (
            "inspect git state and changed files",
            "run detected verification commands",
            "assemble PR, release, changelog, and test summary artifacts",
            "record release-facing decisions in project memory",
        ),
        "learn": (
            "index symbols and dependency edges",
            "summarize architecture, hotspots, and likely impact zones",
            "merge saved conventions and decisions into one digest",
        ),
        "fixci": (
            "inspect workflows, checks, and repo health",
            "plan bounded repairs for failing verification paths",
            "apply fixes and rerun relevant checks",
            "capture final diagnostics and release notes",
        ),
    }
    artifacts = {
        "build": ("commit title", "PR description", "test summary", "architecture summary"),
        "review": ("review summary", "risk report", "test gaps"),
        "ship": ("release notes", "changelog", "PR description", "test summary"),
        "learn": ("architecture summary", "repo digest"),
        "fixci": ("CI repair summary", "test summary", "PR description"),
    }[normalized_mode]

    return WorkbenchPlan(
        mode=normalized_mode,
        objective=(objective or normalized_mode).strip(),
        dry_run=bool(dry_run),
        risk_level=risk_level,
        safety_warnings=safety_warnings,
        suggested_steps=suggested_steps_map[normalized_mode],
        recommended_checks=intelligence.verification_commands,
        intelligence=intelligence,
        project_memory=project_memory,
        artifacts=artifacts,
    )


def _git_lines(base_dir: Path, command: str) -> list[str]:
    ok, output = run_git_subcommand(command, cwd=base_dir)
    if not ok:
        return []
    return [line for line in output.splitlines() if line.strip()][:10]


def _release_bullets(intelligence: RepoIntelligence, summary: str) -> list[str]:
    bullets = [summary.strip() or "Updated the workspace."]
    if intelligence.impact_files:
        bullets.append("Touched: " + ", ".join(intelligence.impact_files[:4]))
    if intelligence.suggested_tests:
        bullets.append("Suggested checks: " + ", ".join(intelligence.suggested_tests[:4]))
    if intelligence.frameworks:
        bullets.append("Stack: " + ", ".join(intelligence.frameworks[:4]))
    return bullets[:4]


def build_artifact_bundle(
    *,
    base_dir: Path | None = None,
    mode: str,
    objective: str,
    summary: str,
    intelligence: RepoIntelligence,
    risk_level: str,
    failed_checks: tuple[str, ...] = (),
) -> ArtifactBundle:
    root = (base_dir or Path.cwd()).resolve()
    focus = intelligence.impact_files[0] if intelligence.impact_files else intelligence.relevant_files[0] if intelligence.relevant_files else "workspace"
    verb = {
        "build": "build",
        "review": "review",
        "ship": "release",
        "learn": "map",
        "fixci": "fixci",
    }.get(mode, mode)
    commit_title = f"{verb}: {Path(focus).stem.replace('_', ' ').replace('-', ' ')[:52]}".strip()
    review_lines = _git_lines(root, "review")
    log_lines = _git_lines(root, "log")
    changed = ", ".join(intelligence.changed_files[:6]) or "working tree clean"
    checks = ", ".join(intelligence.verification_commands) or "none detected"
    failed = ", ".join(failed_checks) if failed_checks else "none"

    pr_description = "\n".join(
        [
            "## Summary",
            f"- Mode: {mode}",
            f"- Objective: {objective}",
            f"- Result: {summary}",
            f"- Risk: {risk_level}",
            "",
            "## Impact",
            f"- Changed files: {changed}",
            f"- Suggested tests: {', '.join(intelligence.suggested_tests[:6]) or checks}",
            "",
            "## Notes",
            f"- Hotspots: {', '.join(intelligence.hotspots[:5]) or 'none'}",
            f"- Failed checks: {failed}",
        ]
    )

    release_notes = "\n".join(f"- {bullet}" for bullet in _release_bullets(intelligence, summary))
    changelog_lines = log_lines or ["(no git history found)"]
    changelog = "\n".join(f"- {line}" for line in changelog_lines[:8])
    test_summary = (
        f"Checks: {checks}\n"
        f"Suggested tests: {', '.join(intelligence.suggested_tests[:6]) or 'none'}\n"
        f"Failed checks: {failed}"
    )
    architecture_summary = "\n".join(
        [
            f"Workspace: {intelligence.workspace}",
            f"Languages: {', '.join(intelligence.languages) or 'unknown'}",
            f"Frameworks: {', '.join(intelligence.frameworks) or 'unknown'}",
            f"Entrypoints: {', '.join(intelligence.entrypoints) or 'none'}",
            f"Hotspots: {', '.join(intelligence.hotspots[:5]) or 'none'}",
            f"Symbols indexed: {intelligence.symbol_count}",
            *(review_lines[:5] if review_lines else []),
        ]
    )
    return ArtifactBundle(
        commit_title=commit_title,
        pr_description=pr_description,
        release_notes=release_notes,
        changelog=changelog,
        test_summary=test_summary,
        architecture_summary=architecture_summary,
    )


def _copy_memory(memory: Any | None) -> ShortTermMemory:
    max_turns = getattr(memory, "max_turns", 20) if memory is not None else 20
    duplicate = ShortTermMemory(max_turns=max_turns)
    if memory is not None and hasattr(memory, "get"):
        duplicate.set_history(list(memory.get()))
    return duplicate


def _command_to_string(command: str | tuple[str, ...]) -> str:
    if isinstance(command, str):
        return command
    return " ".join(command)


def _run_command_specs(
    base_dir: Path,
    commands: tuple[tuple[str, str | tuple[str, ...]], ...],
    *,
    progress_cb: Callable[[str], None] | None = None,
    timeout: int = 180,
) -> tuple[str, tuple[str, ...]]:
    outputs: list[str] = []
    failed: list[str] = []
    for label, command in commands:
        command_text = _command_to_string(command)
        if progress_cb:
            progress_cb(f"running {label}: {command_text}")
        try:
            result = subprocess.run(
                command if not isinstance(command, str) else command_text,
                shell=isinstance(command, str),
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            failed.append(label)
            outputs.append(f"{label}: failed to start ({exc})")
            continue
        output = (result.stdout + result.stderr).strip() or "(no output)"
        snippet = output.splitlines()[0][:220] if output else "(no output)"
        if result.returncode != 0:
            failed.append(label)
        outputs.append(f"{label}: rc={result.returncode} · {snippet}")
    return "\n".join(outputs) if outputs else "No commands executed.", tuple(failed)


def _run_detected_checks(base_dir: Path, intelligence: RepoIntelligence, progress_cb: Callable[[str], None] | None = None) -> tuple[str, tuple[str, ...]]:
    profile = inspect_workspace(base_dir)
    specs = tuple((kind, command) for kind, command in profile.verification_commands.items())
    if not specs:
        return "No verification commands detected.", ()
    return _run_command_specs(base_dir, specs, progress_cb=progress_cb, timeout=120)


def _parse_workflow_run_blocks(text: str) -> list[str]:
    commands: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(\s*)run:\s*(.*)$", line)
        if not match:
            index += 1
            continue
        indent = len(match.group(1))
        value = match.group(2).strip()
        block: list[str] = []
        if value in {"|", ">", "|-", ">-"}:
            index += 1
            while index < len(lines):
                candidate = lines[index]
                if candidate.strip() and (len(candidate) - len(candidate.lstrip())) <= indent:
                    break
                block.append(candidate.strip())
                index += 1
            value = " && ".join(item for item in block if item)
            commands.append(value.strip())
            continue
        commands.append(value.strip().strip("'\""))
        index += 1
    return [command for command in commands if command]


def _workflow_commands(base_dir: Path) -> tuple[str, ...]:
    roots = [base_dir / ".github" / "workflows"]
    allowed_prefixes = (
        "pytest",
        "python -m pytest",
        "python3 -m pytest",
        "ruff",
        "python -m ruff",
        "python3 -m ruff",
        "mypy",
        "python -m mypy",
        "python3 -m mypy",
        "npm test",
        "npm run test",
        "npm run lint",
        "npm run typecheck",
        "pnpm test",
        "pnpm lint",
        "pnpm typecheck",
        "yarn test",
        "yarn lint",
        "cargo test",
        "cargo check",
        "go test",
        "bun test",
    )
    commands: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.y*ml")):
            text = _read_text(path, limit=80_000)
            for command in _parse_workflow_run_blocks(text):
                lowered = command.lower()
                if "${{" in command or "sudo " in lowered or "rm -rf" in lowered:
                    continue
                if any(lowered.startswith(prefix) for prefix in allowed_prefixes):
                    commands.append(command)
    return tuple(dict.fromkeys(commands))


def _fixci_command_specs(base_dir: Path) -> tuple[tuple[str, str | tuple[str, ...]], ...]:
    profile = inspect_workspace(base_dir)
    specs: list[tuple[str, str | tuple[str, ...]]] = [
        (kind, command) for kind, command in profile.verification_commands.items()
    ]
    workflow_commands = _workflow_commands(base_dir)
    for command in workflow_commands:
        if command not in {_command_to_string(item[1]) for item in specs}:
            specs.append((f"workflow:{command.split()[0]}", command))
    return tuple(specs)


def _build_review_prompt(plan: WorkbenchPlan, *, git_review: str = "", git_diff: str = "") -> str:
    changed = ", ".join(plan.intelligence.changed_files[:8]) or "working tree clean"
    relevant = ", ".join(plan.intelligence.relevant_files[:8]) or "none"
    impact = ", ".join(plan.intelligence.impact_files[:8]) or "none"
    hotspots = ", ".join(plan.intelligence.hotspots[:6]) or "none"
    tests = ", ".join(plan.intelligence.suggested_tests[:6]) or ", ".join(plan.intelligence.verification_commands) or "none"
    sections = [
        f"Review the current workspace for: {plan.objective}",
        "Findings first. Order by severity. Focus on bugs, regressions, behavioral risk, and missing tests.",
        "Use file paths and line references whenever possible.",
        f"Changed files: {changed}",
        f"Relevant files: {relevant}",
        f"Impact files: {impact}",
        f"Hotspots: {hotspots}",
        f"Suggested tests: {tests}",
    ]
    if plan.project_memory.conventions:
        sections.append("Project conventions:\n" + "\n".join(f"- {item}" for item in plan.project_memory.conventions[:6]))
    if git_review:
        sections.append("Git review snapshot:\n" + git_review[:2400])
    if git_diff:
        sections.append("Diff excerpt:\n" + git_diff[:3200])
    return "\n\n".join(sections)


def _complete_text(
    *,
    client: Any,
    model: str,
    system_prompt: str,
    prompt: str,
    max_tokens: int = 1600,
    temperature: float = 0.2,
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=False,
    )
    choice = response.choices[0].message.content
    if isinstance(choice, list):
        return "\n".join(str(item.get("text", "")) for item in choice if isinstance(item, dict)).strip()
    return str(choice or "").strip()


def _first_line(text: str, *, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip(" -•\t")
        if stripped:
            return stripped[:220]
    return fallback


def _record_workbench_run(
    *,
    base_dir: Path,
    mode: str,
    objective: str,
    summary: str,
    risk_level: str,
    artifacts: ArtifactBundle,
) -> ProjectMemoryProfile:
    profile = load_project_memory(base_dir)
    recent_runs = (
        {
            "ts": _now(),
            "mode": mode,
            "objective": objective[:160],
            "summary": summary[:220],
            "risk": risk_level,
        },
        *profile.recent_runs,
    )[:8]
    artifact_history = (
        {
            "ts": _now(),
            "mode": mode,
            "commit_title": artifacts.commit_title,
            "release_excerpt": artifacts.release_notes.splitlines()[0] if artifacts.release_notes else "",
        },
        *profile.artifact_history,
    )[:8]
    decisions = profile.decisions
    if mode in {"build", "fixci", "ship"}:
        decision = f"{mode}: {summary[:180]}"
        decisions = tuple(dict.fromkeys([decision, *decisions]))[:12]
    updated = ProjectMemoryProfile(
        workspace=profile.workspace,
        updated_at=_now(),
        conventions=profile.conventions,
        decisions=decisions,
        recent_runs=tuple(recent_runs),
        artifact_history=tuple(artifact_history),
    )
    _persist_project_memory(updated)
    return updated


def execute_workbench(
    mode: str,
    objective: str,
    *,
    client: Any | None = None,
    model: str = "",
    memory: Any | None = None,
    system_prompt: str = "",
    base_dir: Path | None = None,
    dry_run: bool = False,
    progress_cb: Callable[[str], None] | None = None,
    run_agent_fn: Callable[..., str] | None = None,
) -> WorkbenchRunResult:
    root = (base_dir or Path.cwd()).resolve()
    if run_agent_fn is None and mode.strip().lower() in {"build", "review", "fixci"}:
        from src.agents.agent import run_agent as default_run_agent

        run_agent_fn = default_run_agent
    plan = prepare_workbench_plan(mode, objective, base_dir=root, dry_run=dry_run)
    normalized_mode = plan.mode
    if progress_cb:
        progress_cb(f"prepared {normalized_mode} plan")

    summary = ""
    execution_log = ""
    failed_checks: tuple[str, ...] = ()

    if normalized_mode == "learn":
        summary = (
            f"{WORKBENCH_NAME} indexed {plan.intelligence.symbol_count} symbol(s) across "
            f"{len(plan.intelligence.dependency_graph) or len(plan.intelligence.relevant_files) or len(plan.intelligence.changed_files)} tracked file(s)."
        )
    elif normalized_mode == "review":
        if client is None or not model:
            raise ValueError("review mode requires a client and model")
        if progress_cb:
            progress_cb("collecting git review context")
        _ok_review, git_review = run_git_subcommand("review", cwd=root)
        _ok_diff, git_diff = run_git_subcommand("diff", cwd=root)
        review_text = _complete_text(
            client=client,
            model=model,
            system_prompt=system_prompt,
            prompt=_build_review_prompt(
                plan,
                git_review=git_review if _ok_review else "",
                git_diff=git_diff if _ok_diff else "",
            ),
            max_tokens=2200,
            temperature=0.15,
        )
        summary = _first_line(review_text, fallback="Workspace review completed.")
        execution_log = review_text
    elif normalized_mode == "ship":
        check_output, failed_checks = _run_detected_checks(root, plan.intelligence, progress_cb=progress_cb)
        execution_log = check_output
        summary = "Release artifacts prepared from current git state."
    else:
        if client is None or not model or not run_agent_fn:
            raise ValueError(f"{normalized_mode} mode requires a client, model, and run_agent_fn")
        objective_prefix = {
            "build": (
                f"{objective}\n\n"
                "Requirements:\n"
                "- inspect the repo before editing\n"
                "- change the minimum set of files needed\n"
                "- preserve behavior outside the requested scope\n"
                "- run detected verification commands after edits and mention failures clearly"
            ),
            "fixci": f"Fix CI and verification issues for this workspace. {objective}".strip(),
        }[normalized_mode]
        local_memory = _copy_memory(memory)
        preflight_log = ""
        if normalized_mode == "fixci":
            command_specs = _fixci_command_specs(root)
            preflight_log, preflight_failed = _run_command_specs(root, command_specs, progress_cb=progress_cb, timeout=180)
            failed_checks = preflight_failed
            objective_prefix = (
                f"{objective_prefix}\n\n"
                "Current failing checks:\n"
                f"{', '.join(preflight_failed) or 'none detected'}\n\n"
                "Diagnostics:\n"
                f"{preflight_log}"
            )
        if progress_cb:
            progress_cb(f"running {normalized_mode} agent")
        buf = io.StringIO()
        agent_kwargs: dict[str, Any] = {}
        try:
            params = inspect.signature(run_agent_fn).parameters
        except (TypeError, ValueError):
            params = {}
        if "base_dir" in params:
            agent_kwargs["base_dir"] = root
        with redirect_stdout(buf):
            summary = run_agent_fn(
                objective_prefix,
                client,
                model,
                local_memory,
                system_prompt,
                True,
                dry_run or normalized_mode == "review",
                **agent_kwargs,
            )
        agent_log = buf.getvalue().strip()
        execution_parts = [part for part in (preflight_log, agent_log) if part]

        if normalized_mode == "build":
            check_output, failed_checks = _run_detected_checks(root, plan.intelligence, progress_cb=progress_cb)
            execution_parts.append(check_output)
            if failed_checks and run_agent_fn is not None and not dry_run:
                repair_prompt = (
                    "Repair the failing verification checks from the build run.\n\n"
                    f"Original objective: {objective}\n"
                    f"Failing checks: {', '.join(failed_checks)}\n\n"
                    "Stay inside the current task scope. Fix only what the verification output proves is broken.\n\n"
                    f"Diagnostics:\n{check_output}"
                )
                if progress_cb:
                    progress_cb("repairing failing build checks")
                repair_buf = io.StringIO()
                with redirect_stdout(repair_buf):
                    repair_summary = run_agent_fn(
                        repair_prompt,
                        client,
                        model,
                        _copy_memory(memory),
                        system_prompt,
                        True,
                        dry_run,
                        **agent_kwargs,
                    )
                repair_log = repair_buf.getvalue().strip()
                if repair_summary and repair_summary != summary:
                    summary = f"{summary.rstrip('.')} · repair pass: {repair_summary}"
                if repair_log:
                    execution_parts.append(repair_log)
                check_output, failed_checks = _run_detected_checks(root, plan.intelligence, progress_cb=progress_cb)
                execution_parts.append(check_output)
        elif normalized_mode == "fixci":
            command_specs = _fixci_command_specs(root)
            post_log, post_failed = _run_command_specs(root, command_specs, progress_cb=progress_cb, timeout=180)
            execution_parts.append(post_log)
            failed_checks = post_failed
            if post_failed and run_agent_fn is not None:
                repair_prompt = (
                    "Repair the remaining failing CI/verification checks.\n\n"
                    f"Failed checks: {', '.join(post_failed)}\n\n"
                    f"Latest diagnostics:\n{post_log}"
                )
                if progress_cb:
                    progress_cb("repairing remaining ci failures")
                retry_buf = io.StringIO()
                with redirect_stdout(retry_buf):
                    summary = run_agent_fn(
                        repair_prompt,
                        client,
                        model,
                        _copy_memory(memory),
                        system_prompt,
                        True,
                        dry_run,
                        **agent_kwargs,
                    )
                retry_log = retry_buf.getvalue().strip()
                if retry_log:
                    execution_parts.append(retry_log)
                post_log, post_failed = _run_command_specs(root, command_specs, progress_cb=progress_cb, timeout=180)
                execution_parts.append(post_log)
                failed_checks = post_failed
        execution_log = "\n".join(part for part in execution_parts if part).strip()
        if failed_checks:
            summary = f"{summary.rstrip('.')} · remaining failed checks: {', '.join(failed_checks[:4])}"

    final_intelligence = build_repo_intelligence(root, task=objective)
    touched_files = final_intelligence.changed_files
    artifacts = build_artifact_bundle(
        base_dir=root,
        mode=normalized_mode,
        objective=objective,
        summary=summary,
        intelligence=final_intelligence,
        risk_level=plan.risk_level,
        failed_checks=failed_checks,
    )
    project_memory = _record_workbench_run(
        base_dir=root,
        mode=normalized_mode,
        objective=objective,
        summary=summary,
        risk_level=plan.risk_level,
        artifacts=artifacts,
    )
    return WorkbenchRunResult(
        mode=normalized_mode,
        objective=objective,
        dry_run=bool(dry_run),
        summary=summary,
        risk_level=plan.risk_level,
        touched_files=touched_files,
        failed_checks=failed_checks,
        intelligence=final_intelligence,
        project_memory=project_memory,
        artifacts=artifacts,
        execution_log=execution_log,
    )


def render_project_memory(profile: ProjectMemoryProfile) -> str:
    lines = ["Project memory", f"  Workspace: {profile.workspace}", f"  Updated:   {profile.updated_at}"]
    lines.append("  Conventions: " + (", ".join(profile.conventions[:5]) if profile.conventions else "none"))
    lines.append("  Decisions:   " + (", ".join(profile.decisions[:4]) if profile.decisions else "none"))
    if profile.recent_runs:
        last = profile.recent_runs[0]
        lines.append(f"  Last run:    {last.get('mode', '?')} · {last.get('summary', '')}")
    return "\n".join(lines)


def render_repo_intelligence(intelligence: RepoIntelligence) -> str:
    lines = [WORKBENCH_TITLE, f"  Workspace: {intelligence.workspace}", f"  Indexed:   {intelligence.symbol_count} symbols"]
    lines.append("  Languages: " + (", ".join(intelligence.languages) if intelligence.languages else "unknown"))
    lines.append("  Frameworks: " + (", ".join(intelligence.frameworks) if intelligence.frameworks else "unknown"))
    if intelligence.entrypoints:
        lines.append("  Entrypoints: " + ", ".join(intelligence.entrypoints[:5]))
    if intelligence.changed_files:
        lines.append("  Changed:   " + ", ".join(intelligence.changed_files[:6]))
    if intelligence.relevant_files:
        lines.append("  Relevant:  " + ", ".join(intelligence.relevant_files[:6]))
    if intelligence.impact_files:
        lines.append("  Impact:    " + ", ".join(intelligence.impact_files[:6]))
    if intelligence.hotspots:
        lines.append("  Hotspots:  " + ", ".join(intelligence.hotspots[:6]))
    if intelligence.verification_commands:
        lines.append("  Checks:    " + ", ".join(intelligence.verification_commands[:6]))
    if intelligence.suggested_tests:
        lines.append("  Tests:     " + ", ".join(intelligence.suggested_tests[:6]))
    if intelligence.warnings:
        lines.append("  Warnings:  " + ", ".join(intelligence.warnings[:4]))
    return "\n".join(lines)


def render_workbench_plan(plan: WorkbenchPlan) -> str:
    lines = [
        WORKBENCH_TITLE,
        f"Mode: {plan.mode}",
        f"Objective: {plan.objective}",
        f"Risk: {plan.risk_level}",
        f"Dry run: {'yes' if plan.dry_run else 'no'}",
        "",
        "Plan",
    ]
    lines.extend(f"  - {step}" for step in plan.suggested_steps)
    if plan.recommended_checks:
        lines.append("")
        lines.append("Checks")
        lines.extend(f"  - {check}" for check in plan.recommended_checks)
    if plan.safety_warnings:
        lines.append("")
        lines.append("Safety")
        lines.extend(f"  - {warning}" for warning in plan.safety_warnings)
    lines.append("")
    lines.append(render_repo_intelligence(plan.intelligence))
    lines.append("")
    lines.append(render_project_memory(plan.project_memory))
    return "\n".join(lines)


def render_workbench_result(result: WorkbenchRunResult) -> str:
    lines = [
        WORKBENCH_TITLE,
        f"Mode: {result.mode}",
        f"Objective: {result.objective}",
        f"Summary: {result.summary}",
        f"Risk: {result.risk_level}",
    ]
    if result.touched_files:
        lines.append("Touched: " + ", ".join(result.touched_files[:8]))
    if result.failed_checks:
        lines.append("Failed checks: " + ", ".join(result.failed_checks[:6]))
    lines.append("")
    lines.append("Artifacts")
    lines.append(f"  Commit: {result.artifacts.commit_title}")
    lines.append(f"  Release: {result.artifacts.release_notes.splitlines()[0] if result.artifacts.release_notes else 'n/a'}")
    if result.execution_log:
        lines.append("")
        lines.append("Execution log")
        lines.extend(f"  {line}" for line in result.execution_log.splitlines()[:12])
    return "\n".join(lines)


def workbench_status_summary(base_dir: Path | None = None) -> str:
    cached = load_cached_repo_intelligence(base_dir)
    memory = load_project_memory(base_dir)
    if cached is None:
        return f"{WORKBENCH_NAME} · index pending · {len(memory.conventions)} convention(s)"
    return (
        f"{WORKBENCH_NAME} · {cached.symbol_count} symbol(s) · "
        f"{len(memory.conventions)} convention(s) · {len(memory.decisions)} decision(s)"
    )


def render_workbench_report(base_dir: Path | None = None, *, task: str = "") -> str:
    root = (base_dir or Path.cwd()).resolve()
    intelligence = build_repo_intelligence(root, task=task)
    memory = load_project_memory(root)
    normalized = (task or "").strip()
    lowered = normalized.lower()
    if lowered.startswith("symbol "):
        return render_symbol_report(intelligence, normalized.split(None, 1)[1].strip())
    if lowered.startswith("symbols "):
        return render_symbol_report(intelligence, normalized.split(None, 1)[1].strip())
    if lowered.startswith("refs "):
        return render_reference_report(root, normalized.split(None, 1)[1].strip(), intelligence=intelligence)
    if lowered.startswith("references "):
        return render_reference_report(root, normalized.split(None, 1)[1].strip(), intelligence=intelligence)
    if lowered.startswith("impact "):
        return render_impact_report(root, normalized.split(None, 1)[1].strip(), intelligence=intelligence)
    sections = [
        render_repo_intelligence(intelligence),
        render_project_memory(memory),
    ]
    recent_jobs = workbench_jobs_lines(root, limit=4)
    if recent_jobs and recent_jobs[0] != "No workbench jobs yet.":
        sections.append("\n".join(["Recent workbench jobs", *recent_jobs[:12]]))
    sections.append(intelligence.context_digest)
    return "\n\n".join(sections)
