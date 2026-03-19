"""Tests for shared chat runtime helpers."""

from __future__ import annotations

from src.chat.optimizer import ContextCache, SessionTelemetry
from src.chat.runtime import build_runtime_messages, infer_message_mode


def test_infer_message_mode_supports_file_markers():
    history = [{"role": "user", "content": "cached for retrieval in src/app.py"}]
    mode = infer_message_mode(history, file_markers=("cached for retrieval",), include_coding_detector=True)
    assert mode == "files"


def test_build_runtime_messages_uses_resolved_model():
    cache = ContextCache()
    telemetry = SessionTelemetry()
    messages = build_runtime_messages(
        "You are Lumi.",
        [{"role": "user", "content": "review src/app.py"}],
        model="",
        get_provider_fn=lambda: "huggingface",
        get_models_fn=lambda _provider: ["meta-llama/Llama-3.3-70B-Instruct"],
        context_cache=cache,
        telemetry=telemetry,
    )

    assert messages[0]["role"] == "system"
    assert telemetry.last_budget is not None
    assert telemetry.last_budget.model == "meta-llama/Llama-3.3-70B-Instruct"
