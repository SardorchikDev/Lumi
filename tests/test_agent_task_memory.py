"""Tests for persistent agent task memory."""

from __future__ import annotations

from src.agents import task_memory


def test_record_run_and_render_context(monkeypatch, tmp_path):
    monkeypatch.setattr(task_memory, "TASK_MEMORY_PATH", tmp_path / "task_memory.json")
    task_memory.record_run(
        "fix parser",
        status="completed",
        summary="updated parser logic",
        touched_files=["src/parser.py"],
        failed_checks=["tests"],
    )
    context = task_memory.render_task_memory_context("parser")
    assert "Recent agent task memory:" in context
    assert "fix parser" in context
    assert "src/parser.py" in context
