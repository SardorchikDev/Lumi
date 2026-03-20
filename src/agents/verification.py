"""Verification command helpers for Lumi agent execution."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path


def summarize_verification_output(command: tuple[str, ...], output: str) -> str:
    lowered = output.lower()
    summary_bits = [" ".join(command)]
    match = re.search(r"(\d+)\s+passed", lowered)
    if match:
        summary_bits.append(f"{match.group(1)} passed")
    match = re.search(r"(\d+)\s+failed", lowered)
    if match:
        summary_bits.append(f"{match.group(1)} failed")
    match = re.search(r"found\s+(\d+)\s+error", lowered)
    if match:
        summary_bits.append(f"{match.group(1)} errors")
    if "success" in lowered and len(summary_bits) == 1:
        summary_bits.append("success")
    preview = output[:600].rstrip()
    if preview:
        summary_bits.append(preview)
    return " | ".join(summary_bits)


def classify_failure_output(output: str) -> str:
    lowered = (output or "").lower()
    if any(token in lowered for token in ("timed out", "timeout")):
        return "timeout"
    if any(token in lowered for token in ("not found", "no such file", "does not exist")):
        return "missing_path"
    if any(token in lowered for token in ("syntaxerror", "parse error", "yamlerror", "jsondecodeerror")):
        return "syntax_or_parse_error"
    if any(token in lowered for token in ("ambiguous", "matched multiple", "old_text was not found", "old_block does not match")):
        return "stale_patch_context"
    if any(token in lowered for token in ("failed", "error", "assert", "traceback", "exception")):
        return "verification_or_runtime_error"
    return "unknown"


def run_verification_command(
    command: tuple[str, ...],
    base_dir: Path,
    *,
    timeout: int = 90,
    run_command: Callable[[list[str], Path, int], tuple[bool, str]],
) -> tuple[bool, str]:
    ok, output = run_command(list(command), base_dir, timeout=timeout)
    return ok, summarize_verification_output(command, output)
