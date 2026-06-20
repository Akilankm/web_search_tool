"""SerpAPI endpoints, request params, response keys and no-result handling."""

from __future__ import annotations

from typing import Final

# -----------------------------------------------------------------------------
# Endpoints / engines
# -----------------------------------------------------------------------------

SERPAPI_SEARCH_URL: Final[str] = "https://serpapi.com/search.json"

SERPAPI_ENGINE_GOOGLE: Final[str] = "google"
SERPAPI_ENGINE_GOOGLE_AI_MODE: Final[str] = "google_ai_mode"
SERPAPI_OUTPUT_JSON: Final[str] = "json"

SERPAPI_PARAM_API_KEY: Final[str] = "api_key"
SERPAPI_PARAM_ENGINE: Final[str] = "engine"
SERPAPI_PARAM_QUERY: Final[str] = "q"
SERPAPI_PARAM_COUNTRY: Final[str] = "gl"
SERPAPI_PARAM_LANGUAGE: Final[str] = "hl"
SERPAPI_PARAM_DEVICE: Final[str] = "device"
SERPAPI_PARAM_OUTPUT: Final[str] = "output"
SERPAPI_PARAM_LOCATION: Final[str] = "location"
SERPAPI_PARAM_NO_CACHE: Final[str] = "no_cache"
SERPAPI_PARAM_START: Final[str] = "start"
SERPAPI_PARAM_NUM: Final[str] = "num"

SERPAPI_TRUE_VALUE: Final[str] = "true"

DEFAULT_COUNTRY_CODE: Final[str] = "us"
DEFAULT_LANGUAGE_CODE: Final[str] = "en"
DEFAULT_DEVICE: Final[str] = "desktop"
DEFAULT_TIMEOUT_SECONDS: Final[int] = 90
DEFAULT_MAX_RETRIES: Final[int] = 2
DEFAULT_BACKOFF_SECONDS: Final[float] = 2.0
DEFAULT_NO_CACHE: Final[bool] = False
DEFAULT_ORGANIC_NUM_RESULTS: Final[int] = 10
DEFAULT_MAX_CANDIDATES_FOR_AI: Final[int] = 18

HTTP_BAD_REQUEST: Final[int] = 400
MAX_ERROR_BODY_CHARS: Final[int] = 2000


# -----------------------------------------------------------------------------
# No-result handling
# -----------------------------------------------------------------------------

SERPAPI_NO_RESULTS_ERROR_PHRASES: Final[tuple[str, ...]] = (
    "hasn't returned any results",
    "has not returned any results",
    "no results for this query",
    "google hasn't returned any results",
    "google has not returned any results",
)

ORGANIC_STATUS_NO_RESULTS: Final[str] = "No Results"
AI_STATUS_NO_RESULTS: Final[str] = "No Results"

AI_MODE_NO_MATCH_MARKDOWN: Final[str] = (
    "FINAL_URL: NO_MATCH\n"
    "MATCH_DECISION: NO_MATCH\n"
    "CONFIDENCE_REASON: SerpAPI returned no AI Mode results.\n"
    "EAN_EVIDENCE: not_visible\n"
    "TITLE_EVIDENCE: weak\n"
    "RETAILER_EVIDENCE: weak\n"
    "COUNTRY_EVIDENCE: weak\n"
    "PRODUCT_PAGE_EVIDENCE: unknown\n"
    "REJECTED_CANDIDATES: no AI Mode result\n"
)


# -----------------------------------------------------------------------------
# Response keys
# -----------------------------------------------------------------------------

RESPONSE_KEY_SEARCH_METADATA: Final[str] = "search_metadata"
RESPONSE_KEY_STATUS: Final[str] = "status"
RESPONSE_KEY_ID: Final[str] = "id"
RESPONSE_KEY_ORGANIC_RESULTS: Final[str] = "organic_results"
RESPONSE_KEY_REFERENCES: Final[str] = "references"
RESPONSE_KEY_RECONSTRUCTED_MARKDOWN: Final[str] = "reconstructed_markdown"
RESPONSE_KEY_TEXT_BLOCKS: Final[str] = "text_blocks"
RESPONSE_KEY_ERROR: Final[str] = "error"

ORGANIC_KEY_POSITION: Final[str] = "position"
ORGANIC_KEY_TITLE: Final[str] = "title"
ORGANIC_KEY_LINK: Final[str] = "link"
ORGANIC_KEY_SNIPPET: Final[str] = "snippet"
ORGANIC_KEY_DISPLAYED_LINK: Final[str] = "displayed_link"
ORGANIC_KEY_SOURCE: Final[str] = "source"

REFERENCE_KEY_TITLE: Final[str] = "title"
REFERENCE_KEY_LINK: Final[str] = "link"
REFERENCE_KEY_URL: Final[str] = "url"
REFERENCE_KEY_SOURCE: Final[str] = "source"
REFERENCE_KEY_SNIPPET: Final[str] = "snippet"

DEFAULT_AI_STATUS: Final[str] = "Unknown"
DEFAULT_ORGANIC_STATUS: Final[str] = "Unknown"
