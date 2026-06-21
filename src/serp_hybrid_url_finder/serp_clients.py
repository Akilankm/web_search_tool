from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import requests
from loguru import logger

from src.serp_hybrid_url_finder.config import SerpAPIConfig
from src.serp_hybrid_url_finder.constants import (
    AI_MODE_NO_MATCH_MARKDOWN,
    AI_STATUS_NO_RESULTS,
    DEFAULT_AI_STATUS,
    DEFAULT_ORGANIC_STATUS,
    HTTP_BAD_REQUEST,
    MASKED_SERPAPI_KEY,
    MAX_ERROR_BODY_CHARS,
    ORGANIC_KEY_DISPLAYED_LINK,
    ORGANIC_KEY_LINK,
    ORGANIC_KEY_POSITION,
    ORGANIC_KEY_SNIPPET,
    ORGANIC_KEY_SOURCE,
    ORGANIC_KEY_TITLE,
    ORGANIC_STATUS_NO_RESULTS,
    REFERENCE_KEY_LINK,
    REFERENCE_KEY_SNIPPET,
    REFERENCE_KEY_SOURCE,
    REFERENCE_KEY_TITLE,
    REFERENCE_KEY_URL,
    RESPONSE_KEY_ERROR,
    RESPONSE_KEY_ID,
    RESPONSE_KEY_ORGANIC_RESULTS,
    RESPONSE_KEY_RECONSTRUCTED_MARKDOWN,
    RESPONSE_KEY_REFERENCES,
    RESPONSE_KEY_SEARCH_METADATA,
    RESPONSE_KEY_STATUS,
    RESPONSE_KEY_TEXT_BLOCKS,
    SERPAPI_ENGINE_GOOGLE,
    SERPAPI_ENGINE_GOOGLE_AI_MODE,
    SERPAPI_NO_RESULTS_ERROR_PHRASES,
    SERPAPI_OUTPUT_JSON,
    SERPAPI_PARAM_API_KEY,
    SERPAPI_PARAM_COUNTRY,
    SERPAPI_PARAM_DEVICE,
    SERPAPI_PARAM_ENGINE,
    SERPAPI_PARAM_LANGUAGE,
    SERPAPI_PARAM_LOCATION,
    SERPAPI_PARAM_NO_CACHE,
    SERPAPI_PARAM_NUM,
    SERPAPI_PARAM_OUTPUT,
    SERPAPI_PARAM_QUERY,
    SERPAPI_SEARCH_URL,
    SERPAPI_TRUE_VALUE,
)
from src.serp_hybrid_url_finder.models import (
    AIReference,
    OrganicSearchResponse,
    OrganicSearchResult,
    ProductQuery,
    SerpAIResponse,
)


class SerpAPIClientError(RuntimeError):
    """Raised when a SerpAPI request fails."""


class SerpAPINoResultsError(SerpAPIClientError):
    """Raised when SerpAPI reports that Google returned no results."""


@dataclass
class _BaseSerpAPIClient:
    config: SerpAPIConfig
    search_url: str = SERPAPI_SEARCH_URL
    _session: requests.Session = field(default_factory=requests.Session, init=False)

    def _base_params(
        self,
        *,
        engine: str,
        query: str,
        country_code: Optional[str] = None,
        language_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        gl = (country_code or self.config.country_code or "").lower().strip()
        hl = (language_code or self.config.language_code or "").lower().strip()
        params: Dict[str, Any] = {
            SERPAPI_PARAM_API_KEY: self.config.api_key,
            SERPAPI_PARAM_ENGINE: engine,
            SERPAPI_PARAM_QUERY: query.strip(),
            SERPAPI_PARAM_COUNTRY: gl,
            SERPAPI_PARAM_LANGUAGE: hl,
            SERPAPI_PARAM_DEVICE: self.config.device,
            SERPAPI_PARAM_OUTPUT: SERPAPI_OUTPUT_JSON,
        }

        if self.config.location:
            params[SERPAPI_PARAM_LOCATION] = self.config.location

        if self.config.no_cache:
            params[SERPAPI_PARAM_NO_CACHE] = SERPAPI_TRUE_VALUE

        return params

    def _get_with_retries(self, params: Dict[str, Any]) -> Dict[str, Any]:
        last_error: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self._session.get(
                    self.search_url,
                    params=params,
                    timeout=self.config.timeout_seconds,
                )

                if not response.ok:
                    body = self._mask_secret(response.text[:MAX_ERROR_BODY_CHARS])
                    url = self._mask_secret(response.url)
                    raise SerpAPIClientError(
                        f"SerpAPI HTTP {response.status_code}\nURL: {url}\nBODY: {body}"
                    )

                data = response.json()

                if RESPONSE_KEY_ERROR in data:
                    error_message = str(data[RESPONSE_KEY_ERROR])

                    if self._is_no_results_error(error_message):
                        raise SerpAPINoResultsError(
                            f"SerpAPI no results: {error_message}"
                        )

                    raise SerpAPIClientError(
                        f"SerpAPI returned error: {error_message}"
                    )

                return data

            except SerpAPINoResultsError:
                # No-results is a valid search outcome. Do not retry.
                raise

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "SerpAPI attempt {} failed: {}",
                    attempt,
                    self._mask_secret(str(exc)),
                )

                if isinstance(exc, SerpAPIClientError) and f"HTTP {HTTP_BAD_REQUEST}" in str(exc):
                    raise

                if attempt >= self.config.max_retries:
                    break

                time.sleep(self.config.backoff_seconds * attempt)

        raise SerpAPIClientError(
            f"SerpAPI request failed after retries: {last_error}"
        ) from last_error

    def _is_no_results_error(self, message: str) -> bool:
        message_lower = message.lower()
        return any(
            phrase.lower() in message_lower
            for phrase in SERPAPI_NO_RESULTS_ERROR_PHRASES
        )

    def _mask_secret(self, text: str) -> str:
        if not self.config.api_key:
            return text
        return text.replace(self.config.api_key, MASKED_SERPAPI_KEY)


