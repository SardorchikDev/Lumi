"""
Lumi file system agent — detects and executes file/folder creation
and removal from natural language. No slash command needed.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from difflib import unified_diff
from pathlib import Path
from typing import Any

from src.config import UNDO_DIR

# ── Intent detection ──────────────────────────────────────────────────────────

CREATE_PATTERNS = [
    r"\bcreate\b.{0,60}\bfolder\b",
    r"\bcreate\b.{0,60}\bdir(ectory)?\b",
    r"\bmake\b.{0,60}\bfolder\b",
    r"\bmake\b.{0,60}\bproject\b",
    r"\bset up\b.{0,60}\bfolder\b",
    r"\bset up\b.{0,60}\bproject\b",
    r"\binitialize\b.{0,60}\bproject\b",
    r"\binit\b.{0,60}\bproject\b",
    r"\bscaffold\b",
    r"\bcreate\b.{0,30}\b(index\.html|style\.css|script\.js|main\.py|app\.py|README\.md)\b",
    r"\badd\b.{0,30}\b(index\.html|style\.css|script\.js|main\.py|app\.py)\b.{0,30}\bto it\b",
    r"\bcreate\b.{0,40}\bfiles?\b.{0,40}\bcode\b",
    r"\bgenerate\b.{0,40}\bfiles?\b",
    r"\bbootstrap\b.{0,40}\bproject\b",
]

DELETE_PATTERNS = [
    r"\bdelete\b.{0,60}\b(folder|directory|file|files)\b",
    r"\bremove\b.{0,60}\b(folder|directory|file|files)\b",
    r"\bdelete\b.{0,40}\b[A-Za-z0-9._/-]+\b",
    r"\bremove\b.{0,40}\b[A-Za-z0-9._/-]+\b",
    r"\brm\b.{0,40}\b[A-Za-z0-9._/-]+\b",
]

MOVE_PATTERNS = [
    r"\bmove\b.{0,60}\b(folder|directory|file|files)\b",
    r"\bmove\b.{0,40}\b[A-Za-z0-9._/-]+\b.{0,20}\b(to|into|under|inside)\b",
]

COPY_PATTERNS = [
    r"\bcopy\b.{0,60}\b(folder|directory|file|files)\b",
    r"\bcopy\b.{0,40}\b[A-Za-z0-9._/-]+\b.{0,20}\b(to|into|under|inside)\b",
]

RENAME_PATTERNS = [
    r"\brename\b.{0,60}\b(folder|directory|file|files)\b",
    r"\brename\b.{0,40}\b[A-Za-z0-9._/-]+\b.{0,20}\bto\b",
]

UNDO_ROOT = UNDO_DIR
MAX_PREVIEW_LINES = 6
MAX_DIFF_LINES = 24
MAX_SUGGESTIONS = 8

# Pre-compile for performance — avoid recompiling on every call.
_COMPILED_CREATE_PATTERNS = [re.compile(p) for p in CREATE_PATTERNS]
_COMPILED_DELETE_PATTERNS = [re.compile(p) for p in DELETE_PATTERNS]
_COMPILED_MOVE_PATTERNS = [re.compile(p) for p in MOVE_PATTERNS]
_COMPILED_COPY_PATTERNS = [re.compile(p) for p in COPY_PATTERNS]
_COMPILED_RENAME_PATTERNS = [re.compile(p) for p in RENAME_PATTERNS]


def is_create_request(text: str) -> bool:
    """Return True if the message is asking to create files/folders."""
    t = text.lower()
    return any(p.search(t) for p in _COMPILED_CREATE_PATTERNS)


def is_delete_request(text: str) -> bool:
    """Return True if the message is asking to remove files/folders."""
    t = text.lower()
    if re.match(r"^\s*(?:explain|how|what|why|when)\b", t):
        return False
    return any(p.search(t) for p in _COMPILED_DELETE_PATTERNS)


def is_move_request(text: str) -> bool:
    t = text.lower()
    return any(p.search(t) for p in _COMPILED_MOVE_PATTERNS)


def is_copy_request(text: str) -> bool:
    t = text.lower()
    return any(p.search(t) for p in _COMPILED_COPY_PATTERNS)


def is_rename_request(text: str) -> bool:
    t = text.lower()
    return any(p.search(t) for p in _COMPILED_RENAME_PATTERNS)


def is_filesystem_request(text: str) -> bool:
    return any(
        fn(text)
        for fn in (
            is_create_request,
            is_delete_request,
            is_move_request,
            is_copy_request,
            is_rename_request,
        )
    )


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _normalize_target_name(value: str) -> str:
    cleaned = _strip_wrapping_quotes(value.strip().rstrip(".,;:"))
    cleaned = re.sub(r"^(?:the\s+)?(?:folder|directory|dir|file|path)\b\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:named|called)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _split_operation_clauses(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.replace("\n", " ")).strip()
    if not text:
        return []
    text = re.sub(
        r"(?<!^)\s+(?=(?:create|make|add|delete|remove|rm)\s+(?:a|an|the)?\s*(?:new\s+)?(?:file|folder|directory|dir)\b)",
        " | ",
        text,
        flags=re.IGNORECASE,
    )
    parts = re.split(
        r"\s*(?:\||,|;|\bthen\b|\band then\b|\band\b(?=\s+(?:create|make|add|delete|remove|rm|inside|in|under)\b))\s*",
        text,
        flags=re.IGNORECASE,
    )
    return [part.strip() for part in parts if part.strip()]


def _extract_named_target(clause: str, kind_words: str, verbs: str) -> str:
    token_pattern = r'"[^"]+"|\'[^\']+\'|[A-Za-z0-9][A-Za-z0-9._/-]*'
    patterns = (
        rf"\b(?:{verbs})\s+(?:a|an|the)?\s*(?:new\s+)?(?:{kind_words})\s+(?:named|called)\s*(?P<name>{token_pattern})",
        rf"\b(?:{verbs})\s+(?:a|an|the)?\s*(?:new\s+)?(?:{kind_words})\s+(?P<name>{token_pattern})(?=$|\s+(?:inside|in|under)\b)",
        rf"\b(?:{verbs})\s+(?:a|an|the)?\s*(?:new\s+)?(?:{kind_words})\b.*?\b(?:named|called)\s*(?P<name>{token_pattern})",
    )
    for pattern in patterns:
        match = re.search(pattern, clause, flags=re.IGNORECASE)
        if match:
            return _normalize_target_name(match.group("name"))
    return ""


def _extract_location_reference(clause: str, last_dir: Path | None) -> tuple[bool, Path | None]:
    match = re.search(
        r"\b(?:inside|in|under)\s+(?P<loc>that folder|that directory|it|there|(?:the\s+)?(?:folder|directory|dir)\s+(?:(?:named|called)\s+)?(?:\"[^\"]+\"|'[^']+'|[A-Za-z0-9][A-Za-z0-9._/-]*)|(?:\"[^\"]+\"|'[^']+'|[A-Za-z0-9][A-Za-z0-9._/-]*))",
        clause,
        flags=re.IGNORECASE,
    )
    if not match:
        return False, None
    raw = _normalize_target_name(match.group("loc"))
    if raw.lower() in {"that folder", "that directory", "it", "there"}:
        return True, last_dir
    return True, Path(raw) if raw else None


def _extract_generic_delete_target(clause: str, last_dir: Path | None) -> tuple[str, str] | None:
    token_pattern = r'"[^"]+"|\'[^\']+\'|[A-Za-z0-9][A-Za-z0-9._/-]*'
    match = re.search(
        rf"\b(?:delete|remove|rm)\s+(?:the\s+)?(?P<name>{token_pattern})(?=$|\s+(?:inside|in|under)\b)",
        clause,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    raw = _normalize_target_name(match.group("name"))
    if raw.lower() in {"it", "there"}:
        if last_dir is None:
            return None
        return last_dir.as_posix(), "dir"
    if not raw:
        return None
    if "/" in raw or "." in Path(raw).name:
        return raw, "path"
    return raw, "path"


def _extract_transfer_clause(clause: str, verbs: str) -> tuple[str, str, str] | None:
    token_pattern = r'"[^"]+"|\'[^\']+\'|[A-Za-z0-9][A-Za-z0-9._/-]*'
    patterns = (
        rf"\b(?:{verbs})\s+(?:the\s+)?(?:file|folder|directory|dir)?\s*(?P<src>{token_pattern})\s+(?P<link>to|into|under|inside)\s+(?:the\s+)?(?:folder|directory|dir)?\s*(?P<dst>{token_pattern})",
        rf"\b(?:{verbs})\s+(?:the\s+)?(?P<src>{token_pattern})\s+(?P<link>to|into|under|inside)\s+(?P<dst>{token_pattern})",
    )
    for pattern in patterns:
        match = re.search(pattern, clause, flags=re.IGNORECASE)
        if match:
            src = _normalize_target_name(match.group("src"))
            dst = _normalize_target_name(match.group("dst"))
            link = match.group("link").lower()
            if src and dst:
                return src, dst, link
    return None


def _extract_rename_clause(clause: str) -> tuple[str, str] | None:
    token_pattern = r'"[^"]+"|\'[^\']+\'|[A-Za-z0-9][A-Za-z0-9._/-]*'
    patterns = (
        rf"\brename\s+(?:the\s+)?(?:file|folder|directory|dir)?\s*(?P<src>{token_pattern})\s+to\s+(?P<dst>{token_pattern})",
        rf"\brename\s+(?:the\s+)?(?P<src>{token_pattern})\s+to\s+(?P<dst>{token_pattern})",
    )
    for pattern in patterns:
        match = re.search(pattern, clause, flags=re.IGNORECASE)
        if match:
            src = _normalize_target_name(match.group("src"))
            dst = _normalize_target_name(match.group("dst"))
            if src and dst:
                return src, dst
    return None


def _resolve_path(target: str, base_dir: str | Path) -> Path:
    base_path = Path(base_dir).expanduser().resolve()
    candidate = Path(os.path.expanduser(target))
    if not candidate.is_absolute():
        candidate = base_path / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base_path):
        raise ValueError(f"Path escapes the workspace: {target}")
    if ".git" in resolved.relative_to(base_path).parts:
        raise ValueError("Refusing to touch .git content for safety")
    return resolved


def _iter_missing_parent_dirs(path: Path, base_path: Path) -> list[Path]:
    missing: list[Path] = []
    current = path.parent
    while current != base_path and not current.exists():
        missing.append(current)
        current = current.parent
    missing.reverse()
    return missing


def _text_preview(content: str, max_lines: int = MAX_PREVIEW_LINES) -> list[str]:
    lines = content.splitlines()
    preview = lines[:max_lines]
    if len(lines) > max_lines:
        preview.append("…")
    return preview or ["(empty file)"]


def _diff_preview(old_text: str, new_text: str) -> list[str]:
    diff = list(
        unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile="current",
            tofile="planned",
            lineterm="",
        )
    )
    if len(diff) > MAX_DIFF_LINES:
        diff = diff[:MAX_DIFF_LINES] + ["… diff truncated …"]
    return diff


def _count_dir_contents(path: Path) -> tuple[int, int]:
    file_count = 0
    dir_count = 0
    for child in path.rglob("*"):
        if child.is_dir():
            dir_count += 1
        elif child.is_file():
            file_count += 1
    return file_count, dir_count


def _normalize_create_plan(plan: dict) -> dict:
    normalized = dict(plan)
    normalized.setdefault("operation", "create")
    normalized.setdefault("root", ".")
    normalized.setdefault("files", [])
    return normalized


def _resolve_create_entries(plan: dict, base_dir: str | Path) -> tuple[Path, list[dict[str, Any]]]:
    base_path = Path(base_dir).expanduser().resolve()
    normalized = _normalize_create_plan(plan)
    root = str(normalized.get("root", ".")).strip() or "."
    root_path = _resolve_path(root, base_path) if root != "." else base_path
    entries: list[dict[str, Any]] = []
    for raw in normalized.get("files", []):
        if not isinstance(raw, dict):
            continue
        rel_path = str(raw.get("path", "")).strip().lstrip("/")
        if not rel_path:
            continue
        full_path = _resolve_path(str(Path(root) / rel_path) if root != "." else rel_path, base_path)
        entries.append(
            {
                "path": full_path,
                "relative": str(full_path.relative_to(base_path)),
                "content": str(raw.get("content", "")),
            }
        )
    return root_path, entries


def _resolve_transfer_items(plan: dict, base_dir: str | Path) -> list[dict[str, Any]]:
    base_path = Path(base_dir).expanduser().resolve()
    operation = str(plan.get("operation", "")).strip()
    items: list[dict[str, Any]] = []
    for raw in plan.get("items", []):
        if not isinstance(raw, dict):
            continue
        source = _resolve_path(str(raw.get("source", "")).strip(), base_path)
        if not source.exists():
            raise ValueError(f"Source does not exist: {source.relative_to(base_path)}")
        destination_hint = str(raw.get("destination", "")).strip()
        if not destination_hint:
            continue
        link = str(raw.get("link", "to")).strip().lower()
        destination_seed = _resolve_path(destination_hint, base_path)
        if link in {"into", "inside", "under"} or destination_seed.is_dir():
            destination = destination_seed / source.name
        else:
            destination = destination_seed
        destination = destination.resolve()
        if not destination.is_relative_to(base_path):
            raise ValueError(f"Path escapes the workspace: {destination_hint}")
        if ".git" in destination.relative_to(base_path).parts:
            raise ValueError("Refusing to touch .git content for safety")
        items.append(
            {
                "operation": operation,
                "source": source,
                "destination": destination,
                "relative_source": str(source.relative_to(base_path)),
                "relative_destination": str(destination.relative_to(base_path)),
            }
        )
    return items


# ── AI-powered file plan generation ──────────────────────────────────────────

SYSTEM_PROMPT = """You are a file system agent. When asked to create files and folders,
you respond ONLY with a valid JSON object describing what to create.

