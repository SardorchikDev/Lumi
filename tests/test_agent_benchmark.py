"""Tests for agent benchmark helpers."""

from __future__ import annotations

from src.agents.benchmark import (
    BenchmarkScenario,
    run_benchmark_suite,
    summarize_benchmark_results,
)


def test_run_benchmark_suite_scores_expected_outputs(tmp_path):
    (tmp_path / "notes.txt").write_text("done\n", encoding="utf-8")

    def runner(task: str) -> str:
        return f"Agent completed 1/1 steps for {task}"

    results = run_benchmark_suite(
        [
            BenchmarkScenario(
                name="notes",
                task="write notes",
                expected_files=("notes.txt",),
                expected_substrings=("completed",),
            )
        ],
        runner=runner,
        workspace=tmp_path,
    )

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].score >= 0.8
    assert results[0].verification_ok is True


def test_summarize_benchmark_results_tracks_quality_signals(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")

    def runner(task: str) -> str:
        return f"Agent completed 1/1 steps for {task}. Recovery used. Rolled back 0 change(s). 1 passed."

    results = run_benchmark_suite(
        [
            BenchmarkScenario(
                name="main",
                task="write main",
                expected_files=("main.py",),
                expected_substrings=("passed",),
            )
        ],
        runner=runner,
        workspace=tmp_path,
    )
    summary = summarize_benchmark_results(results)

    assert summary.total == 1
    assert summary.passed == 1
    assert summary.average_score > 0.7
    assert summary.verification_pass_rate == 1.0
    assert summary.recovery_rate == 1.0
    assert summary.rollback_rate == 1.0
