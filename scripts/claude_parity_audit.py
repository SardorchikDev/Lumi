#!/usr/bin/env python3
"""Audit Lumi's parity against the Claude command catalog."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.claude_parity import (  # noqa: E402
    claude_parity_summary,
    collect_beacon_workstreams,
    collect_command_parity,
    render_claude_parity_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Lumi against the Claude command catalog")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail with non-zero exit if any Claude command or Beacon workstream is still missing",
    )
    parser.add_argument(
        "--json",
        default="",
        help="Optional path to write machine-readable audit output",
    )
    args = parser.parse_args(argv)

    categories = collect_command_parity(ROOT)
    present, total, ratio = claude_parity_summary(ROOT)
    missing_commands = [
        {"category": item.name, "command": command}
        for item in categories
        for command in item.missing
    ]
    workstreams = collect_beacon_workstreams()

    print(render_claude_parity_report(ROOT))

    payload = {
        "present": present,
        "total": total,
        "ratio": ratio,
        "missing_commands": missing_commands,
        "workstreams": [
            {
                "key": item.key,
                "name": item.name,
                "target": item.target,
                "rewrite_relevant": item.rewrite_relevant,
            }
            for item in workstreams
        ],
    }
    if args.json:
        output_path = Path(args.json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    if args.strict and (missing_commands or workstreams):
        print("\nClaude parity audit failed: Lumi is not yet at 1:1 parity.")
        print(f"  Missing command tokens: {len(missing_commands)}")
        print(f"  Beacon workstreams remaining: {len(workstreams)}")
        return 1

    print("\nClaude parity audit completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