Format:
{
  "root": "folder_name_or_dot",
  "files": [
    {
      "path": "relative/path/to/file.ext",
      "content": "full file content here"
    }
  ]
}

Rules:
- "root" is the top-level folder to create (use "." if no folder needed)
- "path" is relative to root
- "content" must be real, working, production-quality code — not placeholder comments
- For HTML: semantic structure, meta tags, link to CSS/JS
- For CSS: modern variables, reset, actual styles that look good
- For JS: real functionality, event listeners, no lorem ipsum
- For Python: real imports, real logic
- NEVER return anything except the JSON object — no explanation, no markdown fences
"""


def generate_file_plan(request: str, client, model: str) -> dict | None:
    """Ask AI to generate a JSON file plan. Three-strategy robust JSON extraction."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": request},
            ],
            max_tokens=4000,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip()

        # Strategy 1: strip fences and parse
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", raw, flags=re.MULTILINE)
        cleaned = re.sub(r"\n?```\s*$",        "", cleaned, flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Strategy 2: extract first {...} block
        m = re.search(r"\{[\s\S]+\}", cleaned)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

        # Strategy 3: retry with stricter instruction
        retry = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": request},
                {"role": "assistant", "content": raw},
                {
                    "role":    "user",
                    "content": (
                        "Output ONLY a raw JSON object. "
                        "No markdown, no explanation. Start with { end with }."
                    ),
                },
            ],
            max_tokens=4000,
            temperature=0.1,
        )
        raw2 = retry.choices[0].message.content.strip()
        m2   = re.search(r"\{[\s\S]+\}", raw2)
        if m2:
            return json.loads(m2.group())
        return None
    except Exception:
        return None


