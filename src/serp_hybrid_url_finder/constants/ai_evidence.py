"""AI Mode evidence parsing and scoring constants."""

from __future__ import annotations

from typing import Final

AI_FINAL_URL_LINE_REGEX: Final[str] = (
    r"FINAL_URL\s*\*{0,2}\s*:\s*\*{0,2}\s*"
    r"(https?://[^\s\])}>\"']+|NO_MATCH)"
)
AI_NO_MATCH_VALUE: Final[str] = "NO_MATCH"

AI_MATCH_DECISION_EXACT: Final[str] = "EXACT"
AI_MATCH_DECISION_HIGH: Final[str] = "HIGH"
AI_MATCH_DECISION_MEDIUM: Final[str] = "MEDIUM"
AI_MATCH_DECISION_LOW: Final[str] = "LOW"
AI_MATCH_DECISION_NO_MATCH: Final[str] = "NO_MATCH"

AI_MATCH_DECISION_SCORES: Final[dict[str, float]] = {
    AI_MATCH_DECISION_EXACT: 1.00,
    AI_MATCH_DECISION_HIGH: 0.85,
    AI_MATCH_DECISION_MEDIUM: 0.60,
    AI_MATCH_DECISION_LOW: 0.30,
    AI_MATCH_DECISION_NO_MATCH: 0.00,
}

# Confidence floor applied to the FINAL emitted URL when crawl4ai could NOT
# confirm the page on its scraped content and we are therefore trusting the AI
# Mode decider's verdict (it judged the page against Google's live index).
# Kept strictly BELOW HIGH_CONFIDENCE_THRESHOLD (0.75) so an AI-only pick is
# always surfaced as NEEDS_REVIEW, never as VERIFIED. VERIFIED stays reserved
# for pages whose identity was confirmed by deterministic scrape evidence.
AI_DECISION_CONFIDENCE_FLOOR: Final[dict[str, float]] = {
    AI_MATCH_DECISION_EXACT: 0.70,
    AI_MATCH_DECISION_HIGH: 0.60,
    AI_MATCH_DECISION_MEDIUM: 0.48,
    AI_MATCH_DECISION_LOW: 0.33,
    AI_MATCH_DECISION_NO_MATCH: 0.05,
}

AI_EVIDENCE_MATCHED_VALUE: Final[str] = "matched"
AI_EVIDENCE_PARTIAL_VALUE: Final[str] = "partial"
AI_EVIDENCE_WEAK_VALUE: Final[str] = "weak"
AI_EVIDENCE_NOT_VISIBLE_VALUE: Final[str] = "not_visible"
AI_EVIDENCE_NOT_PROVIDED_VALUE: Final[str] = "not_provided"
AI_EVIDENCE_PRODUCT_DETAIL_VALUE: Final[str] = "product_detail"

AI_EVIDENCE_FIELD_SCORES: Final[dict[str, float]] = {
    AI_EVIDENCE_MATCHED_VALUE: 1.00,
    AI_EVIDENCE_PRODUCT_DETAIL_VALUE: 1.00,
    AI_EVIDENCE_PARTIAL_VALUE: 0.60,
    AI_EVIDENCE_WEAK_VALUE: 0.35,
    AI_EVIDENCE_NOT_VISIBLE_VALUE: 0.15,
    AI_EVIDENCE_NOT_PROVIDED_VALUE: 0.50,
    "category": 0.00,
    "search": 0.00,
    "homepage": 0.00,
    "listing": 0.10,
    "unknown": 0.30,
}
