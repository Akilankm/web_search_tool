from __future__ import annotations

import sys
from dataclasses import asdict, is_dataclass
from typing import Any

from loguru import logger
from rich.console import Console
from rich.table import Table


def configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(sys.stderr, level=level, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")


class RichPrinter:
    def __init__(self) -> None:
        self.console = Console()

    def print_dict(self, obj: dict[str, Any]) -> None:
        self.console.print(obj)

    def print_match(self, match: Any) -> None:
        data = match.to_dict() if hasattr(match, "to_dict") else asdict(match) if is_dataclass(match) else dict(match)
        table = Table(title="Product URL Match")
        table.add_column("Field")
        table.add_column("Value")
        for key, value in data.items():
            if key in {"specs", "image_urls"}:
                continue
            table.add_row(str(key), str(value)[:500])
        self.console.print(table)

    def print_scorecards(self, scorecards: list[Any], *, limit: int = 10) -> None:
        table = Table(title="Candidate Scorecards")
        for col in ["rank", "confidence", "status", "identity", "scrapable", "country", "url"]:
            table.add_column(col)
        for idx, card in enumerate(scorecards[:limit], start=1):
            table.add_row(
                str(idx),
                str(card.final_confidence),
                card.validation_status,
                card.verification.identity_status if card.verification else "UNVERIFIED",
                str(bool(card.scrape and card.scrape.is_scrapable)),
                card.country_check,
                card.candidate.url,
            )
        self.console.print(table)