def generate_delete_plan(request: str) -> dict | None:
    """Parse a delete/remove request into a structured removal plan."""
    if not is_delete_request(request):
        return None

    targets: list[dict[str, str]] = []
    last_dir: Path | None = None

    for raw_clause in _split_operation_clauses(request):
        clause = re.sub(
            r"^(?:please|pls|can you|could you|would you|lumi|hey lumi|bro|hey|yo)\s+",
            "",
            raw_clause.strip(),
            flags=re.IGNORECASE,
        )
        if not clause:
            continue

        has_action = bool(re.search(r"\b(?:delete|remove|rm)\b", clause, flags=re.IGNORECASE))
        file_name = _extract_named_target(clause, "file", "delete|remove|rm")
        folder_name = _extract_named_target(clause, "folder|directory|dir", "delete|remove|rm")
        location_mentioned, location = _extract_location_reference(clause, last_dir)
        if location_mentioned and location is None:
            return None

        if file_name:
            full_path = (location / file_name) if location is not None else Path(file_name)
            targets.append({"path": full_path.as_posix(), "kind": "file"})
            last_dir = full_path.parent if full_path.parent != Path(".") else last_dir
            continue

        if folder_name:
            full_path = (location / folder_name) if location is not None else Path(folder_name)
            targets.append({"path": full_path.as_posix(), "kind": "dir"})
            last_dir = full_path
            continue

        generic = _extract_generic_delete_target(clause, last_dir)
        if generic:
            path_text, kind = generic
            full_path = (location / path_text) if location is not None else Path(path_text)
            targets.append({"path": full_path.as_posix(), "kind": kind})
            if kind == "dir":
                last_dir = full_path
            elif full_path.parent != Path("."):
                last_dir = full_path.parent
            continue

        if has_action:
            return None

    if not targets:
        return None

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for target in targets:
        key = (target["path"], target["kind"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)

    return {"operation": "delete", "targets": deduped}


def generate_transfer_plan(request: str) -> dict | None:
    """Parse move/copy/rename requests into a structured transfer plan."""
    operation = ""
    if is_rename_request(request):
        operation = "rename"
    elif is_move_request(request):
        operation = "move"
    elif is_copy_request(request):
        operation = "copy"
    if not operation:
        return None

    items: list[dict[str, str]] = []
    for raw_clause in _split_operation_clauses(request):
        clause = re.sub(
            r"^(?:please|pls|can you|could you|would you|lumi|hey lumi|bro|hey|yo)\s+",
            "",
            raw_clause.strip(),
            flags=re.IGNORECASE,
        )
        if not clause:
            continue
        if operation == "rename":
            pair = _extract_rename_clause(clause)
            if pair:
                src, dst = pair
                items.append({"source": src, "destination": dst, "link": "to"})
                continue
        else:
            pair = _extract_transfer_clause(clause, operation)
            if pair:
                src, dst, link = pair
                items.append({"source": src, "destination": dst, "link": link})
                continue
            if operation == "move" and clause.lower().startswith("rename "):
                pair = _extract_rename_clause(clause)
                if pair:
                    src, dst = pair
                    items.append({"source": src, "destination": dst, "link": "to"})
                    continue
        if re.search(rf"\b{operation}\b", clause, flags=re.IGNORECASE):
            return None

    if not items:
        return None
    return {"operation": operation, "items": items}


# ── File writing ──────────────────────────────────────────────────────────────

def write_file_plan(plan: dict, base_dir: str | Path = ".") -> list[str]:
    """Execute a file plan — create folders and write files.

    Returns the list of created paths (directories end with ``/``).

    Raises:
        ValueError: plan is structurally invalid or a path traversal is detected.
        PermissionError: the filesystem refused a write.
        OSError: any other I/O failure.
    """
    created: list[str] = []
    base_path = Path(base_dir).expanduser().resolve()

    root = plan.get("root", ".").strip()

    if root and root != ".":
        root_path = (base_path / root).resolve()
        # Guard against crafted root values like "../../etc"
        if not root_path.is_relative_to(base_path):
            raise ValueError(
                f"root '{root}' escapes the base directory (path traversal detected)"
            )
        root_path.mkdir(parents=True, exist_ok=True)
        created.append(str(root_path) + "/")
    else:
        root_path = base_path

    files = plan.get("files")
    if not isinstance(files, list):
        raise ValueError("Plan must contain a 'files' list")

    for f in files:
        if not isinstance(f, dict):
            continue

        rel_path = f.get("path", "").strip().lstrip("/")
        content  = f.get("content", "")

        if not rel_path:
            continue

        full_path = (root_path / rel_path).resolve()

        # Reject any path that escapes the root — covers "../../" tricks.
        if not full_path.is_relative_to(root_path):
            raise ValueError(
                f"Invalid path '{rel_path}': resolves outside the target directory "
                f"(path traversal detected)"
            )

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        created.append(str(full_path))

    return created


def delete_file_plan(plan: dict, base_dir: str | Path = ".") -> list[str]:
    """Execute a delete plan for files and directories inside the base directory."""
    base_path = Path(base_dir).expanduser().resolve()
    targets = plan.get("targets")
    if not isinstance(targets, list):
        raise ValueError("Plan must contain a 'targets' list")

    deleted: list[str] = []
    deleted_dirs: list[Path] = []
    sorted_targets = sorted(
        (target for target in targets if isinstance(target, dict)),
        key=lambda item: len(Path(str(item.get("path", ""))).parts),
        reverse=True,
    )

    for target in sorted_targets:
        rel_path = str(target.get("path", "")).strip().lstrip("/")
        kind = str(target.get("kind", "path")).strip() or "path"
        if not rel_path:
            continue

        resolved = (base_path / rel_path).resolve()
        if not resolved.is_relative_to(base_path):
            raise ValueError(
                f"Invalid path '{rel_path}': resolves outside the target directory "
                f"(path traversal detected)"
            )
        if resolved == base_path:
            raise ValueError("Refusing to delete the base directory")
        if ".git" in resolved.relative_to(base_path).parts:
            raise ValueError("Refusing to touch .git content for safety")
        if any(resolved == deleted_dir or deleted_dir in resolved.parents for deleted_dir in deleted_dirs):
            continue
        if not resolved.exists():
            raise ValueError(f"Target does not exist: {rel_path}")

        if resolved.is_dir():
            if kind == "file":
                raise ValueError(f"Expected a file but found a directory: {rel_path}")
            shutil.rmtree(resolved)
            deleted.append(str(resolved) + "/")
            deleted_dirs.append(resolved)
            continue

        if kind == "dir":
            raise ValueError(f"Expected a directory but found a file: {rel_path}")
        resolved.unlink()
        deleted.append(str(resolved))

    return deleted


def execute_transfer_plan(plan: dict, base_dir: str | Path = ".") -> list[str]:
    """Execute move/copy/rename items inside the base directory."""
    items = _resolve_transfer_items(plan, base_dir)
    changed: list[str] = []
    operation = str(plan.get("operation", "")).strip()

    for item in items:
        source = item["source"]
        destination = item["destination"]
        if not source.exists():
            raise ValueError(f"Source does not exist: {item['relative_source']}")
        if source == destination:
            raise ValueError(f"Source and destination are identical: {item['relative_source']}")
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()

        if operation == "copy":
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
        else:
            shutil.move(str(source), str(destination))

        changed.append(f"{item['relative_source']} -> {item['relative_destination']}")

    return changed


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def _top_level_delete_targets(plan: dict, base_dir: str | Path) -> list[Path]:
    base_path = Path(base_dir).expanduser().resolve()
    targets: list[Path] = []
    for raw in plan.get("targets", []):
        if not isinstance(raw, dict):
            continue
        rel_path = str(raw.get("path", "")).strip()
        if not rel_path:
            continue
        resolved = _resolve_path(rel_path, base_path)
        if not resolved.exists():
            raise ValueError(f"Target does not exist: {rel_path}")
        targets.append(resolved)
    targets.sort(key=lambda path: len(path.parts))
    top_level: list[Path] = []
    for path in targets:
        if any(parent == path or parent in path.parents for parent in top_level):
            continue
        top_level.append(path)
    return top_level


def _build_undo_record(plan: dict, base_dir: str | Path) -> dict[str, Any]:
    base_path = Path(base_dir).expanduser().resolve()
    operation = str(plan.get("operation", "create")).strip() or "create"
    UNDO_ROOT.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(tempfile.mkdtemp(prefix="fs-undo-", dir=UNDO_ROOT))

    touch_paths: list[Path] = []
    if operation == "create":
        root_path, entries = _resolve_create_entries(plan, base_path)
        touch_paths.extend(entry["path"] for entry in entries)
        if root_path != base_path and not root_path.exists():
            touch_paths.append(root_path)
        for entry in entries:
            touch_paths.extend(_iter_missing_parent_dirs(entry["path"], base_path))
    elif operation == "delete":
        touch_paths.extend(_top_level_delete_targets(plan, base_path))
    elif operation in {"move", "copy", "rename"}:
        for item in _resolve_transfer_items(plan, base_path):
            touch_paths.append(item["destination"])
            touch_paths.extend(_iter_missing_parent_dirs(item["destination"], base_path))
            if operation != "copy":
                touch_paths.append(item["source"])

    items: list[dict[str, Any]] = []
    for index, path in enumerate(_dedupe_paths(touch_paths), start=1):
        existed = path.exists()
        item: dict[str, Any] = {
            "path": str(path),
            "existed": existed,
            "kind": "dir" if path.is_dir() else "file",
        }
        if existed:
            backup_path = backup_dir / f"{index}"
            if path.is_dir():
                shutil.copytree(path, backup_path)
            else:
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup_path)
            item["backup"] = str(backup_path)
        items.append(item)

    return {"operation": operation, "backup_dir": str(backup_dir), "items": items}


