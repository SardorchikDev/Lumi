"""Validation tests for the Lumi installer script."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_script_has_valid_bash_syntax():
    subprocess.run(["bash", "-n", "install.sh"], cwd=ROOT, check=True)


def test_install_help_lists_supported_flags():
    result = subprocess.run(
        ["bash", "install.sh", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "--dev" in result.stdout
    assert "--dir <path>" in result.stdout
    assert "--bin-dir <path>" in result.stdout
    assert "--no-path" in result.stdout


def test_install_script_templates_runtime_and_provider_envs():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "LUMI_STATE_DIR" in text
    assert "LUMI_CACHE_DIR" in text
    assert "AIRFORCE_API_KEY" in text
    assert "POLLINATIONS_API_KEY" in text
