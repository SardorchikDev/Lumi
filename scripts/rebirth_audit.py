#!/usr/bin/env python3
"""Audit Lumi - rebirth capability readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.rebirth import collect_rebirth_capabilities, rebirth_readiness, render_rebirth_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Lumi - rebirth capability readiness")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail with non-zero exit if any capability is missing",
    )
    parser.add_argument(
        "--json",
        default="",
        help="Optional path to write machine-readable audit output",
    )
    args = parser.parse_args(argv)

    capabilities = collect_rebirth_capabilities()
    ready, total, ratio = rebirth_readiness()
    missing = [cap for cap in capabilities if not cap.ready]

    print(render_rebirth_report())

    payload = {
        "ready": ready,
        "total": total,
        "ratio": ratio,
        "missing": [
            {
                "key": cap.key,
                "name": cap.name,
                "command": cap.command,
                "detail": cap.detail,
            }
            for cap in missing
        ],
    }
    if args.json:
        output_path = Path(args.json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    if args.strict and missing:
        print("\nRebirth audit failed: missing capabilities detected.")
        for cap in missing:
            print(f"  - {cap.name} ({cap.command})")
        return 1

    print("\nRebirth audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
