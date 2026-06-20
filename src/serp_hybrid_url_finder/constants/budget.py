"""Per-product external call budget constants."""

from __future__ import annotations

from typing import Final

MAX_ORGANIC_SEARCH_CALLS_PER_PRODUCT: Final[int] = 2
MAX_AI_MODE_CALLS_PER_PRODUCT: Final[int] = 2

CALL_TYPE_ORGANIC: Final[str] = "organic_search"
CALL_TYPE_AI_MODE: Final[str] = "ai_mode"
