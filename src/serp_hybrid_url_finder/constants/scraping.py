"""crawl4ai scrape verification constants.

Every URL that the pipeline is willing to return as the final answer must be
scraped at least once with crawl4ai and proven to yield real, product-like
content. URLs that cannot be scraped are never returned.
"""

from __future__ import annotations

from typing import Final

SCRAPE_ENABLED_DEFAULT: Final[bool] = True
REQUIRE_SCRAPABLE_FINAL_DEFAULT: Final[bool] = True

# How many of the strongest candidates are actually scraped with crawl4ai per
# product. The final returned URL is always taken from this scraped set. A larger
# pool gives the richness-aware ranker more correct+scrapable pages to compare.
DEFAULT_MAX_URLS_TO_SCRAPE: Final[int] = 8

CRAWL_HEADLESS_DEFAULT: Final[bool] = True
CRAWL_VERBOSE_DEFAULT: Final[bool] = False
CRAWL_PAGE_TIMEOUT_MS: Final[int] = 30_000
CRAWL_MIN_WORD_COUNT: Final[int] = 40
CRAWL_MARKDOWN_EXCERPT_CHARS: Final[int] = 1_500
CRAWL_MAX_HTML_CHARS_FOR_VALIDATION: Final[int] = 250_000
CRAWL_USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# Generic HTTP status interpretation, shared by the scrape verdict.
HTTP_OK_STATUS_MIN: Final[int] = 200
HTTP_OK_STATUS_MAX_EXCLUSIVE: Final[int] = 400
SOFT_BLOCK_HTTP_STATUSES: Final[set[int]] = {401, 403, 429}
DEAD_HTTP_STATUS_MIN: Final[int] = 500