def undo_operation(undo_record: dict[str, Any]) -> list[str]:
    """Undo the last filesystem mutation by restoring recorded snapshots."""
    items = list(undo_record.get("items", []))
    backup_dir = Path(str(undo_record.get("backup_dir", "")))
    restored: list[str] = []

    remove_only = sorted(
        (item for item in items if not item.get("existed")),
        key=lambda item: len(Path(str(item.get("path", ""))).parts),
        reverse=True,
    )
    for item in remove_only:
        path = Path(str(item.get("path", "")))
        if not path.exists():
            continue
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                shutil.rmtree(path)
        else:
            path.unlink()
        restored.append(str(path))

    restore_items = sorted(
        (item for item in items if item.get("existed")),
        key=lambda item: len(Path(str(item.get("path", ""))).parts),
    )
    for item in restore_items:
        path = Path(str(item.get("path", "")))
        backup = Path(str(item.get("backup", "")))
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        if item.get("kind") == "dir":
            shutil.copytree(backup, path)
        else:
            shutil.copy2(backup, path)
        restored.append(str(path))

    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    return restored


def execute_operation_plan(plan: dict, base_dir: str | Path = ".") -> dict[str, Any]:
    """Execute any supported filesystem operation and return summary + undo data."""
    base_path = Path(base_dir).expanduser().resolve()
    operation = str(plan.get("operation", "create")).strip() or "create"
    normalized_plan = _normalize_create_plan(plan) if operation == "create" else plan
    inspection = inspect_operation_plan(normalized_plan, base_path)
    undo_record = _build_undo_record(normalized_plan, base_path)

    if operation == "create":
        changed = write_file_plan(normalized_plan, base_path)
    elif operation == "delete":
        changed = delete_file_plan(normalized_plan, base_path)
    elif operation in {"move", "copy", "rename"}:
        changed = execute_transfer_plan(normalized_plan, base_path)
    else:
        raise ValueError(f"Unsupported filesystem operation: {operation}")

    return {
        "operation": operation,
        "changed": changed,
        "summary": inspection["result_summary"],
        "details": inspection["detail_lines"],
        "undo": undo_record,
    }


