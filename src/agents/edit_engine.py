"""Low-level file mutation helpers for Lumi agent execution."""

from __future__ import annotations

import re
import tempfile
from difflib import unified_diff
from pathlib import Path


def build_file_write_preview(
    path: Path,
    new_content: str,
    *,
    max_diff_lines: int = 80,
    max_diff_chars: int = 4000,
) -> str:
    if not path.exists():
        return ""
    try:
        old_content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"[Could not read existing file for preview: {exc}]"
    if old_content == new_content:
        return "[No changes]"
    diff_lines = list(
        unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"{path.name} (current)",
            tofile=f"{path.name} (agent)",
            lineterm="",
        )
    )
    truncated = False
    if len(diff_lines) > max_diff_lines:
        diff_lines = diff_lines[:max_diff_lines]
        truncated = True
    preview = "\n".join(diff_lines)
    if len(preview) > max_diff_chars:
        preview = preview[:max_diff_chars].rstrip()
        truncated = True
    if truncated:
        preview += "\n... diff truncated ..."
    return preview


def compute_patch_file_update(step: dict, path: Path) -> tuple[bool, str]:
    old_text = str(step.get("old_text", ""))
    new_text = str(step.get("new_text", ""))
    replace_all = bool(step.get("replace_all", False))
    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)
    matches = current.count(old_text)
    if matches == 0:
        return False, "Blocked: patch_file old_text was not found"
    if matches > 1 and not replace_all:
        return False, "Blocked: patch_file old_text is ambiguous; set replace_all=true"
    updated = current.replace(old_text, new_text) if replace_all else current.replace(old_text, new_text, 1)
    return True, updated


def compute_patch_lines_update(step: dict, path: Path) -> tuple[bool, str]:
    try:
        start_line = int(step.get("start_line"))
        end_line = int(step.get("end_line"))
    except (TypeError, ValueError):
        return False, "Blocked: patch_lines requires integer line bounds"
    if start_line < 1 or end_line < start_line:
        return False, "Blocked: patch_lines has invalid line bounds"

    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)

    lines = current.splitlines(keepends=True)
    if end_line > len(lines):
        return False, "Blocked: patch_lines line range is outside the file"

    current_block = "".join(lines[start_line - 1:end_line])
    old_block = step.get("old_block")
    if old_block is not None and str(old_block) != current_block:
        return False, "Blocked: patch_lines old_block does not match the current file"

    replacement = str(step.get("replacement", ""))
    new_lines = replacement.splitlines(keepends=True)
    if replacement and not replacement.endswith(("\n", "\r")) and current_block.endswith("\n"):
        new_lines.append("\n")
    updated_lines = lines[:start_line - 1] + new_lines + lines[end_line:]
    return True, "".join(updated_lines)


def compute_patch_context_update(step: dict, path: Path) -> tuple[bool, str]:
    before_context = str(step.get("before_context", ""))
    after_context = str(step.get("after_context", ""))
    old_block = step.get("old_block")
    replacement = str(step.get("replacement", ""))

    if not before_context and not after_context:
        return False, "Blocked: patch_context requires before_context or after_context"
    if old_block is None and not (before_context and after_context):
        return False, "Blocked: patch_context requires old_block when only one context anchor is provided"

    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)

    matches: list[tuple[int, int]] = []
    expected = str(old_block) if old_block is not None else None

    if before_context and after_context:
        search_from = 0
        while True:
            before_index = current.find(before_context, search_from)
            if before_index == -1:
                break
            start = before_index + len(before_context)
            end = current.find(after_context, start)
            if end != -1:
                matches.append((start, end))
            search_from = before_index + 1
    elif before_context:
        token = before_context + expected
        search_from = 0
        while True:
            match_index = current.find(token, search_from)
            if match_index == -1:
                break
            start = match_index + len(before_context)
            end = start + len(expected)
            matches.append((start, end))
            search_from = match_index + 1
    else:
        token = expected + after_context
        search_from = 0
        while True:
            match_index = current.find(token, search_from)
            if match_index == -1:
                break
            start = match_index
            end = start + len(expected)
            matches.append((start, end))
            search_from = match_index + 1

    if not matches:
        return False, "Blocked: patch_context could not find a matching anchored block"
    if len(matches) > 1:
        return False, "Blocked: patch_context matched multiple regions"

    start, end = matches[0]
    current_block = current[start:end]
    if expected is not None and current_block != expected:
        return False, "Blocked: patch_context old_block does not match the current file"
    if replacement and not replacement.endswith(("\n", "\r")) and current_block.endswith("\n"):
        replacement += "\n"
    updated = current[:start] + replacement + current[end:]
    return True, updated


def compute_patch_apply_update(step: dict, path: Path) -> tuple[bool, str]:
    hunks = step.get("hunks", [])
    if not isinstance(hunks, list) or not hunks:
        return False, "Blocked: patch_apply requires a non-empty hunks list"
    try:
        current = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)

    updated = current
    for index, raw_hunk in enumerate(hunks, start=1):
        if not isinstance(raw_hunk, dict):
            return False, f"Blocked: patch_apply hunk {index} is not an object"
        temp_step = dict(raw_hunk)
        temp_step.setdefault("path", str(path))
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write(updated)
            temp_path = Path(handle.name)
        try:
            if "old_text" in temp_step:
                ok, updated = compute_patch_file_update(temp_step, temp_path)
            elif temp_step.get("start_line") is not None or temp_step.get("end_line") is not None:
                ok, updated = compute_patch_lines_update(temp_step, temp_path)
            elif temp_step.get("before_context") or temp_step.get("after_context"):
                ok, updated = compute_patch_context_update(temp_step, temp_path)
            else:
                return False, f"Blocked: patch_apply hunk {index} has no supported patch shape"
        finally:
            temp_path.unlink(missing_ok=True)
        if not ok:
            return False, f"Blocked: patch_apply hunk {index} failed: {updated}"
        if updated == current:
            return False, f"Blocked: patch_apply hunk {index} made no changes"
        current = updated
    return True, updated


def detect_symbol_pattern(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return r"^\s*(def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"
    if suffix in {".js", ".ts", ".jsx", ".tsx"}:
        return r"^\s*(export\s+)?(async\s+)?(function|class|const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)"
    if suffix == ".go":
        return r"^\s*func\s+([A-Za-z_][A-Za-z0-9_]*)"
    if suffix == ".rs":
        return r"^\s*(pub\s+)?(fn|struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)"
    return ""


def search_symbols(base_dir: Path, target: Path, symbol: str, symbol_kind: str = "") -> str:
    matches: list[str] = []
    for path in sorted(target.rglob("*")) if target.is_dir() else [target]:
        if not path.is_file():
            continue
        pattern = detect_symbol_pattern(path)
        if not pattern:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        regex = re.compile(pattern)
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = regex.search(line)
            if not match:
                continue
            groups = match.groups()
            name = next((group for group in reversed(groups) if group and re.match(r"[A-Za-z_$]", group)), "")
            kind = next((group for group in groups if group in {"def", "class", "function", "const", "let", "var", "fn", "struct", "enum", "trait"}), "")
            if symbol and symbol.lower() not in name.lower():
                continue
            if symbol_kind and kind and symbol_kind.lower() != kind.lower():
                continue
            matches.append(f"{path.relative_to(base_dir)}:{lineno}: {kind or 'symbol'} {name}".strip())
            if len(matches) >= 50:
                return "\n".join(matches) + "\n... symbol search truncated ..."
    return "\n".join(matches) if matches else "(no symbols found)"
