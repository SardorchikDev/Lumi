"""Tests for Claude parity helpers."""

from __future__ import annotations

from src.utils.claude_parity import (
    claude_parity_summary,
    collect_command_parity,
    collect_mirror_workstreams,
    extract_lumi_command_tokens,
    render_claude_parity_report,
)


def test_extract_lumi_command_tokens_includes_known_commands():
    tokens = extract_lumi_command_tokens()

    assert "/model" in tokens
    assert "/doctor" in tokens
    assert "/review" in tokens


def test_claude_parity_summary_has_expected_shape():
    present, total, ratio = claude_parity_summary()

    assert total >= 90
    assert 0 <= present <= total
    assert 0.0 <= ratio <= 1.0


def test_collect_command_parity_includes_key_categories():
    categories = collect_command_parity()

    names = {item.name for item in categories}
    assert "Git & Version Control" in names
    assert "Tasks & Agents" in names
    assert "Diagnostics & Status" in names


def test_collect_mirror_workstreams_has_17_items():
    workstreams = collect_mirror_workstreams()

    assert len(workstreams) == 17
    assert workstreams[0].key == "permissions"
    assert workstreams[-1].key == "rewrite"


def test_render_claude_parity_report_contains_release_path():
    report = render_claude_parity_report()

    assert "Claude parity audit" in report
    assert "Operator workstreams" in report
    assert "v0.7.0: Operator" in report
    assert "v1.0.0: Native" in report
