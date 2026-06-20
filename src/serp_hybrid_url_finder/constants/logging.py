"""Logging and Rich-printing constants."""

from __future__ import annotations

from typing import Final

DEFAULT_LOG_LEVEL: Final[str] = "INFO"
LOGURU_FORMAT: Final[str] = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

RICH_TABLE_HEADER_STYLE: Final[str] = "bold"
RICH_MATCH_PANEL_TITLE: Final[str] = "Best Product URL Match"
RICH_BUDGET_PANEL_TITLE: Final[str] = "Per-Product Call Budget"
RICH_CANDIDATES_TABLE_TITLE: Final[str] = "Ranked Candidates"
RICH_PAYLOAD_PANEL_TITLE: Final[str] = "Payload"
RICH_PANEL_BORDER_STYLE: Final[str] = "green"
