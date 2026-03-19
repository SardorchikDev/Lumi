"""Small benchmark harness for Lumi agent tasks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    task: str
    expected_files: tuple[str, ...] = ()
    expected_substrings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkResult:
    scenario: str
    success: bool
    summary: str
    score: float


def score_benchmark(summary: str, workspace: Path, scenario: BenchmarkScenario) -> float:
    score = 0.0
    lowered = summary.lower()
    if "agent completed" in lowered:
        score += 0.4
    if "failed" not in lowered:
        score += 0.2
    for rel_path in scenario.expected_files:
        if (workspace / rel_path).exists():
            score += 0.2 / max(1, len(scenario.expected_files))
    for needle in scenario.expected_substrings:
        if needle.lower() in lowered:
            score += 0.2 / max(1, len(scenario.expected_substrings))
    return min(score, 1.0)


def run_benchmark_suite(
    scenarios: list[BenchmarkScenario],
    *,
    runner: Callable[[str], str],
    workspace: Path,
) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    for scenario in scenarios:
        summary = runner(scenario.task)
        score = score_benchmark(summary, workspace, scenario)
        results.append(
            BenchmarkResult(
                scenario=scenario.name,
                success=score >= 0.6,
                summary=summary,
                score=score,
            )
        )
    return results