@dataclass
class GoogleOrganicSearchClient(_BaseSerpAPIClient):
    """SerpAPI Google Search client for candidate discovery."""

    def search(self, query: str, *, product: Optional[ProductQuery] = None) -> OrganicSearchResponse:
        if not query or not query.strip():
            raise ValueError("query cannot be empty")

        country_code = product.country_code if product else None
        language_code = product.language_code if product else None
        params = self._base_params(
            engine=SERPAPI_ENGINE_GOOGLE,
            query=query,
            country_code=country_code,
            language_code=language_code,
        )
        params[SERPAPI_PARAM_NUM] = self.config.organic_num_results

        logger.info(
            "Calling Google organic search | query_chars={} | query={}",
            len(query),
            query,
        )

        try:
            payload = self._get_with_retries(params)

        except SerpAPINoResultsError as exc:
            logger.warning("Organic search returned no results | query={} | {}", query, exc)
            return OrganicSearchResponse(
                query=query,
                search_id=None,
                status=ORGANIC_STATUS_NO_RESULTS,
                results=[],
                raw={RESPONSE_KEY_ERROR: str(exc)},
            )

        metadata = payload.get(RESPONSE_KEY_SEARCH_METADATA, {}) or {}
        status = metadata.get(RESPONSE_KEY_STATUS, DEFAULT_ORGANIC_STATUS)
        search_id = metadata.get(RESPONSE_KEY_ID)

        results: list[OrganicSearchResult] = []
        for item in payload.get(RESPONSE_KEY_ORGANIC_RESULTS, []) or []:
            if not isinstance(item, dict):
                continue

            url = str(item.get(ORGANIC_KEY_LINK) or "")
            if not url:
                continue

            results.append(
                OrganicSearchResult(
                    url=url,
                    title=str(item.get(ORGANIC_KEY_TITLE) or ""),
                    snippet=str(item.get(ORGANIC_KEY_SNIPPET) or ""),
                    displayed_link=str(item.get(ORGANIC_KEY_DISPLAYED_LINK) or ""),
                    source=str(item.get(ORGANIC_KEY_SOURCE) or ""),
                    position=item.get(ORGANIC_KEY_POSITION),
                    query=query,
                    search_id=search_id,
                    search_status=status,
                )
            )

        logger.info("Organic search returned {} result(s)", len(results))
        return OrganicSearchResponse(
            query=query,
            search_id=search_id,
            status=status,
            results=results,
            raw=payload,
        )


@dataclass
class GoogleAIModeClient(_BaseSerpAPIClient):
    """SerpAPI Google AI Mode client for evidence validation / repair."""

    def search(self, query: str, *, product: Optional[ProductQuery] = None) -> SerpAIResponse:
        if not query or not query.strip():
            raise ValueError("query cannot be empty")

        country_code = product.country_code if product else None
        language_code = product.language_code if product else None
        params = self._base_params(
            engine=SERPAPI_ENGINE_GOOGLE_AI_MODE,
            query=query,
            country_code=country_code,
            language_code=language_code,
        )

        logger.info("Calling Google AI Mode | query_chars={}", len(query))

        try:
            payload = self._get_with_retries(params)

        except SerpAPINoResultsError as exc:
            logger.warning("AI Mode returned no results | {}", exc)
            return SerpAIResponse(
                query=query,
                status=AI_STATUS_NO_RESULTS,
                search_id=None,
                markdown=AI_MODE_NO_MATCH_MARKDOWN,
                text_blocks=[],
                references=[],
                raw={RESPONSE_KEY_ERROR: str(exc)},
            )

        metadata = payload.get(RESPONSE_KEY_SEARCH_METADATA, {}) or {}
        status = metadata.get(RESPONSE_KEY_STATUS, DEFAULT_AI_STATUS)
        search_id = metadata.get(RESPONSE_KEY_ID)

        references = [
            AIReference(
                title=str(ref.get(REFERENCE_KEY_TITLE) or ""),
                link=str(ref.get(REFERENCE_KEY_LINK) or ref.get(REFERENCE_KEY_URL) or ""),
                source=str(ref.get(REFERENCE_KEY_SOURCE) or ""),
                snippet=str(ref.get(REFERENCE_KEY_SNIPPET) or ""),
            )
            for ref in payload.get(RESPONSE_KEY_REFERENCES, []) or []
            if isinstance(ref, dict)
        ]

        logger.info("AI Mode returned {} reference(s)", len(references))
        return SerpAIResponse(
            query=query,
            status=status,
            search_id=search_id,
            markdown=str(payload.get(RESPONSE_KEY_RECONSTRUCTED_MARKDOWN) or ""),
            text_blocks=payload.get(RESPONSE_KEY_TEXT_BLOCKS, []) or [],
            references=references,
            raw=payload,
        )