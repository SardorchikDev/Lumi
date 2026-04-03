"""Tests for the Lumi Mirror Workbench subsystem."""

from __future__ import annotations

from src.memory.short_term import ShortTermMemory
from src.utils import workbench


def _seed_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(workbench, "WORKBENCH_STATE_DIR", tmp_path / ".wb-state")
    monkeypatch.setattr(workbench, "WORKBENCH_CACHE_DIR", tmp_path / ".wb-cache")
    monkeypatch.setattr(workbench, "PROJECT_MEMORY_PATH", tmp_path / ".wb-state" / "project_memory.json")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "from src.utils import helper\n\nclass Engine:\n    pass\n\n\ndef run_app(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "utils.py").write_text(
        "def helper() -> str:\n    return 'ok'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_app.py").write_text(
        "from src.app import run_app\n\n\ndef test_run_app() -> None:\n    assert run_app(1) == 2\n",
        encoding="utf-8",
    )
    (tmp_path / "LUMI.md").write_text(
        "# Project Context\n- Prefer small focused functions.\n- Use pytest for regression coverage.\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")


def test_build_repo_intelligence_indexes_symbols_and_tests(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    intelligence = workbench.build_repo_intelligence(tmp_path, task="update app")
    cached = workbench.load_cached_repo_intelligence(tmp_path)

    assert intelligence.symbol_count >= 2
    assert "python" in intelligence.languages
    assert "src/app.py" in intelligence.relevant_files or "src/app.py" in intelligence.impact_files
    assert "tests/test_app.py" in intelligence.suggested_tests
    assert cached is not None
    assert cached.symbol_count == intelligence.symbol_count
    assert "Mirror" in workbench.workbench_status_summary(tmp_path)


def test_project_memory_persists_conventions_and_decisions(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    workbench.remember_project_decision(tmp_path, "Keep ship artifacts concise.")
    profile = workbench.load_project_memory(tmp_path)

    assert any("Prefer small focused functions." in item for item in profile.conventions)
    assert profile.decisions[0] == "Keep ship artifacts concise."


def test_prepare_workbench_plan_sets_risk_and_steps(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    plan = workbench.prepare_workbench_plan(
        "build",
        "Delete old auth flow and rewrite CI checks",
        base_dir=tmp_path,
        dry_run=True,
    )

    assert plan.mode == "build"
    assert plan.dry_run is True
    assert plan.risk_level == "high"
    assert any("delete" in warning for warning in plan.safety_warnings)
    assert any("apply changes" in step for step in plan.suggested_steps)


def test_execute_workbench_learn_generates_digest_and_artifacts(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    result = workbench.execute_workbench("learn", "map the repo", base_dir=tmp_path)

    assert "indexed" in result.summary.lower()
    assert result.artifacts.commit_title.startswith("map:")
    assert result.project_memory.recent_runs[0]["mode"] == "learn"
    assert "Workspace:" in result.artifacts.architecture_summary


def test_execute_workbench_build_uses_agent_runner_and_captures_log(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    def fake_run_agent(task, client, model, memory, system_prompt, yolo, review_only):
        print("planned safe edits")
        assert task == "Implement parser support"
        assert yolo is True
        assert review_only is False
        assert memory.get() == []
        return "Agent completed 2/2 steps"

    result = workbench.execute_workbench(
        "build",
        "Implement parser support",
        client=object(),
        model="gemini-2.5-flash",
        memory=ShortTermMemory(max_turns=4),
        system_prompt="You are Lumi.",
        base_dir=tmp_path,
        run_agent_fn=fake_run_agent,
    )

    assert result.summary == "Agent completed 2/2 steps"
    assert "planned safe edits" in result.execution_log
    assert result.project_memory.recent_runs[0]["mode"] == "build"
    assert result.artifacts.commit_title.startswith("build:")
