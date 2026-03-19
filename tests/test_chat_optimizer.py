"""Tests for the shared chat optimizer layer."""

from __future__ import annotations

from src.chat.optimizer import (
    ContextCache,
    SessionTelemetry,
    optimize_messages,
    route_model,
)


def test_optimize_messages_adds_summary_and_retrieval():
    cache = ContextCache()
    telemetry = SessionTelemetry()
    cache.remember_file(
        "src/app.py",
        "def render_page():\n    return 'hello'\n\nclass App:\n    pass\n",
    )
    messages = [
        {"role": "system", "content": "You are Lumi."},
        {"role": "user", "content": "We discussed architecture yesterday."},
        {"role": "assistant", "content": "Use a thin view layer and keep logic separate."},
        {"role": "user", "content": "Please review render_page in src/app.py and explain the bug."},
    ]

    optimized = optimize_messages(
        messages,
        "meta-llama/Llama-3.3-70B-Instruct",
        mode="review",
        context_cache=cache,
        telemetry=telemetry,
    )

    system_blocks = [msg["content"] for msg in optimized if msg["role"] == "system"]
    assert any("Relevant cached context" in block for block in system_blocks)
    assert any("src/app.py" in block for block in system_blocks)
    assert any("Reply shape" in block for block in system_blocks)
    assert telemetry.last_budget is not None
    assert telemetry.last_budget.retrieved_documents >= 1


def test_optimize_messages_summarizes_when_budget_is_small():
    cache = ContextCache()
    telemetry = SessionTelemetry()
    messages = [{"role": "system", "content": "You are Lumi."}]
    payload = " ".join(["src/app.py next step follow up decision architecture review unresolved tests failing"] * 120)
    for idx in range(44):
        messages.append({"role": "user", "content": f"user turn {idx} {payload}"})
        messages.append({"role": "assistant", "content": f"assistant turn {idx} {payload}"})

    optimized = optimize_messages(
        messages,
        "unknown-model",
        mode="chat",
        context_cache=cache,
        telemetry=telemetry,
    )

    assert any(msg["role"] == "system" and "Conversation summary" in msg["content"] for msg in optimized)
    assert telemetry.last_budget is not None
    assert telemetry.last_budget.dropped_messages > 0


def test_route_model_prefers_helper_model_for_summary():
    models = ["gemini-2.5-pro", "gemini-2.5-flash-lite", "gemini-2.0-flash"]
    assert route_model("gemini-2.5-pro", models, "summary") == "gemini-2.5-flash-lite"


def test_route_model_prefers_heavier_model_for_code():
    models = ["gemini-2.5-flash-lite", "gemini-2.5-pro"]
    assert route_model("gemini-2.5-flash-lite", models, "code") == "gemini-2.5-pro"


def test_telemetry_records_response_tokens():
    cache = ContextCache()
    telemetry = SessionTelemetry()
    optimize_messages(
        [{"role": "system", "content": "You are Lumi."}, {"role": "user", "content": "say hi"}],
        "meta-llama/Llama-3.3-70B-Instruct",
        context_cache=cache,
        telemetry=telemetry,
    )
    telemetry.record_response("hello there")
    assert "Input:" in telemetry.render_usage_report()
    assert "Prompt:" in telemetry.render_context_report()


def test_optimize_messages_keeps_relevant_older_history():
    cache = ContextCache()
    telemetry = SessionTelemetry()
    filler = " ".join(["noise"] * 250)
    messages = [{"role": "system", "content": "You are Lumi."}]
    messages.append({"role": "user", "content": "The bug is in src/api.py auth flow"})
    messages.append({"role": "assistant", "content": "Focus on src/api.py and the login bug."})
    for idx in range(24):
        messages.append({"role": "user", "content": f"turn {idx} {filler}"})
        messages.append({"role": "assistant", "content": f"reply {idx} {filler}"})
    messages.append({"role": "user", "content": "Review src/api.py again and explain the auth bug."})

    optimized = optimize_messages(
        messages,
        "unknown-model",
        mode="review",
        context_cache=cache,
        telemetry=telemetry,
    )

    assert any("src/api.py" in msg["content"] for msg in optimized if msg["role"] != "system")
