from __future__ import annotations

from src.chat.inference_controls import (
    apply_reasoning_effort,
    display_reasoning_effort,
    display_reasoning_indicator,
    normalize_reasoning_effort,
    tune_inference_request,
)


def test_normalize_reasoning_effort_accepts_aliases():
    assert normalize_reasoning_effort("low") == "low"
    assert normalize_reasoning_effort("extra high") == "ehigh"
    assert normalize_reasoning_effort("xhigh") == "ehigh"
    assert normalize_reasoning_effort("max") == "ehigh"
    assert normalize_reasoning_effort("maximum") == "ehigh"
    assert normalize_reasoning_effort("unknown") == "medium"


def test_display_reasoning_effort_uses_max_for_ehigh_in_short_mode():
    assert display_reasoning_effort("ehigh") == "extra high"
    assert display_reasoning_effort("ehigh", short=True) == "max"
    assert display_reasoning_effort("medium", short=True) == "medium"


def test_display_reasoning_indicator_maps_levels_to_circles():
    assert display_reasoning_indicator("low") == "○"
    assert display_reasoning_indicator("medium") == "◐"
    assert display_reasoning_indicator("high") == "◕"
    assert display_reasoning_indicator("ehigh") == "◉"


def test_apply_reasoning_effort_injects_hidden_system_hint():
    messages = [
        {"role": "system", "content": "You are Lumi."},
        {"role": "user", "content": "fix this"},
    ]

    adjusted = apply_reasoning_effort(messages, "high")

    assert adjusted[0]["role"] == "system"
    assert "You are Lumi." in str(adjusted[0]["content"])
    assert "Reasoning effort: high." in str(adjusted[0]["content"])
    assert adjusted[1]["content"] == "fix this"


def test_tune_inference_request_changes_request_profile():
    low_tokens, low_temp = tune_inference_request(1000, 0.7, "low")
    medium_tokens, medium_temp = tune_inference_request(1000, 0.7, "medium")
    ehigh_tokens, ehigh_temp = tune_inference_request(1000, 0.7, "ehigh")

    assert (low_tokens, medium_tokens, ehigh_tokens) == (2048, 4096, 16384)
    assert low_temp > medium_temp > ehigh_temp
