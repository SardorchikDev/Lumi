"""Benchmark helpers for Lumi agent tasks."""

from __future__ import annotations

import inspect
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
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
    expected_file_contents: tuple[tuple[str, str], ...] = ()
    setup_files: tuple[tuple[str, str], ...] = ()
    verification_commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkRunOutcome:
    summary: str
    verification_ok: bool | None = None
    recovery_used: bool = False
    rollback_used: bool = False


@dataclass(frozen=True)
class BenchmarkResult:
    scenario: str
    success: bool
    summary: str
    score: float
    verification_ok: bool
    recovery_used: bool
    rollback_used: bool
    changed_files: tuple[str, ...] = ()
    verification_details: tuple[str, ...] = ()


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
        setup_files=(("README.md", "# temp\n"),),
    ),
    BenchmarkScenario(
        name="scaffold-docs",
        task="create a folder named docs and add a file named README.md inside that folder",
        category="filesystem",
        expected_files=("docs/README.md",),
    ),
    BenchmarkScenario(
        name="rename-file",
        task="rename app.py to main.py",
        category="filesystem",
        expected_files=("main.py",),
        expected_absent_files=("app.py",),
        setup_files=(("app.py", "print('hi')\n"),),
    ),
    BenchmarkScenario(
        name="delete-folder",
        task="delete the folder docs",
        category="filesystem",
        expected_absent_files=("docs",),
        setup_files=(("docs/README.md", "# docs\n"),),
    ),
    BenchmarkScenario(
        name="patch-bug",
        task="fix the failing calculation and run verification",
        category="agent",
        expected_file_contents=(("calc.py", "return a + b"),),
        verification_commands=("python -m pytest -q",),
        setup_files=(
            ("calc.py", "def add(a, b):\n    return a - b\n"),
            (
                "test_calc.py",
                "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            ),
        ),
    ),
]


def _dict_items_tuple(value) -> tuple[tuple[str, str], ...]:
    if isinstance(value, dict):
        return tuple(
            (str(path), str(content))
            for path, content in sorted(value.items())
            if isinstance(path, str)
        )
    return ()


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
                expected_files=tuple(
                    str(path)
                    for path in item.get("expected_files", [])
                    if isinstance(path, str)
                ),
                expected_absent_files=tuple(
                    str(path)
                    for path in item.get("expected_absent_files", [])
                    if isinstance(path, str)
                ),
                expected_substrings=tuple(
                    str(text)
                    for text in item.get("expected_substrings", [])
                    if isinstance(text, str)
                ),
                expected_file_contents=_dict_items_tuple(item.get("expected_file_contents")),
                setup_files=_dict_items_tuple(item.get("setup_files")),
                verification_commands=tuple(
                    str(command)
                    for command in item.get("verification_commands", [])
                    if isinstance(command, str)
                ),
            )
        )
    return loaded or DEFAULT_BENCHMARK_SCENARIOS[:]


def render_benchmark_catalog(scenarios: list[BenchmarkScenario]) -> str:
    counts: dict[str, int] = {}
    for scenario in scenarios:
        counts[scenario.category] = counts.get(scenario.category, 0) + 1
    lines = ["Benchmark scenarios"]
    if scenarios:
        lines.append(f"  Total: {len(scenarios)}")
        lines.append(
            "  Categories: "
            + ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
        )
    for scenario in scenarios:
        lines.append(f"  {scenario.name} [{scenario.category}]")
        lines.append(f"    {scenario.task}")
        if scenario.verification_commands:
            lines.append(f"    verify: {', '.join(scenario.verification_commands)}")
    return "\n".join(lines)


