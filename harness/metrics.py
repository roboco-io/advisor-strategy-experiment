"""run별 계측 수집·비용 환산·JSON 기록."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from harness import models


def _get(usage, key, default=0):
    if isinstance(usage, dict):
        return usage.get(key, default) or default
    return getattr(usage, key, default) or default


@dataclass
class RunMetrics:
    arm: str
    total_cost: float = 0.0
    by_model: dict = field(default_factory=dict)
    advisor_calls: int = 0
    worker_turns: int = 0
    refusals: list = field(default_factory=list)
    wall_clock_s: float = 0.0
    grade: dict | None = None

    def add_usage(self, model: str, usage) -> None:
        i = _get(usage, "input_tokens")
        o = _get(usage, "output_tokens")
        cr = _get(usage, "cache_read_input_tokens")
        cw = _get(usage, "cache_creation_input_tokens")
        self.total_cost += models.cost_of(model, i, o, cr, cw)
        b = self.by_model.setdefault(
            model, {"input_tokens": 0, "output_tokens": 0, "cache_read": 0, "cache_write": 0, "calls": 0}
        )
        b["input_tokens"] += i
        b["output_tokens"] += o
        b["cache_read"] += cr
        b["cache_write"] += cw
        b["calls"] += 1

    def note_advisor_call(self) -> None:
        self.advisor_calls += 1

    def note_turn(self) -> None:
        self.worker_turns += 1

    def note_refusal(self, category) -> None:
        self.refusals.append(category)

    def to_dict(self) -> dict:
        return {
            "arm": self.arm,
            "total_cost": round(self.total_cost, 6),
            "by_model": self.by_model,
            "advisor_calls": self.advisor_calls,
            "worker_turns": self.worker_turns,
            "refusals": self.refusals,
            "wall_clock_s": round(self.wall_clock_s, 2),
            "grade": self.grade,
        }

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
