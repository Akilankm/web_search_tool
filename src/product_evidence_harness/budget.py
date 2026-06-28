from __future__ import annotations

from dataclasses import dataclass

from src.product_evidence_harness.contracts import SearchBudgetSnapshot


class BudgetExceededError(RuntimeError):
    pass


@dataclass
class BudgetTracker:
    max_organic: int = 3
    max_ai_mode: int = 1
    max_scrapes: int = 180
    organic_used: int = 0
    ai_mode_used: int = 0
    scrape_used: int = 0

    def can_search_organic(self) -> bool:
        return self.organic_used < self.max_organic

    def can_search_ai(self) -> bool:
        return self.ai_mode_used < self.max_ai_mode

    def can_scrape(self) -> bool:
        return self.scrape_used < self.max_scrapes

    def consume_organic(self) -> None:
        if not self.can_search_organic():
            raise BudgetExceededError("organic search budget exceeded")
        self.organic_used += 1

    def consume_ai(self) -> None:
        if not self.can_search_ai():
            raise BudgetExceededError("AI Mode budget exceeded")
        self.ai_mode_used += 1

    def consume_scrape(self) -> None:
        if not self.can_scrape():
            raise BudgetExceededError("scrape budget exceeded")
        self.scrape_used += 1

    def exhausted(self) -> bool:
        return not (self.can_search_organic() or self.can_search_ai() or self.can_scrape())

    def snapshot(self) -> SearchBudgetSnapshot:
        return SearchBudgetSnapshot(
            organic_used=self.organic_used,
            ai_mode_used=self.ai_mode_used,
            scrape_used=self.scrape_used,
            max_organic=self.max_organic,
            max_ai_mode=self.max_ai_mode,
            max_scrapes=self.max_scrapes,
        )
