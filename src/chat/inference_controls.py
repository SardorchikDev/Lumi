"""Reasoning-effort controls for Lumi inference calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

EFFORT_LEVELS = ("low", "medium", "high", "ehigh")
EFFORT_ALIASES = {
    "extra high": "ehigh",
    "extra-high": "ehigh",
    "extra_high": "ehigh",
    "xhigh": "ehigh",
    "max": "ehigh",
    "maximum": "ehigh",
    "very high": "ehigh",
    "very-high": "ehigh",
    "very_high": "ehigh",
}


@dataclass(frozen=True)
class EffortProfile:
    effort: str
    temperature: float
    max_tokens: int
    thinking_enabled: bool
    thinking_budget: int | None
    system_hint: str


EFFORT_PROFILES: dict[str, EffortProfile] = {
    "low": EffortProfile(
        effort="low",
        temperature=1.0,
        max_tokens=2048,
        thinking_enabled=False,
        thinking_budget=None,
        system_hint=(
            "Reasoning effort: low. Solve directly. Prefer the shortest correct path. "
            "Avoid broad exploration unless the task is clearly ambiguous."
        ),
    ),
    "medium": EffortProfile(
        effort="medium",
        temperature=0.7,
        max_tokens=4096,
        thinking_enabled=False,
        thinking_budget=None,
        system_hint="",
    ),
    "high": EffortProfile(
        effort="high",
        temperature=0.3,
        max_tokens=8192,
        thinking_enabled=True,
        thinking_budget=5000,
        system_hint=(
            "Reasoning effort: high. Work carefully through assumptions, edge cases, and tradeoffs "
            "before answering. Prefer correctness over speed."
        ),
    ),
    "ehigh": EffortProfile(
        effort="ehigh",
        temperature=0.1,
        max_tokens=16384,
        thinking_enabled=True,
        thinking_budget=15000,
        system_hint=(
            "Reasoning effort: extra high. Use a deliberate multi-step internal plan, verify key assumptions, "
            "consider strong alternatives, and only then produce the final answer."
        ),
    ),
}


def normalize_reasoning_effort(value: str | None) -> str:
    lowered = (value or "").strip().lower()
    if not lowered:
        return "medium"
    normalized = EFFORT_ALIASES.get(lowered, lowered)
    return normalized if normalized in EFFORT_PROFILES else "medium"


def display_reasoning_effort(effort: str | None, *, short: bool = False) -> str:
    normalized = normalize_reasoning_effort(effort)
    if normalized == "ehigh":
        return "max" if short else "extra high"
    return normalized


def display_reasoning_indicator(effort: str | None) -> str:
    normalized = normalize_reasoning_effort(effort)
    return {
        "low": "○",
        "medium": "◐",
        "high": "◕",
        "ehigh": "◉",
    }.get(normalized, "◐")


def get_effort_profile(effort: str | None) -> EffortProfile:
    return EFFORT_PROFILES[normalize_reasoning_effort(effort)]


def apply_reasoning_effort(messages: list[dict[str, object]], effort: str | None) -> list[dict[str, object]]:
    profile = get_effort_profile(effort)
    if not profile.system_hint:
        return [dict(message) for message in messages]

    adjusted = [dict(message) for message in messages]
    for message in adjusted:
        if str(message.get("role", "")).strip() == "system":
            original = str(message.get("content", "")).rstrip()
            message["content"] = f"{original}\n\n{profile.system_hint}" if original else profile.system_hint
            return adjusted
    return [{"role": "system", "content": profile.system_hint}, *adjusted]


def tune_inference_request(max_tokens: int, temperature: float, effort: str | None) -> tuple[int, float]:
    profile = get_effort_profile(effort)
    _ = max_tokens, temperature
    return profile.max_tokens, profile.temperature


def provider_effort_options(
    provider: str,
    effort: str | None,
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    profile = get_effort_profile(effort)
    payload: dict[str, Any] = {
        "max_tokens": min(profile.max_tokens, max_tokens) if max_tokens is not None else profile.max_tokens,
        "temperature": profile.temperature,
    }
    lowered_provider = str(provider or "").strip().lower()
    if lowered_provider == "claude" and profile.thinking_enabled:
        payload["thinking"] = {"type": "enabled", "budget_tokens": profile.thinking_budget}
    elif lowered_provider == "gemini" and profile.thinking_enabled:
        payload["thinking_config"] = {"mode": "enabled", "budget_tokens": profile.thinking_budget}
    return payload
