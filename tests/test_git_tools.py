"""Tests for shared git command helpers."""

from __future__ import annotations

import subprocess

from src.utils.git_tools import run_git_subcommand


def _init_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Lumi Test"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "lumi@example.com"], cwd=path, check=True, capture_output=True, text=True)


def test_run_git_subcommand_status_and_branches(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "notes.txt").write_text("hi\n", encoding="utf-8")

    ok, status = run_git_subcommand("status", cwd=tmp_path)
    assert ok is True
    assert "notes.txt" in status

    subprocess.run(["git", "add", "notes.txt"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)

    ok, branches = run_git_subcommand("branches", cwd=tmp_path)
    assert ok is True
    assert "*" in branches


def test_run_git_subcommand_remote_and_sync_without_remotes(tmp_path):
    _init_repo(tmp_path)

    ok, remote = run_git_subcommand("remote", cwd=tmp_path)
    assert ok is True
    assert "no remotes configured" in remote.lower()

    ok, sync = run_git_subcommand("sync", cwd=tmp_path)
    assert ok is True
    assert "status" in sync.lower()


def test_run_git_subcommand_unknown():
    ok, output = run_git_subcommand("nope")
    assert ok is False
    assert "Unknown git subcommand" in output
