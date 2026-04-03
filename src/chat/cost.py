"""Session cost tracking for Lumi."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
    "claude-haiku-3-5": (0.80, 4.0),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.0),
}
DEFAULT_PRICE: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class CostRecord:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float

    @property
    def total_cost(self) -> float:
        return self.input_cost + self.output_cost


@dataclass
class SessionCostTracker:
    _records: list[CostRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def _resolve_pricing(self, model: str) -> tuple[float, float]:
        lowered = str(model or "").strip().lower()
        for key, pricing in MODEL_PRICING.items():
            if key in lowered:
                return pricing
        return DEFAULT_PRICE

    def record(self, *, provider: str, model: str, input_tokens: int, output_tokens: int) -> CostRecord:
        input_rate, output_rate = self._resolve_pricing(model)
        input_cost = (max(0, int(input_tokens)) / 1_000_000.0) * input_rate
        output_cost = (max(0, int(output_tokens)) / 1_000_000.0) * output_rate
        record = CostRecord(
            provider=str(provider or "unknown"),
            model=str(model or "unknown"),
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            input_cost=input_cost,
            output_cost=output_cost,
        )
        with self._lock:
            self._records.append(record)
        return record

    def records(self) -> list[CostRecord]:
        with self._lock:
            return list(self._records)

    def total_cost(self) -> float:
        with self._lock:
            return sum(record.total_cost for record in self._records)

    def total_tokens(self) -> tuple[int, int]:
        with self._lock:
            input_tokens = sum(record.input_tokens for record in self._records)
            output_tokens = sum(record.output_tokens for record in self._records)
        return input_tokens, output_tokens

    def render_report(self) -> str:
        records = self.records()
        input_tokens, output_tokens = self.total_tokens()
        lines = [
            "Session cost",
            f"  Requests: {len(records)}",
            f"  Input:    ~{input_tokens:,} tk",
            f"  Output:   ~{output_tokens:,} tk",
            f"  Total:    ${self.total_cost():.4f}",
        ]
        if records:
            lines.append("")
            lines.append("By request")
            for record in records[-10:]:
                lines.append(
                    f"  - {record.provider} · {record.model} · in {record.input_tokens:,} tk · "
                    f"out {record.output_tokens:,} tk · ${record.total_cost:.4f}"
                )
        return "\n".join(lines)


def session_cost_status(tracker: SessionCostTracker) -> str:
    return f"${tracker.total_cost():.3f}"


__all__ = [
    "CostRecord",
    "MODEL_PRICING",
    "SessionCostTracker",
    "session_cost_status",
]
