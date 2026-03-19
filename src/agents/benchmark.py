"""Small benchmark harness for Lumi agent tasks."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SCENARIO_PATH = Path(__file__).with_name("benchmark_scenarios.json")


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    task: str
    category: str = "core"
    expected_files: tuple[str, ...] = ()
    expected_absent_files: tuple[str, ...] = ()
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
        category="filesystem",
        expected_files=("api/main.py",),
        expected_substrings=("completed",),
    ),
    BenchmarkScenario(
        name="scaffold-docs",
        task="create a folder named docs and add a file named README.md inside that folder",
        category="filesystem",
        expected_files=("docs/README.md",),
        expected_substrings=("completed",),
    ),
    BenchmarkScenario(
        name="rename-file",
        task="rename app.py to main.py",
        category="filesystem",
        expected_files=("main.py",),
        expected_substrings=("completed",),
    ),
    BenchmarkScenario(
        name="delete-folder",
        task="delete the folder docs",
        category="filesystem",
        expected_absent_files=("docs",),
        expected_substrings=("completed",),
    ),
    BenchmarkScenario(
        name="patch-bug",
        task="fix the failing calculation and run verification",
        category="agent",
        expected_substrings=("completed", "passed"),
    ),
]


def load_benchmark_scenarios(path: Path | None = None) -> list[BenchmarkScenario]:
    scenario_path = path or DEFAULT_SCENARIO_PATH
    if not scenario_path.exists():
        return DEFAULT_BENCHMARK_SCENARIOS[:]
    try:
        data = json.loads(scenario_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_BENCHMARK_SCENARIOS[:]
    if not isinstance(data, list):
        return DEFAULT_BENCHMARK_SCENARIOS[:]

    loaded: list[BenchmarkScenario] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        task = str(item.get("task", "")).strip()
        if not name or not task:
            continue
        loaded.append(
            BenchmarkScenario(
                name=name,
                task=task,
                category=str(item.get("category", "core")).strip() or "core",
                expected_files=tuple(str(path) for path in item.get("expected_files", []) if isinstance(path, str)),
                expected_absent_files=tuple(str(path) for path in item.get("expected_absent_files", []) if isinstance(path, str)),
                expected_substrings=tuple(str(text) for text in item.get("expected_substrings", []) if isinstance(text, str)),
            )
        )
    return loaded or DEFAULT_BENCHMARK_SCENARIOS[:]


def render_benchmark_catalog(scenarios: list[BenchmarkScenario]) -> str:
    lines = ["Benchmark scenarios"]
    for scenario in scenarios:
        lines.append(f"  {scenario.name} [{scenario.category}]")
        lines.append(f"    {scenario.task}")
    return "\n".join(lines)


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
    for rel_path in scenario.expected_absent_files:
        if not (workspace / rel_path).exists():
            score += 0.2 / max(1, len(scenario.expected_absent_files))
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


def render_benchmark_summary(summary: BenchmarkSuiteSummary) -> str:
    return (
        "Benchmark summary\n"
        f"  Total:        {summary.total}\n"
        f"  Passed:       {summary.passed}\n"
        f"  Avg score:    {summary.average_score:.2f}\n"
        f"  Verification: {summary.verification_pass_rate:.0%}\n"
        f"  Recovery:     {summary.recovery_rate:.0%}\n"
        f"  Rollback:     {summary.rollback_rate:.0%}"
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
