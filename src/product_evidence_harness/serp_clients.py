from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from loguru import logger

from src.product_evidence_harness.config import SerpAPIConfig
from src.product_evidence_harness.constants import (
    SERPAPI_ENGINE_GOOGLE,
    SERPAPI_ENGINE_GOOGLE_AI_MODE,
    SERPAPI_OUTPUT_JSON,
    SERPAPI_SEARCH_URL,
)
from src.product_evidence_harness.contracts import AIReference, OrganicSearchResponse, ProductQuery, SerpAIResponse
from src.product_evidence_harness.serp_harvester import GoogleSERPHarvester


class SerpAPIClientError(RuntimeError):
    pass


class SerpAPINoResultsError(SerpAPIClientError):
    pass


@dataclass
class _BaseSerpClient:
    config: SerpAPIConfig
    search_url: str = SERPAPI_SEARCH_URL
    _session: requests.Session = field(default_factory=requests.Session, init=False)

    def _params(
        self,
        *,
        engine: str,
        query: str,
        product: Optional[ProductQuery],
        scope: str = "country",
        language_code: Optional[str] = None,
        country_code: Optional[str] = None,
    ) -> dict[str, Any]:
        scope_l = (scope or "country").lower()
        hl = (language_code or (product.language_code if product and product.language_code else self.config.language_code) or "en").lower()
        params: dict[str, Any] = {
            "api_key": self.config.api_key,
            "engine": engine,
            "q": query,
            "hl": hl,
            "device": self.config.device,
            "output": SERPAPI_OUTPUT_JSON,
            **({"no_cache": "true"} if self.config.no_cache else {}),
        }
        if scope_l != "global":
            gl = (country_code or (product.country_code if product else self.config.country_code) or "").lower()
            if gl:
                params["gl"] = gl
            if self.config.location:
                params["location"] = self.config.location
        return params

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self._session.get(self.search_url, params=params, timeout=self.config.timeout_seconds)
                if not response.ok:
                    raise SerpAPIClientError(f"SerpAPI HTTP {response.status_code}: {self._mask(response.text[:500])}")
                payload = response.json()
                error = payload.get("error")
                if error:
                    if "hasn't returned any results" in str(error).lower() or "no results" in str(error).lower():
                        raise SerpAPINoResultsError(str(error))
                    raise SerpAPIClientError(str(error))
                return payload
            except SerpAPINoResultsError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning("SerpAPI attempt {} failed: {}", attempt, self._mask(str(exc)))
                if attempt >= self.config.max_retries:
                    break
                time.sleep(self.config.backoff_seconds * attempt)
        raise SerpAPIClientError(f"SerpAPI request failed after retries: {last_error}") from last_error

    def _mask(self, text: str) -> str:
        return text.replace(self.config.api_key, "***SERPAPI_KEY***") if self.config.api_key else text


@dataclass
class GoogleOrganicSearchClient(_BaseSerpClient):
    harvester: GoogleSERPHarvester = field(default_factory=GoogleSERPHarvester)

    def search(
        self,
        query: str,
        *,
        product: Optional[ProductQuery] = None,
        scope: str = "country",
        language_code: Optional[str] = None,
        country_code: Optional[str] = None,
    ) -> OrganicSearchResponse:
        if not query.strip():
            raise ValueError("query cannot be empty")
        params = self._params(
            engine=SERPAPI_ENGINE_GOOGLE,
            query=query,
            product=product,
            scope=scope,
            language_code=language_code,
            country_code=country_code,
        )
        params["num"] = self.config.organic_num_results
        logger.info("One-response organic search | scope={} | hl={} | query={}", scope, params.get("hl"), query)
        try:
            payload = self._get(params)
        except SerpAPINoResultsError as exc:
            return OrganicSearchResponse(query=query, search_id=None, status="No results", results=[], raw={"error": str(exc)})
        metadata = payload.get("search_metadata", {}) or {}
        search_id = metadata.get("id")
        status = metadata.get("status", "Success")
        results = self.harvester.harvest(payload, query=query, search_id=search_id, status=status)
        logger.info("Harvested {} candidate URL occurrences from one SerpAPI response", len(results))
        return OrganicSearchResponse(query=query, search_id=search_id, status=status, results=results, raw=payload)


@dataclass
class GoogleAIModeClient(_BaseSerpClient):
    """Legacy compatibility client; the default one-credit workflow does not call it."""

    def search(
        self,
        query: str,
        *,
        product: Optional[ProductQuery] = None,
        scope: str = "country",
        language_code: Optional[str] = None,
        country_code: Optional[str] = None,
    ) -> SerpAIResponse:
        if not query.strip():
            raise ValueError("query cannot be empty")
        logger.info("AI Mode search | scope={} | hl={} | query_chars={}", scope, language_code or (product.language_code if product else self.config.language_code), len(query))
        params = self._params(engine=SERPAPI_ENGINE_GOOGLE_AI_MODE, query=query, product=product, scope=scope, language_code=language_code, country_code=country_code)
        try:
            payload = self._get(params)
        except SerpAPINoResultsError as exc:
            return SerpAIResponse(query=query, status="No results", search_id=None, markdown="NO_MATCH", references=[], raw={"error": str(exc)})
        metadata = payload.get("search_metadata", {}) or {}
        refs: list[AIReference] = []
        for ref in payload.get("references", []) or []:
            if isinstance(ref, dict):
                refs.append(
                    AIReference(
                        title=str(ref.get("title") or ""),
                        link=str(ref.get("link") or ref.get("url") or ""),
                        source=str(ref.get("source") or ""),
                        snippet=str(ref.get("snippet") or ""),
                    )
                )
        return SerpAIResponse(
            query=query,
            status=metadata.get("status", "Success"),
            search_id=metadata.get("id"),
            markdown=str(payload.get("reconstructed_markdown") or payload.get("answer") or ""),
            text_blocks=payload.get("text_blocks", []) or [],
            references=refs,
            raw=payload,
        )
