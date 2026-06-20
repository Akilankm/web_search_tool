"""URL extraction / filtering constants."""

from __future__ import annotations

from typing import Final

URL_REGEX: Final[str] = r"https?://[^\s\])}>\"']+"
VALID_URL_SCHEMES: Final[tuple[str, ...]] = ("http", "https")
URL_TRAILING_CHARS_TO_STRIP: Final[str] = '.,;:)]}"'
URL_OBJECT_LINK_KEYS: Final[set[str]] = {"url", "link", "href"}

URL_SOURCE_ORGANIC_1: Final[str] = "organic_search_1"
URL_SOURCE_ORGANIC_2: Final[str] = "organic_search_2"
URL_SOURCE_AI_DECLARED_FINAL: Final[str] = "ai_declared_final"
URL_SOURCE_AI_REFERENCE: Final[str] = "ai_reference"
URL_SOURCE_AI_MARKDOWN: Final[str] = "ai_markdown"
URL_SOURCE_AI_TEXT_BLOCK: Final[str] = "ai_text_block"

BLOCKED_DOMAINS: Final[tuple[str, ...]] = (
    "google.com",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "pinterest.com",
)

BLOCKED_EXTENSIONS: Final[tuple[str, ...]] = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
)
