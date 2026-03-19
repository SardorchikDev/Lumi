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
        base_dir=tmp_path,
    )
    context = task_memory.render_task_memory_context("parser", base_dir=tmp_path)
    assert "Recent agent task memory:" in context
    assert "fix parser" in context
    assert "src/parser.py" in context


def test_active_run_is_rendered_and_cleared(monkeypatch, tmp_path):
    monkeypatch.setattr(task_memory, "TASK_MEMORY_PATH", tmp_path / "task_memory.json")
    task_memory.start_active_run("build api", base_dir=tmp_path)
    task_memory.update_active_run(
        status="running",
        summary="editing routes",
        touched_files=["src/api.py"],
        failed_checks=["tests"],
        base_dir=tmp_path,
    )
    context = task_memory.render_task_memory_context("api", base_dir=tmp_path)
    assert "* active [running] build api" in context
    assert "src/api.py" in context
    task_memory.clear_active_run()
    assert task_memory.get_active_run() is None


def test_render_context_filters_other_workspaces(monkeypatch, tmp_path):
    monkeypatch.setattr(task_memory, "TASK_MEMORY_PATH", tmp_path / "task_memory.json")
    workspace_a = tmp_path / "repo-a"
    workspace_b = tmp_path / "repo-b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    task_memory.record_run(
        "fix auth",
        status="completed",
        summary="updated auth flow",
        touched_files=["src/auth.py"],
        base_dir=workspace_a,
    )
    task_memory.record_run(
        "fix billing",
        status="completed",
        summary="updated billing flow",
        touched_files=["src/billing.py"],
        base_dir=workspace_b,
    )

    context = task_memory.render_task_memory_context("auth", base_dir=workspace_a)

    assert "fix auth" in context
    assert "fix billing" not in context