def _copy_workspace(template: Path, destination: Path) -> None:
    if not template.exists():
        return
    for item in template.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _apply_setup_files(workspace: Path, scenario: BenchmarkScenario) -> None:
    for relative, content in scenario.setup_files:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _snapshot_workspace(workspace: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    if not workspace.exists():
        return snapshot
    for path in workspace.rglob("*"):
        if path.is_dir():
            continue
        rel = str(path.relative_to(workspace))
        try:
            snapshot[rel] = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            snapshot[rel] = "<binary>"
    return snapshot


def _changed_files(before: dict[str, str], after: dict[str, str]) -> tuple[str, ...]:
    paths = set(before) | set(after)
    changed = [path for path in sorted(paths) if before.get(path) != after.get(path)]
    return tuple(changed)


def _invoke_runner(runner: Callable, task: str, workspace: Path):
    signature = inspect.signature(runner)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    has_varargs = any(
        parameter.kind == parameter.VAR_POSITIONAL
        for parameter in signature.parameters.values()
    )
    if has_varargs or len(positional) >= 2:
        return runner(task, workspace)
    return runner(task)


def _normalize_outcome(raw) -> BenchmarkRunOutcome:
    if isinstance(raw, BenchmarkRunOutcome):
        return raw
    if isinstance(raw, dict):
        return BenchmarkRunOutcome(
            summary=str(raw.get("summary", "")),
            verification_ok=raw.get("verification_ok"),
            recovery_used=bool(raw.get("recovery_used", False)),
            rollback_used=bool(raw.get("rollback_used", False)),
        )
    return BenchmarkRunOutcome(summary=str(raw))


def _run_verification_commands(
    workspace: Path,
    commands: tuple[str, ...],
) -> tuple[bool | None, tuple[str, ...]]:
    if not commands:
        return None, ()
    details: list[str] = []
    ok = True
    for command in commands:
        if command.startswith("python3 "):
            command = f"{shlex.quote(sys.executable)} {command[len('python3 '):]}"
        elif command.startswith("python "):
            command = f"{shlex.quote(sys.executable)} {command[len('python '):]}"
        proc = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        combined = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
        snippet = combined[:240] if combined else "(no output)"
        details.append(f"$ {command} -> {proc.returncode}: {snippet}")
        if proc.returncode != 0:
            ok = False
    return ok, tuple(details)


def _verification_ok(summary: str) -> bool:
    lowered = summary.lower()
    if "failed" in lowered and "0 failed" not in lowered:
        return False
    return "passed" in lowered or "completed" in lowered


def _check_expected_file_contents(
    workspace: Path,
    expected_file_contents: tuple[tuple[str, str], ...],
) -> list[bool]:
    results: list[bool] = []
    for relative, expected in expected_file_contents:
        path = workspace / relative
        if not path.exists() or not path.is_file():
            results.append(False)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        results.append(expected in text)
    return results


def score_benchmark(
    summary: str,
    workspace: Path,
    scenario: BenchmarkScenario,
    *,
    changed_files: tuple[str, ...] = (),
    verification_ok: bool | None = None,
) -> float:
    weighted_checks: list[tuple[bool, float]] = []
    for rel_path in scenario.expected_files:
        weighted_checks.append(((workspace / rel_path).exists(), 1.0))
    for rel_path in scenario.expected_absent_files:
        weighted_checks.append((not (workspace / rel_path).exists(), 1.0))
    for passed in _check_expected_file_contents(workspace, scenario.expected_file_contents):
        weighted_checks.append((passed, 1.0))
    if (
        scenario.expected_files
        or scenario.expected_absent_files
        or scenario.expected_file_contents
        or scenario.setup_files
    ):
        weighted_checks.append((bool(changed_files), 0.5))
    if scenario.verification_commands or verification_ok is not None:
        weighted_checks.append((bool(verification_ok), 1.0))
    lowered = summary.lower()
    for needle in scenario.expected_substrings:
        weighted_checks.append((needle.lower() in lowered, 0.25))

    if not weighted_checks:
        return 1.0 if summary.strip() else 0.0
    total_weight = sum(weight for _passed, weight in weighted_checks)
    passed_weight = sum(weight for passed, weight in weighted_checks if passed)
    return min(passed_weight / total_weight, 1.0)


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


def render_benchmark_results(results: list[BenchmarkResult]) -> str:
    lines = ["Benchmark results"]
    if not results:
        lines.append("  no results")
        return "\n".join(lines)
    for result in results:
        status = "pass" if result.success else "fail"
        lines.append(
            f"  {result.scenario}: {status} · score {result.score:.2f} · "
            f"verify={'yes' if result.verification_ok else 'no'} · "
            f"changes={len(result.changed_files)} · "
            f"recovery={'yes' if result.recovery_used else 'no'}"
        )
    return "\n".join(lines)


def run_benchmark_suite(
    scenarios: list[BenchmarkScenario],
    *,
    runner: Callable,
    workspace: Path,
) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    template_workspace = workspace.resolve()
    for scenario in scenarios:
        with tempfile.TemporaryDirectory(prefix=f"lumi-bench-{scenario.name}-") as tmpdir:
            scenario_workspace = Path(tmpdir)
            _copy_workspace(template_workspace, scenario_workspace)
            _apply_setup_files(scenario_workspace, scenario)
            before = _snapshot_workspace(scenario_workspace)
            raw_outcome = _invoke_runner(runner, scenario.task, scenario_workspace)
            outcome = _normalize_outcome(raw_outcome)
            after = _snapshot_workspace(scenario_workspace)
            changed_files = _changed_files(before, after)
            command_verification_ok, verification_details = _run_verification_commands(
                scenario_workspace,
                scenario.verification_commands,
            )
            if command_verification_ok is None:
                if outcome.verification_ok is None:
                    verification_ok = _verification_ok(outcome.summary)
                else:
                    verification_ok = bool(outcome.verification_ok)
            else:
                verification_ok = command_verification_ok
            score = score_benchmark(
                outcome.summary,
                scenario_workspace,
                scenario,
                changed_files=changed_files,
                verification_ok=verification_ok,
            )
            results.append(
                BenchmarkResult(
                    scenario=scenario.name,
                    success=score >= 0.6,
                    summary=outcome.summary,
                    score=score,
                    verification_ok=verification_ok,
                    recovery_used=outcome.recovery_used or "recovery used" in outcome.summary.lower(),
                    rollback_used=outcome.rollback_used or "rolled back" in outcome.summary.lower(),
                    changed_files=changed_files,
                    verification_details=verification_details,
                )
            )
    return results
