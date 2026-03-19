"""Tests for agent benchmark helpers."""

from __future__ import annotations

from src.agents.benchmark import (
    BenchmarkRunOutcome,
    BenchmarkScenario,
    load_benchmark_scenarios,
    render_benchmark_catalog,
    render_benchmark_results,
    render_benchmark_summary,
    run_benchmark_suite,
    summarize_benchmark_results,
)


def test_run_benchmark_suite_scores_real_workspace_outputs(tmp_path):
    def runner(task: str, workspace):
        (workspace / "notes.txt").write_text("done\n", encoding="utf-8")
        return BenchmarkRunOutcome(summary=f"Agent completed 1/1 steps for {task}")

    results = run_benchmark_suite(
        [
            BenchmarkScenario(
                name="notes",
                task="write notes",
                expected_files=("notes.txt",),
            )
        ],
        runner=runner,
        workspace=tmp_path,
    )

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].score >= 0.6
    assert "notes.txt" in results[0].changed_files


def test_benchmark_suite_runs_verification_commands_in_temp_workspace(tmp_path):
    def runner(task: str, workspace):
        (workspace / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (workspace / "test_calc.py").write_text(
            "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            encoding="utf-8",
        )
        return {"summary": f"patched bug for {task}", "recovery_used": True}

    results = run_benchmark_suite(
        [
            BenchmarkScenario(
                name="patch-bug",
                task="fix add",
                expected_file_contents=(("calc.py", "return a + b"),),
                verification_commands=("python -m pytest -q",),
            )
        ],
        runner=runner,
        workspace=tmp_path,
    )

    assert results[0].verification_ok is True
    assert results[0].verification_details
    assert results[0].recovery_used is True
    assert results[0].score >= 0.8


def test_summarize_benchmark_results_tracks_quality_signals(tmp_path):
    def runner(task: str, workspace):
        (workspace / "main.py").write_text("print('hi')\n", encoding="utf-8")
        return BenchmarkRunOutcome(
            summary=f"Agent completed 1/1 steps for {task}",
            verification_ok=True,
            recovery_used=True,
            rollback_used=True,
        )

    results = run_benchmark_suite(
        [
            BenchmarkScenario(
                name="main",
                task="write main",
                expected_files=("main.py",),
            )
        ],
        runner=runner,
        workspace=tmp_path,
    )
    summary = summarize_benchmark_results(results)

    assert summary.total == 1
    assert summary.passed == 1
    assert summary.average_score >= 0.6
    assert summary.verification_pass_rate == 1.0
    assert summary.recovery_rate == 1.0
    assert summary.rollback_rate == 1.0


def test_load_benchmark_scenarios_reads_json_catalog(tmp_path):
    path = tmp_path / "benchmarks.json"
    path.write_text(
        """
        [
          {
            "name": "delete-docs",
            "task": "delete the folder docs",
            "category": "filesystem",
            "expected_absent_files": ["docs"],
            "setup_files": {"docs/README.md": "# docs\\n"},
            "verification_commands": ["python -c \\"print('ok')\\""]
          }
        ]
        """,
        encoding="utf-8",
    )
    scenarios = load_benchmark_scenarios(path)
    assert len(scenarios) == 1
    assert scenarios[0].category == "filesystem"
    assert scenarios[0].expected_absent_files == ("docs",)
    assert scenarios[0].verification_commands == ("python -c \"print('ok')\"",)


def test_render_benchmark_outputs_are_scanable(tmp_path):
    def runner(task: str, workspace):
        (workspace / "docs").mkdir()
        return BenchmarkRunOutcome(summary=f"Agent completed 1/1 steps for {task}")

    results = run_benchmark_suite(
        [
            BenchmarkScenario(
                name="create-folder",
                task="create docs",
                category="filesystem",
                setup_files=(),
            )
        ],
        runner=runner,
        workspace=tmp_path,
    )
    catalog = render_benchmark_catalog(
        [BenchmarkScenario(name="create-folder", task="create docs", category="filesystem")]
    )
    summary = render_benchmark_summary(summarize_benchmark_results(results))
    details = render_benchmark_results(results)
    assert "create-folder" in catalog
    assert "Total: 1" in catalog
    assert "Benchmark summary" in summary
    assert "changes=" in details
