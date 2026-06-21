from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from src.serp_hybrid_url_finder.constants import (
    AI_MATCH_DECISION_NO_MATCH,
    AI_NO_MATCH_VALUE,
    URL_TRAILING_CHARS_TO_STRIP,
)
from src.serp_hybrid_url_finder.models import AIMatchEvidence


@dataclass(frozen=True)
class AIMatchEvidenceParser:
    """Parses structured evidence emitted by AI Mode."""

    def parse(self, markdown: str) -> AIMatchEvidence:
        final_url = self._line_value(markdown, "FINAL_URL")
        if final_url:
            final_url = final_url.strip().rstrip(URL_TRAILING_CHARS_TO_STRIP)
            if final_url.upper() == AI_NO_MATCH_VALUE:
                final_url = None

        return AIMatchEvidence(
            final_url=final_url,
            match_decision=(
                self._line_value(markdown, "MATCH_DECISION") or AI_MATCH_DECISION_NO_MATCH
            ).upper(),
            confidence_reason=self._line_value(markdown, "CONFIDENCE_REASON") or "",
            ean_evidence=(self._line_value(markdown, "EAN_EVIDENCE") or "not_provided").lower(),
            title_evidence=(self._line_value(markdown, "TITLE_EVIDENCE") or "weak").lower(),
            retailer_evidence=(self._line_value(markdown, "RETAILER_EVIDENCE") or "not_provided").lower(),
            country_evidence=(self._line_value(markdown, "COUNTRY_EVIDENCE") or "not_provided").lower(),
            product_page_evidence=(self._line_value(markdown, "PRODUCT_PAGE_EVIDENCE") or "unknown").lower(),
            rejected_candidates=self._line_value(markdown, "REJECTED_CANDIDATES") or "",
        )

    def _line_value(self, text: str, key: str) -> Optional[str]:
        if not text:
            return None

        pattern = re.compile(
            rf"{re.escape(key)}\s*\*{{0,2}}\s*:\s*\*{{0,2}}\s*(.+)",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if not match:
            return None

        value = match.group(1).strip().strip("*").strip()
        return value
