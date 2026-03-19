"""Tests for agent benchmark helpers."""

from __future__ import annotations

from src.agents.benchmark import BenchmarkScenario, run_benchmark_suite


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
