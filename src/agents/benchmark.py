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
    verification_ok: bool
    recovery_used: bool
    rollback_used: bool


@dataclass(frozen=True)
class BenchmarkSuiteSummary:
    total: int
    passed: int
    average_score: float
    verification_pass_rate: float
    recovery_rate: float
    rollback_rate: float


DEFAULT_BENCHMARK_SCENARIOS = [
    BenchmarkScenario(
        name="scaffold-python",
        task="create a folder named api and add a file named main.py inside that folder",
        expected_files=("api/main.py",),
        expected_substrings=("completed",),
    ),
    BenchmarkScenario(
        name="scaffold-docs",
        task="create a folder named docs and add a file named README.md inside that folder",
        expected_files=("docs/README.md",),
        expected_substrings=("completed",),
    ),
    BenchmarkScenario(
        name="rename-file",
        task="rename app.py to main.py",
        expected_files=("main.py",),
        expected_substrings=("completed",),
    ),
    BenchmarkScenario(
        name="delete-folder",
        task="delete the folder docs",
        expected_substrings=("completed",),
    ),
    BenchmarkScenario(
        name="patch-bug",
        task="fix the failing calculation and run verification",
        expected_substrings=("completed", "passed"),
    ),
]


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


def _verification_ok(summary: str) -> bool:
    lowered = summary.lower()
    if "failed" in lowered and "0 failed" not in lowered:
        return False
    return "passed" in lowered or "completed" in lowered


def summarize_benchmark_results(results: list[BenchmarkResult]) -> BenchmarkSuiteSummary:
    total = len(results)
    if not results:
        return BenchmarkSuiteSummary(
            total=0,
            passed=0,
            average_score=0.0,
            verification_pass_rate=0.0,
            recovery_rate=0.0,
            rollback_rate=0.0,
        )
    passed = sum(1 for result in results if result.success)
    verification_ok = sum(1 for result in results if result.verification_ok)
    recovery_used = sum(1 for result in results if result.recovery_used)
    rollback_used = sum(1 for result in results if result.rollback_used)
    return BenchmarkSuiteSummary(
        total=total,
        passed=passed,
        average_score=sum(result.score for result in results) / total,
        verification_pass_rate=verification_ok / total,
        recovery_rate=recovery_used / total,
        rollback_rate=rollback_used / total,
    )


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
                verification_ok=_verification_ok(summary),
                recovery_used="recovery used" in summary.lower(),
                rollback_used="rolled back" in summary.lower(),
            )
        )
    return results
