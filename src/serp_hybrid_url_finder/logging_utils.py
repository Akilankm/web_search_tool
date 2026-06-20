from __future__ import annotations

import sys
from typing import Any, Iterable, Mapping, Optional

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from serp_hybrid_url_finder.constants import (
    DEFAULT_LOG_LEVEL,
    LOGURU_FORMAT,
    RICH_BUDGET_PANEL_TITLE,
    RICH_CANDIDATES_TABLE_TITLE,
    RICH_MATCH_PANEL_TITLE,
    RICH_PANEL_BORDER_STYLE,
    RICH_PAYLOAD_PANEL_TITLE,
    RICH_TABLE_HEADER_STYLE,
)


class RichPrinter:
    """Rich notebook/terminal printer for pipeline outputs."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()

    def print_match(self, match: Any, title: str = RICH_MATCH_PANEL_TITLE) -> None:
        table = Table(show_header=True, header_style=RICH_TABLE_HEADER_STYLE)
        table.add_column("Field")
        table.add_column("Value", overflow="fold")

        values = match.to_dict() if hasattr(match, "to_dict") else dict(match)
        for key, value in values.items():
            table.add_row(str(key), "" if value is None else str(value))

        self.console.print(
            Panel(table, title=title, border_style=RICH_PANEL_BORDER_STYLE)
        )

    def print_budget(self, budget: Any) -> None:
        values = budget.to_dict() if hasattr(budget, "to_dict") else dict(budget)
        table = Table(show_header=True, header_style=RICH_TABLE_HEADER_STYLE)
        table.add_column("Metric")
        table.add_column("Value")
        for key, value in values.items():
            table.add_row(str(key), str(value))
        self.console.print(Panel(table, title=RICH_BUDGET_PANEL_TITLE, border_style="blue"))

    def print_candidates(self, scored_candidates: Iterable[Any], max_rows: int = 15) -> None:
        table = Table(
            title=RICH_CANDIDATES_TABLE_TITLE,
            show_header=True,
            header_style=RICH_TABLE_HEADER_STYLE,
        )
        table.add_column("Rank", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Validation", justify="center")
        table.add_column("Identity", justify="center")
        table.add_column("EAN", justify="center")
        table.add_column("Qty", justify="center")
        table.add_column("Retailer", justify="center")
        table.add_column("Scrapable", justify="center")
        table.add_column("Rich", justify="right")
        table.add_column("URL", overflow="fold")
        table.add_column("Reason", overflow="fold")

        for idx, item in enumerate(list(scored_candidates)[:max_rows], start=1):
            scrapable = "yes" if (item.scrape and item.scrape.is_scrapable) else "no"
            richness = f"{item.scrape.richness_score:.2f}" if item.scrape else "-"
            verification = getattr(item, "verification", None)
            identity = verification.identity_status if verification else "-"
            ean_check = verification.ean_check if verification else "-"
            qty_check = verification.quantity_check if verification else "-"
            retailer_check = getattr(item, "retailer_check", "-")
            breakdown = getattr(item, "confidence_breakdown", None)
            validation = breakdown.validation_status if breakdown else "-"
            table.add_row(
                str(idx),
                f"{item.confidence:.3f}",
                validation,
                identity,
                ean_check,
                qty_check,
                retailer_check,
                scrapable,
                richness,
                item.candidate.url,
                item.reason,
            )

        self.console.print(table)

    def print_verification(self, match_or_scored: Any) -> None:
        """Render the identity verification + confidence breakdown for auditing."""
        verification = getattr(match_or_scored, "verification", None)
        breakdown = getattr(match_or_scored, "confidence_breakdown", None)

        if verification is not None:
            table = Table(show_header=True, header_style=RICH_TABLE_HEADER_STYLE)
            table.add_column("Identity Check")
            table.add_column("Result", overflow="fold")
            for key, value in verification.to_dict().items():
                table.add_row(str(key), "" if value is None else str(value))
            self.console.print(
                Panel(table, title="Product Identity Verification", border_style="magenta")
            )

        if breakdown is not None:
            table = Table(
                title="Confidence Breakdown",
                show_header=True,
                header_style=RICH_TABLE_HEADER_STYLE,
            )
            table.add_column("Component")
            table.add_column("Raw", justify="right")
            table.add_column("Weight", justify="right")
            table.add_column("Contribution", justify="right")
            table.add_column("Justification", overflow="fold")
            for component in breakdown.components:
                table.add_row(
                    component.name,
                    f"{component.raw_score:.3f}",
                    f"{component.weight:.3f}",
                    f"{component.contribution:.3f}",
                    component.justification,
                )
            self.console.print(table)

            if breakdown.caps_applied:
                cap_table = Table(
                    title="Caps Applied",
                    show_header=True,
                    header_style=RICH_TABLE_HEADER_STYLE,
                )
                cap_table.add_column("Cap", justify="right")
                cap_table.add_column("Reason", overflow="fold")
                for cap in breakdown.caps_applied:
                    cap_table.add_row(str(cap.get("cap")), str(cap.get("reason")))
                self.console.print(cap_table)

            self.console.print(
                Panel(
                    f"base={breakdown.base_confidence:.3f} -> final={breakdown.final_confidence:.3f} "
                    f"| status={breakdown.validation_status}\n{breakdown.justification_summary}",
                    title="Confidence Verdict",
                    border_style="green",
                )
            )

    def print_dict(self, payload: Mapping[str, Any], title: str = RICH_PAYLOAD_PANEL_TITLE) -> None:
        table = Table(show_header=True, header_style=RICH_TABLE_HEADER_STYLE)
        table.add_column("Key")
        table.add_column("Value", overflow="fold")
        for key, value in payload.items():
            table.add_row(str(key), "" if value is None else str(value))
        self.console.print(Panel(table, title=title))


def configure_logging(level: str = DEFAULT_LOG_LEVEL) -> None:
    logger.remove()
    logger.add(sys.stderr, level=level.upper(), colorize=True, format=LOGURU_FORMAT)
