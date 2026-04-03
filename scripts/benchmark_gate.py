#!/usr/bin/env python3
"""Offline benchmark gate used by CI to catch benchmark regressions."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agents.benchmark import (  # noqa: E402
    BenchmarkRunOutcome,
    BenchmarkScenario,
    benchmark_payload,
    load_benchmark_scenarios,
    render_benchmark_markdown,
    render_benchmark_results,
    render_benchmark_summary,
    run_benchmark_suite,
    summarize_benchmark_results,
)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _contract_runner(task: str, workspace: Path) -> BenchmarkRunOutcome:
    lowered = task.lower().strip()

    if "folder named api" in lowered and "main.py" in lowered:
        (workspace / "api").mkdir(parents=True, exist_ok=True)
        (workspace / "api" / "main.py").write_text("", encoding="utf-8")
        return BenchmarkRunOutcome(summary="Agent completed scaffold-python contract")

    if "folder named docs" in lowered and "readme.md" in lowered:
        (workspace / "docs").mkdir(parents=True, exist_ok=True)
        (workspace / "docs" / "README.md").write_text("# docs\n", encoding="utf-8")
        return BenchmarkRunOutcome(summary="Agent completed scaffold-docs contract")

    if "rename app.py to main.py" in lowered:
        source = workspace / "app.py"
        target = workspace / "main.py"
        if source.exists():
            source.rename(target)
        return BenchmarkRunOutcome(summary="Agent completed rename-file contract")

    if "delete the folder docs" in lowered:
        _remove_path(workspace / "docs")
        return BenchmarkRunOutcome(summary="Agent completed delete-folder contract")

    if "fix the failing calculation" in lowered:
        (workspace / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        return BenchmarkRunOutcome(
            summary="Agent completed patch-bug contract",
            verification_ok=True,
            recovery_used=True,
        )

    return BenchmarkRunOutcome(summary=f"Unhandled contract task: {task}")


def _load_gate_config(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("benchmark gate config must be a JSON object")
    return raw


def _select_scenarios(all_scenarios: list[BenchmarkScenario], names: list[str]) -> list[BenchmarkScenario]:
    by_name = {scenario.name: scenario for scenario in all_scenarios}
    selected: list[BenchmarkScenario] = []
    for name in names:
        scenario = by_name.get(name)
        if scenario is None:
            raise ValueError(f"Configured scenario not found: {name}")
        selected.append(scenario)
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run offline Lumi benchmark gate")
    parser.add_argument("--config", default=str(ROOT / "configs" / "benchmark_gate.json"), help="Path to benchmark gate JSON config")
    parser.add_argument(
        "--workspace",
        default="",
        help="Workspace template path (defaults to an empty temporary workspace)",
    )
    parser.add_argument("--output-json", default="", help="Optional path to write machine-readable results")
    parser.add_argument("--output-markdown", default="", help="Optional path to write a Markdown benchmark report")
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    config = _load_gate_config(config_path)

    names = [str(name) for name in config.get("scenarios", []) if str(name).strip()]
    if not names:
        raise ValueError("benchmark gate config must declare at least one scenario")

    scenarios = _select_scenarios(load_benchmark_scenarios(), names)
    if args.workspace:
        workspace = Path(args.workspace).resolve()
        results = run_benchmark_suite(scenarios, runner=_contract_runner, workspace=workspace)
    else:
        with tempfile.TemporaryDirectory(prefix="lumi-bench-template-") as tmpdir:
            results = run_benchmark_suite(
                scenarios,
                runner=_contract_runner,
                workspace=Path(tmpdir),
            )
    summary = summarize_benchmark_results(results)

    print(render_benchmark_summary(summary))
    print()
    print(render_benchmark_results(results))

    failures: list[str] = []
    minimum = config.get("minimum", {}) if isinstance(config.get("minimum"), dict) else {}
    pass_rate = (summary.passed / summary.total) if summary.total else 0.0

    min_pass_rate = float(minimum.get("pass_rate", 0.0))
    min_avg_score = float(minimum.get("average_score", 0.0))
    min_verification_rate = float(minimum.get("verification_pass_rate", 0.0))

    if pass_rate < min_pass_rate:
        failures.append(f"pass_rate {pass_rate:.2f} < {min_pass_rate:.2f}")
    if summary.average_score < min_avg_score:
        failures.append(f"average_score {summary.average_score:.2f} < {min_avg_score:.2f}")
    if summary.verification_pass_rate < min_verification_rate:
        failures.append(
            f"verification_pass_rate {summary.verification_pass_rate:.2f} < {min_verification_rate:.2f}"
        )

    minimum_scenario_score = config.get("minimum_scenario_score", {})
    if isinstance(minimum_scenario_score, dict):
        by_name = {result.scenario: result for result in results}
        for name, threshold in minimum_scenario_score.items():
            threshold_float = float(threshold)
            scenario_result = by_name.get(str(name))
            if scenario_result is None:
                failures.append(f"minimum_scenario_score references unknown scenario: {name}")
                continue
            if scenario_result.score < threshold_float:
                failures.append(
                    f"scenario {name} score {scenario_result.score:.2f} < {threshold_float:.2f}"
                )

    payload = benchmark_payload(summary, results)
    payload["threshold_failures"] = failures

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    if args.output_markdown:
        output_path = Path(args.output_markdown).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_benchmark_markdown(summary, results), encoding="utf-8")

    if failures:
        print("\nBenchmark gate failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nBenchmark gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