def inspect_operation_plan(plan: dict, base_dir: str | Path = ".") -> dict[str, Any]:
    """Inspect a plan and return counts, previews, and confirmation text."""
    base_path = Path(base_dir).expanduser().resolve()
    operation = str(plan.get("operation", "create")).strip() or "create"
    summary_lines: list[str] = []
    detail_lines: list[str] = []
    preview_lines: list[str] = []
    counts: dict[str, int] = {
        "files": 0,
        "dirs": 0,
        "overwrites": 0,
        "delete_files": 0,
        "delete_dirs": 0,
        "items": 0,
    }

    if operation == "create":
        root_path, entries = _resolve_create_entries(plan, base_path)
        missing_dirs: list[Path] = []
        if root_path != base_path and not root_path.exists():
            missing_dirs.append(root_path)
        for entry in entries:
            missing_dirs.extend(_iter_missing_parent_dirs(entry["path"], base_path))
            counts["files"] += 1
            path = entry["path"]
            if path.exists() and path.is_file():
                counts["overwrites"] += 1
                old_text = path.read_text(encoding="utf-8", errors="replace")
                preview_lines.append(f"  ~ {entry['relative']}  (overwrite)")
                for line in _diff_preview(old_text, entry["content"]):
                    preview_lines.append(f"    {line}")
            else:
                preview_lines.append(f"  + {entry['relative']}")
                for line in _text_preview(entry["content"]):
                    preview_lines.append(f"    {line}")
        counts["dirs"] = len(_dedupe_paths([path for path in missing_dirs if path != base_path]))
        summary_lines.append(f"Create {counts['dirs']} folder(s) and {counts['files']} file(s)")
        detail_lines.append(f"workspace  {base_path}")
        detail_lines.append(f"folders  {counts['dirs']} · files  {counts['files']} · overwrites  {counts['overwrites']}")
        detail_lines.append("shortcuts  y yes confirm apply · n no cancel · Enter cancel")
        result_summary = f"Created {counts['files']} file(s) and {counts['dirs']} folder(s)."

    elif operation == "delete":
        targets = _top_level_delete_targets(plan, base_path)
        counts["items"] = len(targets)
        for target in targets:
            rel = str(target.relative_to(base_path))
            if target.is_dir():
                files, dirs = _count_dir_contents(target)
                counts["dirs"] += 1
                counts["delete_files"] += files
                counts["delete_dirs"] += dirs
                preview_lines.append(f"  - {rel}/  ({files} file(s), {dirs} subfolder(s))")
            else:
                counts["files"] += 1
                preview_lines.append(f"  - {rel}")
        summary_lines.append(
            f"Remove {counts['dirs']} folder(s) and {counts['files'] + counts['delete_files']} file(s)"
        )
        detail_lines.append(f"workspace  {base_path}")
        detail_lines.append(
            f"folders  {counts['dirs']} · files  {counts['files'] + counts['delete_files']} · nested folders  {counts['delete_dirs']}"
        )
        detail_lines.append("shortcuts  y yes confirm apply · n no cancel · Enter cancel")
        result_summary = (
            f"Removed {counts['dirs']} folder(s) and {counts['files'] + counts['delete_files']} file(s)."
        )

    elif operation in {"move", "copy", "rename"}:
        items = _resolve_transfer_items(plan, base_path)
        counts["items"] = len(items)
        for item in items:
            source = item["source"]
            destination = item["destination"]
            if destination.exists():
                counts["overwrites"] += 1
            label = "~" if destination.exists() else "→"
            kind = "folder" if source.is_dir() else "file"
            preview_lines.append(
                f"  {label} {item['relative_source']} -> {item['relative_destination']}  ({kind})"
            )
        summary_lines.append(
            f"{operation.capitalize()} {counts['items']} path(s)"
        )
        detail_lines.append(f"workspace  {base_path}")
        detail_lines.append(f"items  {counts['items']} · overwrites  {counts['overwrites']}")
        detail_lines.append("shortcuts  y yes confirm apply · n no cancel · Enter cancel")
        past_tense = {"move": "Moved", "copy": "Copied", "rename": "Renamed"}[operation]
        result_summary = f"{past_tense} {counts['items']} path(s)."

    else:
        raise ValueError(f"Unsupported filesystem operation: {operation}")

    return {
        "operation": operation,
        "summary_lines": summary_lines,
        "detail_lines": detail_lines,
        "preview_lines": preview_lines[:80],
        "counts": counts,
        "result_summary": result_summary,
    }


