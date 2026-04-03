"""Tests for the Lumi Beacon Workbench subsystem."""

from __future__ import annotations

from types import SimpleNamespace

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
        "from src.utils import helper\n\nclass Engine:\n    pass\n\n\ndef run_app(value: int) -> int:\n    return value + 1 if helper() == 'ok' else value\n",
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
    assert "Beacon" in workbench.workbench_status_summary(tmp_path)


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
        assert "Implement parser support" in task
        assert "run detected verification commands" in task
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


def test_workbench_job_history_persists_and_renders(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    job = workbench.create_workbench_job("build", "Implement parser support", base_dir=tmp_path, job_id="wb-7")
    job = workbench.update_workbench_job(
        job,
        status="done",
        stage="artifacts ready",
        risk="low",
        summary="Created parser support",
        touched_files=("src/app.py", "tests/test_app.py"),
        failed_checks=(),
        log_excerpt="tests: rc=0 · ok",
    )
    workbench.save_workbench_job(job)

    loaded = workbench.load_workbench_jobs(tmp_path)
    report = workbench.render_workbench_jobs_report(tmp_path)

    assert loaded
    assert loaded[0].status == "done"
    assert loaded[0].touched_files[0] == "src/app.py"
    assert "[done] build" in report
    assert "Created parser support" in report
    assert "tests: rc=0" in report


def test_execute_workbench_passes_base_dir_to_agent_runner_when_supported(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    captured: dict[str, object] = {}

    def fake_run_agent(task, client, model, memory, system_prompt, yolo, review_only, *, base_dir=None):
        captured["task"] = task
        captured["base_dir"] = base_dir
        return "Agent completed 1/1 steps"

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

    assert result.summary == "Agent completed 1/1 steps"
    assert "Implement parser support" in str(captured["task"])
    assert captured["base_dir"] == tmp_path


def test_render_workbench_report_supports_symbol_refs_and_impact(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    symbol_report = workbench.render_workbench_report(tmp_path, task="symbol run_app")
    refs_report = workbench.render_workbench_report(tmp_path, task="refs helper")
    impact_report = workbench.render_workbench_report(tmp_path, task="impact src/utils.py")

    assert "Symbol search: run_app" in symbol_report
    assert "src/app.py" in symbol_report
    assert "References: helper" in refs_report
    assert "src/app.py" in refs_report
    assert "Impact analysis: src/utils.py" in impact_report
    assert "src/utils.py" in impact_report
    assert "src/app.py" in impact_report


def test_execute_workbench_review_returns_model_findings(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    class FakeCompletions:
        def create(self, **kwargs):
            prompt = kwargs["messages"][-1]["content"]
            assert "Findings first." in prompt
            assert "Changed files:" in prompt
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="High: src/app.py:7 can hide input validation gaps\n- Missing regression test for negative values."
                        )
                    )
                ]
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    result = workbench.execute_workbench(
        "review",
        "Review the current workspace changes",
        client=fake_client,
        model="gemini-2.5-flash",
        memory=ShortTermMemory(max_turns=4),
        system_prompt="You are Lumi.",
        base_dir=tmp_path,
    )

    assert result.summary.startswith("High:")
    assert "src/app.py:7" in result.execution_log


def test_execute_workbench_build_retries_failed_checks_once(tmp_path, monkeypatch):
    _seed_workspace(tmp_path, monkeypatch)

    check_calls = {"count": 0}

    def fake_checks(_base_dir, _intelligence, progress_cb=None):
        check_calls["count"] += 1
        if progress_cb is not None:
            progress_cb("running tests: pytest -q")
        if check_calls["count"] == 1:
            return "tests: rc=1 · failing assertion", ("tests",)
        return "tests: rc=0 · ok", ()

    calls: list[str] = []

    def fake_run_agent(task, client, model, memory, system_prompt, yolo, review_only, *, base_dir=None):
        calls.append(task)
        return "Build applied" if len(calls) == 1 else "Repair applied"

    monkeypatch.setattr(workbench, "_run_detected_checks", fake_checks)

    result = workbench.execute_workbench(
        "build",
        "Implement calculator addition",
        client=object(),
        model="gemini-2.5-flash",
        memory=ShortTermMemory(max_turns=4),
        system_prompt="You are Lumi.",
        base_dir=tmp_path,
        run_agent_fn=fake_run_agent,
    )

    assert len(calls) == 2
    assert "Repair the failing verification checks from the build run." in calls[1]
    assert check_calls["count"] == 2
    assert result.failed_checks == ()
    assert "tests: rc=1" in result.execution_log
    assert "tests: rc=0" in result.execution_log


def test_execute_workbench_fixci_runs_workflow_commands_and_verifies_again(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(workbench, "WORKBENCH_STATE_DIR", tmp_path / ".wb-state")
    monkeypatch.setattr(workbench, "WORKBENCH_CACHE_DIR", tmp_path / ".wb-cache")
    monkeypatch.setattr(workbench, "PROJECT_MEMORY_PATH", tmp_path / ".wb-state" / "project_memory.json")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "jobs:\n  test:\n    steps:\n      - run: python -m pytest -q test_calc.py\n",
        encoding="utf-8",
    )
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    calls: list[str] = []

    def fake_run_agent(task, client, model, memory, system_prompt, yolo, review_only, *, base_dir=None):
        calls.append(task)
        (base_dir / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return "CI repair applied"

    result = workbench.execute_workbench(
        "fixci",
        "repair failing CI",
        client=object(),
        model="gemini-2.5-flash",
        memory=ShortTermMemory(max_turns=4),
        system_prompt="You are Lumi.",
        base_dir=tmp_path,
        run_agent_fn=fake_run_agent,
    )

    assert calls
    assert "Current failing checks:" in calls[0]
    assert result.failed_checks == ()
    assert "tests: rc=1" in result.execution_log
    assert "tests: rc=0" in result.execution_log
