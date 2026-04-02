"""Tests for Lumi - rebirth capability helpers."""

from __future__ import annotations

from src.utils import rebirth


def test_collect_rebirth_capabilities_has_expected_keys():
    capabilities = rebirth.collect_rebirth_capabilities()

    assert capabilities
    keys = {cap.key for cap in capabilities}
    assert {"agent", "council", "vessel", "benchmark", "media"} <= keys


def test_rebirth_readiness_shape():
    ready, total, ratio = rebirth.rebirth_readiness()

    assert total >= 10
    assert 0 <= ready <= total
    assert 0.0 <= ratio <= 1.0


def test_render_rebirth_report_contains_matrix_and_quickstart():
    report = rebirth.render_rebirth_report()

    assert "capability matrix" in report.lower()
    assert "Readiness:" in report
    assert "Quickstart" in report