# ── Summary formatter ─────────────────────────────────────────────────────────

def format_creation_summary(plan: dict, created: list[str]) -> str:
    """Return a human-readable summary of what was created."""
    root  = plan.get("root", ".")
    files = plan.get("files", [])
    lines: list[str] = []
    if root != ".":
        lines.append(f"📁 {root}/")
    for f in files:
        path    = f.get("path", "")
        size    = len(f.get("content", "").encode())
        lines.append(f"   📄 {path}  ({size:,} bytes)")
    return "\n".join(lines)


def format_delete_summary(plan: dict) -> str:
    """Return a human-readable summary of what will be removed."""
    lines: list[str] = []
    for target in plan.get("targets", []):
        if not isinstance(target, dict):
            continue
        path = str(target.get("path", "")).strip()
        kind = str(target.get("kind", "path")).strip() or "path"
        if not path:
            continue
        if kind == "dir":
            lines.append(f"  📁 {path}/")
        elif kind == "file":
            lines.append(f"  📄 {path}")
        else:
            lines.append(f"  🗑 {path}")
    return "\n".join(lines)


def suggest_paths(text: str, base_dir: str | Path = ".", limit: int = MAX_SUGGESTIONS) -> dict[str, Any] | None:
    """Suggest file paths while the user is typing a filesystem request."""
    if not text or not is_filesystem_request(text):
        return None

    prefix = text.rstrip("\n")
    path_match = re.search(r"([A-Za-z0-9._/-]*)$", prefix)
    if not path_match:
        return None
    fragment = path_match.group(1)
    start = path_match.start(1)
    end = path_match.end(1)
    context = prefix[:start].lower()
    if not re.search(r"(create|make|add|delete|remove|rm|move|copy|rename|inside|under|into|to|from|file|folder|directory|dir)\s*$", context):
        return None

    base_path = Path(base_dir).expanduser().resolve()
    normalized_fragment = fragment.lstrip("/")
    directory_hint = Path(normalized_fragment).parent.as_posix() if "/" in normalized_fragment else ""
    name_hint = Path(normalized_fragment).name if normalized_fragment else ""
    search_root = _resolve_path(directory_hint, base_path) if directory_hint else base_path
    if not search_root.exists():
        return None
    if search_root.is_file():
        return {
            "fragment": fragment,
            "start": start,
            "end": end,
            "items": [str(search_root.relative_to(base_path))],
        }

    candidates: list[str] = []
    for child in sorted(search_root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name.startswith(".git"):
            continue
        if name_hint and not child.name.lower().startswith(name_hint.lower()):
            continue
        rel = str(child.relative_to(base_path))
        if child.is_dir():
            rel += "/"
        candidates.append(rel)
        if len(candidates) >= limit:
            break

    if not candidates:
        return None
    return {"fragment": fragment, "start": start, "end": end, "items": candidates}
