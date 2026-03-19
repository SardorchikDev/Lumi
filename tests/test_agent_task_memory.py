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


def test_active_run_is_rendered_and_cleared(monkeypatch, tmp_path):
    monkeypatch.setattr(task_memory, "TASK_MEMORY_PATH", tmp_path / "task_memory.json")
    task_memory.start_active_run("build api")
    task_memory.update_active_run(
        status="running",
        summary="editing routes",
        touched_files=["src/api.py"],
        failed_checks=["tests"],
    )
    context = task_memory.render_task_memory_context("api")
    assert "* active [running] build api" in context
    assert "src/api.py" in context
    task_memory.clear_active_run()
    assert task_memory.get_active_run() is None
