"""Tests for shared Lumi status and onboarding reports."""

from __future__ import annotations

from src.agents import task_memory
from src.memory import longterm
from src.utils import plugins, system_reports
from src.utils.system_reports import build_doctor_report, build_onboarding_report, build_status_report


def test_build_status_report_includes_workspace_and_memory(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    monkeypatch.setattr(longterm, "MEMORY_FILE", tmp_path / "longterm.json")
    monkeypatch.setattr(longterm, "EPISODIC_DB_PATH", tmp_path / "episodes.sqlite3")
    monkeypatch.setattr(longterm, "LEGACY_EPISODIC_DB_PATH", tmp_path / "episodes.pkl")
    monkeypatch.setattr(task_memory, "TASK_MEMORY_PATH", tmp_path / "task_memory.json")
    task_memory.start_active_run("inspect api", base_dir=tmp_path)
    longterm.add_fact("User prefers concise replies")
    plugins._registry.clear()
    plugins._plugin_meta.clear()

    report = build_status_report(
        base_dir=tmp_path,
        provider="huggingface",
        model="meta-llama/Llama-3.3-70B-Instruct",
        session_turns=3,
        short_term_stats={"total_messages": 6, "user_messages": 3, "assistant_messages": 3},
        recent_commands=["/agent", "/status"],
    )

    assert "Lumi status" in report
    assert "User prefers concise replies" not in report
    assert "Turns:     3" in report
    assert "huggingface".lower() not in report.lower() or "HuggingFace" in report
    assert "Agent:     running" in report
    assert "Checks:" in report
    assert "Runtime:" in report
    assert "Rebirth:" in report
    assert "Workbench:" in report


def test_build_doctor_report_surfaces_missing_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(longterm, "MEMORY_FILE", tmp_path / "longterm.json")
    monkeypatch.setattr(longterm, "EPISODIC_DB_PATH", tmp_path / "episodes.sqlite3")
    monkeypatch.setattr(longterm, "LEGACY_EPISODIC_DB_PATH", tmp_path / "episodes.pkl")
    monkeypatch.setattr(system_reports, "LUMI_HOME", tmp_path / "lumi-home")
    plugins._registry.clear()
    plugins._plugin_meta.clear()

    report = build_doctor_report(
        base_dir=tmp_path,
        provider="",
        model="",
        configured_providers=[],
    )

    assert "Lumi doctor" in report
    assert "No configured providers detected." in report
    assert "No LUMI.md project context file found." in report
    assert "No .env file found" in report
    assert "Runtime:" in report
    assert "Rebirth:" in report
    assert "Workbench:" in report


def test_build_onboarding_report_includes_workspace_summary(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("# Lumi\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    monkeypatch.setattr(system_reports, "LUMI_HOME", tmp_path / "lumi-home")

    report = build_onboarding_report(
        base_dir=tmp_path,
        configured_providers=["huggingface", "gemini", "groq"],
    )

    assert "Lumi onboarding" in report
    assert "Workspace:" in report
    assert "Source:" in report
    assert "Tests:" in report
    assert "Starter prompts" in report
    assert "Shortcuts" in report
    assert "/image <path> [question]" in report
