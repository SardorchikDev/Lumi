"""Tests for the offline benchmark gate script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_gate(config_path: Path, workspace: Path) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_gate.py"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--config",
            str(config_path),
            "--workspace",
            str(workspace),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_benchmark_gate_passes_with_default_thresholds(tmp_path):
    config_path = Path(__file__).resolve().parents[1] / "configs" / "benchmark_gate.json"

    result = _run_gate(config_path, tmp_path)

    assert result.returncode == 0
    assert "Benchmark gate passed." in result.stdout


def test_benchmark_gate_fails_when_thresholds_are_too_strict(tmp_path):
    config_path = tmp_path / "strict_gate.json"
    config_path.write_text(
        json.dumps(
            {
                "scenarios": ["scaffold-python", "patch-bug"],
                "minimum": {
                    "pass_rate": 1.0,
                    "average_score": 1.1,
                    "verification_pass_rate": 1.0,
                },
            }
        ),
        encoding="utf-8",
    )

    result = _run_gate(config_path, tmp_path)

    assert result.returncode == 1
    assert "Benchmark gate failed:" in result.stdout
    assert "average_score" in result.stdout
