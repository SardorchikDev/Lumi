"""Reasoning-effort controls for Lumi inference calls."""

from __future__ import annotations

from dataclasses import dataclass

EFFORT_LEVELS = ("low", "medium", "high", "ehigh")
EFFORT_ALIASES = {
    "extra high": "ehigh",
    "extra-high": "ehigh",
    "extra_high": "ehigh",
    "xhigh": "ehigh",
    "very high": "ehigh",
    "very-high": "ehigh",
    "very_high": "ehigh",
}


@dataclass(frozen=True)
class EffortProfile:
    effort: str
    token_scale: float
    temperature_cap: float
    system_hint: str


EFFORT_PROFILES: dict[str, EffortProfile] = {
    "low": EffortProfile(
        effort="low",
        token_scale=0.7,
        temperature_cap=0.45,
        system_hint=(
            "Reasoning effort: low. Solve directly. Prefer the shortest correct path. "
            "Avoid exhaustive branch exploration unless the task is clearly ambiguous or risky."
        ),
    ),
    "medium": EffortProfile(
        effort="medium",
        token_scale=1.0,
        temperature_cap=0.7,
        system_hint="",
    ),
    "high": EffortProfile(
        effort="high",
        token_scale=1.25,
        temperature_cap=0.35,
        system_hint=(
            "Reasoning effort: high. Work carefully through assumptions, edge cases, and tradeoffs "
            "before answering. Prefer correctness over speed."
        ),
    ),
    "ehigh": EffortProfile(
        effort="ehigh",
        token_scale=1.5,
        temperature_cap=0.2,
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


def apply_reasoning_effort(messages: list[dict[str, object]], effort: str | None) -> list[dict[str, object]]:
    normalized = normalize_reasoning_effort(effort)
    profile = EFFORT_PROFILES[normalized]
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
    normalized = normalize_reasoning_effort(effort)
    profile = EFFORT_PROFILES[normalized]
    tuned_tokens = max(64, int(max_tokens * profile.token_scale))
    tuned_temperature = min(float(temperature), profile.temperature_cap)
    return tuned_tokens, max(0.0, tuned_temperature)
