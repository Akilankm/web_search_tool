from __future__ import annotations

from dataclasses import dataclass

from src.serp_hybrid_url_finder.constants import CALL_TYPE_AI_MODE, CALL_TYPE_ORGANIC
from src.serp_hybrid_url_finder.models import BudgetState


class BudgetExceededError(RuntimeError):
    """Raised when per-product external call budget is exceeded."""


@dataclass
class BudgetTracker:
    max_organic: int = 2
    max_ai_mode: int = 2
    organic_used: int = 0
    ai_mode_used: int = 0

    def consume(self, call_type: str) -> None:
        if call_type == CALL_TYPE_ORGANIC:
            if self.organic_used >= self.max_organic:
                raise BudgetExceededError("Organic search budget exceeded")
            self.organic_used += 1
            return

        if call_type == CALL_TYPE_AI_MODE:
            if self.ai_mode_used >= self.max_ai_mode:
                raise BudgetExceededError("AI Mode budget exceeded")
            self.ai_mode_used += 1
            return

        raise ValueError(f"Unknown call_type: {call_type}")

    def can_use_ai_mode(self) -> bool:
        return self.ai_mode_used < self.max_ai_mode

    def can_use_organic(self) -> bool:
        return self.organic_used < self.max_organic

    def state(self) -> BudgetState:
        return BudgetState(
            organic_used=self.organic_used,
            ai_mode_used=self.ai_mode_used,
            max_organic=self.max_organic,
            max_ai_mode=self.max_ai_mode,
        )
