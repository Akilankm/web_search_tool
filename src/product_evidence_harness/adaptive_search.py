from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import parse_qs, urlparse

import requests
from loguru import logger

from src.product_evidence_harness.config import SerpAPIConfig
from src.product_evidence_harness.contracts import (
    OrganicSearchResponse,
    OrganicSearchResult,
    ProductQuery,
    URLCandidate,
)
from src.product_evidence_harness.llm.service import LLMService
from src.product_evidence_harness.url_utils import normalize_url


class SearchEngine(str, Enum):
    GOOGLE = "google"
    GOOGLE_SHOPPING = "google_shopping"
    GOOGLE_AI_MODE = "google_ai_mode"
    GOOGLE_IMMERSIVE_PRODUCT = "google_immersive_product"
    GOOGLE_LENS = "google_lens"
    AMAZON = "amazon"
    EBAY = "ebay"
    WALMART = "walmart"
    HOME_DEPOT = "home_depot"


DEFAULT_ALLOWED_ENGINES: tuple[str, ...] = tuple(engine.value for engine in SearchEngine)


@dataclass(frozen=True, slots=True)
class SearchHandle:
    kind: str
    value: str
    source_engine: str
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SearchAction:
    engine: str
    purpose: str
    query: str = ""
    scope: str = "country"
    language_code: str = ""
    country_code: str = ""
    page_token: str = ""
    image_url: str = ""
    lens_type: str = "products"
    more_stores: bool = True
    expected_signals: tuple[str, ...] = ()
    reason: str = ""
    planner_source: str = "llm"

    def signature(self) -> str:
        return "|".join(
            [
                self.engine.strip().lower(),
                self.query.strip().lower(),
                self.page_token.strip(),
                self.image_url.strip(),
                self.lens_type.strip().lower(),
            ]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SearchObservation:
    action: SearchAction
    status: str
    search_id: str | None
    results: list[OrganicSearchResult]
    handles: list[SearchHandle] = field(default_factory=list)
    answer_summary: str = ""
    raw_result_count: int = 0
    external_url_count: int = 0
    error: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_response(self) -> OrganicSearchResponse:
        query = self.action.query or (
            f"{self.action.engine}:{self.action.page_token[:24]}"
            if self.action.page_token
            else f"{self.action.engine}:{self.action.image_url[:80]}"
        )
        return OrganicSearchResponse(
            query=query,
            search_id=self.search_id,
            status=self.status,
            results=list(self.results),
            raw=self.raw_payload,
        )

    def compact_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "status": self.status,
            "search_id": self.search_id,
            "raw_result_count": self.raw_result_count,
            "external_url_count": self.external_url_count,
            "handle_count": len(self.handles),
            "handles": [item.to_dict() for item in self.handles[:12]],
            "answer_summary": self.answer_summary[:1200],
            "error": self.error,
        }


class AdaptiveSearchError(RuntimeError):
    pass


@dataclass
class SerpAPIMultiEngineClient:
    config: SerpAPIConfig
    search_url: str = "https://serpapi.com/search.json"
    _session: requests.Session = field(default_factory=requests.Session, init=False)

    def execute(self, action: SearchAction, product: ProductQuery) -> SearchObservation:
        self._validate_action(action)
        params = self._build_params(action, product)
        payload = self._get(params)
        return SerpAPIResponseParser().parse(action, payload)

    def _build_params(self, action: SearchAction, product: ProductQuery) -> dict[str, Any]:
        engine = action.engine
        country = (action.country_code or product.country_code or self.config.country_code or "us").lower()
        language = (action.language_code or product.language_code or self.config.language_code or "en").lower()
        params: dict[str, Any] = {
            "api_key": self.config.api_key,
            "engine": engine,
            "output": "json",
            "device": self.config.device,
        }
        if self.config.no_cache:
            params["no_cache"] = "true"

        if engine in {
            SearchEngine.GOOGLE.value,
            SearchEngine.GOOGLE_SHOPPING.value,
            SearchEngine.GOOGLE_AI_MODE.value,
        }:
            params["q"] = action.query
            params["hl"] = language
            if action.scope != "global":
                params["gl"] = country
                if self.config.location:
                    params["location"] = self.config.location
            if engine == SearchEngine.GOOGLE.value:
                params["num"] = self.config.organic_num_results
        elif engine == SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value:
            params["page_token"] = action.page_token
            params["more_stores"] = "true" if action.more_stores else "false"
        elif engine == SearchEngine.GOOGLE_LENS.value:
            params["url"] = action.image_url
            params["type"] = action.lens_type or "products"
            if action.query:
                params["q"] = action.query
            params["hl"] = language
            params["country"] = country.upper()
        elif engine == SearchEngine.AMAZON.value:
            params["k"] = action.query
            params["amazon_domain"] = _amazon_domain(country)
        elif engine == SearchEngine.EBAY.value:
            params["_nkw"] = action.query
            params["ebay_domain"] = _ebay_domain(country)
        elif engine == SearchEngine.WALMART.value:
            params["query"] = action.query
            params["walmart_domain"] = _walmart_domain(country)
        elif engine == SearchEngine.HOME_DEPOT.value:
            params["q"] = action.query
            params["country"] = "ca" if country == "ca" else "us"
        else:
            raise AdaptiveSearchError(f"Unsupported SerpAPI engine: {engine}")
        return params

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, max(1, self.config.max_retries) + 1):
            try:
                response = self._session.get(
                    self.search_url,
                    params=params,
                    timeout=self.config.timeout_seconds,
                )
                if not response.ok:
                    raise AdaptiveSearchError(
                        f"SerpAPI HTTP {response.status_code}: "
                        f"{self._mask(response.text[:500])}"
                    )
                payload = response.json()
                if payload.get("error"):
                    raise AdaptiveSearchError(str(payload["error"]))
                return payload
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Adaptive SerpAPI engine={} attempt={} failed: {}",
                    params.get("engine"),
                    attempt,
                    self._mask(str(exc)),
                )
                if attempt >= max(1, self.config.max_retries):
                    break
                time.sleep(self.config.backoff_seconds * attempt)
        raise AdaptiveSearchError(
            f"SerpAPI engine {params.get('engine')} failed after retries: {last_error}"
        ) from last_error

    def _mask(self, text: str) -> str:
        return text.replace(self.config.api_key, "***SERPAPI_KEY***") if self.config.api_key else text

    @staticmethod
    def _validate_action(action: SearchAction) -> None:
        if action.engine not in DEFAULT_ALLOWED_ENGINES:
            raise AdaptiveSearchError(f"Unsupported engine: {action.engine}")
        if action.engine == SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value and not action.page_token:
            raise AdaptiveSearchError("google_immersive_product requires page_token")
        if action.engine == SearchEngine.GOOGLE_LENS.value and not action.image_url:
            raise AdaptiveSearchError("google_lens requires image_url")
        if action.engine not in {
            SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value,
            SearchEngine.GOOGLE_LENS.value,
        } and not action.query.strip():
            raise AdaptiveSearchError(f"{action.engine} requires a query")


class SerpAPIResponseParser:
    _SECTIONS: dict[str, tuple[str, ...]] = {
        SearchEngine.GOOGLE.value: (
            "organic_results",
            "shopping_results",
            "inline_shopping_results",
            "product_results",
            "product_sites",
            "knowledge_graph",
        ),
        SearchEngine.GOOGLE_SHOPPING.value: (
            "shopping_results",
            "categorized_shopping_results",
            "inline_shopping_results",
        ),
        SearchEngine.GOOGLE_AI_MODE.value: (
            "references",
            "quick_results",
            "shopping_results",
        ),
        SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value: (
            "product_results",
        ),
        SearchEngine.GOOGLE_LENS.value: (
            "exact_matches",
            "products",
            "visual_matches",
            "knowledge_graph",
        ),
        SearchEngine.AMAZON.value: (
            "featured_products",
            "organic_results",
            "product_ads",
        ),
        SearchEngine.EBAY.value: (
            "organic_results",
            "inline_results",
        ),
        SearchEngine.WALMART.value: (
            "featured_item",
            "organic_results",
        ),
        SearchEngine.HOME_DEPOT.value: (
            "products",
        ),
    }

    def parse(self, action: SearchAction, payload: dict[str, Any]) -> SearchObservation:
        metadata = payload.get("search_metadata") or {}
        status = str(metadata.get("status") or "Success")
        search_id = metadata.get("id")
        results: list[OrganicSearchResult] = []
        handles: list[SearchHandle] = []

        for section in self._SECTIONS.get(action.engine, ()):
            value = payload.get(section)
            if value is None:
                continue
            for record in self._records(value):
                handles.extend(self._handles_from_record(record, action.engine))
                results.extend(self._urls_from_record(record, action, section))

        results.extend(self._derived_native_urls(payload, action))
        results = self._deduplicate_results(results)
        handles = self._deduplicate_handles(handles)
        answer = str(
            payload.get("reconstructed_markdown")
            or payload.get("answer")
            or (payload.get("product_results") or {}).get("title")
            or ""
        )
        return SearchObservation(
            action=action,
            status=status,
            search_id=search_id,
            results=results,
            handles=handles,
            answer_summary=answer,
            raw_result_count=self._count_records(payload, action.engine),
            external_url_count=len(results),
            raw_payload=payload,
        )

    def _urls_from_record(
        self,
        record: dict[str, Any],
        action: SearchAction,
        section: str,
    ) -> list[OrganicSearchResult]:
        title = str(
            record.get("title")
            or record.get("name")
            or record.get("product_title")
            or ""
        )
        snippet = str(
            record.get("snippet")
            or record.get("description")
            or record.get("source")
            or record.get("brand")
            or ""
        )
        position = _integer(record.get("position") or record.get("rank"))
        output: list[OrganicSearchResult] = []
        for key in (
            "link",
            "product_link",
            "url",
            "website",
            "source_link",
            "product_page_url",
        ):
            value = record.get(key)
            if not isinstance(value, str) or not value.startswith(("http://", "https://")):
                continue
            normalized = normalize_url(value)
            if not normalized or not _is_external_candidate(normalized):
                continue
            output.append(
                OrganicSearchResult(
                    url=normalized,
                    title=title,
                    snippet=snippet,
                    displayed_link=str(record.get("displayed_link") or ""),
                    source=f"{action.engine}:{section}",
                    position=position,
                    query=action.query or action.purpose,
                    search_id=None,
                    search_status="Success",
                )
            )
        return output

    def _handles_from_record(
        self,
        record: dict[str, Any],
        engine: str,
    ) -> list[SearchHandle]:
        title = str(record.get("title") or record.get("name") or "")
        output: list[SearchHandle] = []
        direct_keys = {
            "immersive_product_page_token": "immersive_product_page_token",
            "page_token": "immersive_product_page_token",
            "product_id": "product_id",
            "asin": "asin",
            "us_item_id": "walmart_item_id",
        }
        for key, kind in direct_keys.items():
            value = record.get(key)
            if value not in (None, ""):
                output.append(
                    SearchHandle(
                        kind=kind,
                        value=str(value),
                        source_engine=engine,
                        title=title,
                    )
                )
        for key in ("thumbnail", "image", "image_url"):
            value = record.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                output.append(
                    SearchHandle(
                        kind="image_url",
                        value=value,
                        source_engine=engine,
                        title=title,
                    )
                )
        serpapi_link = record.get("serpapi_link")
        if isinstance(serpapi_link, str):
            token = parse_qs(urlparse(serpapi_link).query).get("page_token", [""])[0]
            if token:
                output.append(
                    SearchHandle(
                        kind="immersive_product_page_token",
                        value=token,
                        source_engine=engine,
                        title=title,
                    )
                )
        return output

    def _derived_native_urls(
        self,
        payload: dict[str, Any],
        action: SearchAction,
    ) -> list[OrganicSearchResult]:
        output: list[OrganicSearchResult] = []
        if action.engine == SearchEngine.AMAZON.value:
            domain = _amazon_domain(action.country_code or "us")
            for record in self._records(payload.get("organic_results") or []):
                asin = str(record.get("asin") or "").strip()
                if asin and re.fullmatch(r"[A-Z0-9]{10}", asin):
                    output.append(
                        OrganicSearchResult(
                            url=f"https://{domain}/dp/{asin}",
                            title=str(record.get("title") or ""),
                            snippet="Derived from SerpAPI Amazon ASIN; must pass live validation",
                            source="amazon:asin",
                            position=_integer(record.get("position")),
                            query=action.query,
                            search_status="Success",
                        )
                    )
        if action.engine == SearchEngine.WALMART.value:
            domain = _walmart_domain(action.country_code or "us")
            for record in self._records(payload.get("organic_results") or []):
                item_id = str(record.get("us_item_id") or "").strip()
                if item_id and domain == "walmart.com":
                    output.append(
                        OrganicSearchResult(
                            url=f"https://www.walmart.com/ip/{item_id}",
                            title=str(record.get("title") or ""),
                            snippet="Derived from SerpAPI Walmart item ID; must pass live validation",
                            source="walmart:item_id",
                            position=_integer(record.get("position")),
                            query=action.query,
                            search_status="Success",
                        )
                    )
        return output

    def _records(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from self._records(nested)
        elif isinstance(value, list):
            for item in value:
                yield from self._records(item)

    def _count_records(self, payload: dict[str, Any], engine: str) -> int:
        count = 0
        for section in self._SECTIONS.get(engine, ()):
            value = payload.get(section)
            if value is not None:
                count += sum(1 for _ in self._records(value))
        return count

    @staticmethod
    def _deduplicate_results(
        results: Sequence[OrganicSearchResult],
    ) -> list[OrganicSearchResult]:
        by_url: dict[str, OrganicSearchResult] = {}
        for item in results:
            previous = by_url.get(item.url)
            if previous is None:
                by_url[item.url] = item
                continue
            if len(item.title) + len(item.snippet) > len(previous.title) + len(previous.snippet):
                by_url[item.url] = item
        return list(by_url.values())

    @staticmethod
    def _deduplicate_handles(handles: Sequence[SearchHandle]) -> list[SearchHandle]:
        output: list[SearchHandle] = []
        seen: set[tuple[str, str]] = set()
        for handle in handles:
            key = (handle.kind, handle.value)
            if key in seen:
                continue
            seen.add(key)
            output.append(handle)
        return output


@dataclass
class BudgetAwareSearchPlanner:
    llm_service: LLMService | None = None
    allowed_engines: tuple[str, ...] = DEFAULT_ALLOWED_ENGINES
    require_llm: bool = True
    max_context_candidates: int = 8
    calls: int = 0
    fallbacks: int = 0

    def choose_action(
        self,
        *,
        product: ProductQuery,
        credit_number: int,
        credits_remaining: int,
        observations: Sequence[SearchObservation],
        handles: Sequence[SearchHandle],
        candidates: Sequence[URLCandidate],
        rejection_summary: Mapping[str, int] | None = None,
        used_signatures: set[str] | None = None,
    ) -> SearchAction:
        used_signatures = used_signatures or set()
        available = self._available_engines(product, handles)
        try:
            service = self.llm_service or LLMService()
            prompt = self._prompt(
                product=product,
                credit_number=credit_number,
                credits_remaining=credits_remaining,
                observations=observations,
                handles=handles,
                candidates=candidates,
                rejection_summary=rejection_summary or {},
                available_engines=available,
            )
            self.calls += 1
            response = service.predict(
                prompt,
                system_prompt=self._system_prompt(),
                max_tokens=900,
                temperature=0.0,
                response_format={"type": "json_object"},
                purpose="adaptive_serpapi_search_planning",
            )
            action = self._parse_action(
                response.content,
                product=product,
                available_engines=available,
            )
            if action.signature() in used_signatures:
                raise ValueError("LLM proposed a duplicate search action")
            return action
        except Exception as exc:
            self.fallbacks += 1
            logger.warning(
                "LLM search planner fallback | credit={} | error={}",
                credit_number,
                type(exc).__name__,
            )
            if self.require_llm and self.llm_service is not None:
                raise
            return self.deterministic_fallback(
                product=product,
                credit_number=credit_number,
                observations=observations,
                handles=handles,
                used_signatures=used_signatures,
                available_engines=available,
                fallback_reason=f"{type(exc).__name__}: {exc}",
            )

    def deterministic_fallback(
        self,
        *,
        product: ProductQuery,
        credit_number: int,
        observations: Sequence[SearchObservation],
        handles: Sequence[SearchHandle],
        used_signatures: set[str],
        available_engines: Sequence[str],
        fallback_reason: str = "",
    ) -> SearchAction:
        token = _first_handle(handles, "immersive_product_page_token")
        image = _first_handle(handles, "image_url")
        retailer_engine = _retailer_native_engine(product.retailer_name or "")
        identity_query = _identity_query(product)

        choices: list[SearchAction] = []
        if credit_number == 1 and retailer_engine in available_engines:
            choices.append(
                SearchAction(
                    engine=retailer_engine,
                    purpose="requested_retailer_native_discovery",
                    query=identity_query,
                    scope="country",
                    language_code=product.language_code or "en",
                    country_code=product.country_code,
                    reason="Use the retailer-native result surface before broad web fallback.",
                    planner_source="deterministic_fallback",
                )
            )
        if credit_number == 1 and product.ean:
            choices.append(
                SearchAction(
                    engine=SearchEngine.GOOGLE.value,
                    purpose="exact_identifier_direct_url_discovery",
                    query=_google_exact_query(product),
                    scope="country",
                    language_code=product.language_code or "en",
                    country_code=product.country_code,
                    reason="EAN/GTIN is the strongest direct-page identity anchor.",
                    planner_source="deterministic_fallback",
                )
            )
        if credit_number == 1:
            choices.append(
                SearchAction(
                    engine=SearchEngine.GOOGLE_SHOPPING.value,
                    purpose="resolve_product_identity_and_product_token",
                    query=identity_query,
                    scope="country",
                    language_code=product.language_code or "en",
                    country_code=product.country_code,
                    reason="Shopping is product-oriented and can expose merchant links or immersive tokens.",
                    planner_source="deterministic_fallback",
                )
            )
        if token and SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value in available_engines:
            choices.append(
                SearchAction(
                    engine=SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value,
                    purpose="expand_product_token_to_direct_store_urls",
                    page_token=token.value,
                    scope="country",
                    country_code=product.country_code,
                    reason="Expand the product token into direct merchant product URLs.",
                    planner_source="deterministic_fallback",
                )
            )
        if image and SearchEngine.GOOGLE_LENS.value in available_engines:
            choices.append(
                SearchAction(
                    engine=SearchEngine.GOOGLE_LENS.value,
                    purpose="visual_exact_product_resolution",
                    query=identity_query,
                    image_url=image.value,
                    lens_type="products",
                    scope="country",
                    language_code=product.language_code or "en",
                    country_code=product.country_code,
                    reason="Use available product imagery to resolve ambiguous identity.",
                    planner_source="deterministic_fallback",
                )
            )
        choices.extend(
            [
                SearchAction(
                    engine=SearchEngine.GOOGLE.value,
                    purpose="direct_product_page_recovery",
                    query=_google_exact_query(product),
                    scope="country" if credit_number < 3 else "global",
                    language_code=product.language_code or "en",
                    country_code=product.country_code,
                    reason="Recover durable external product-detail URLs with exact identifiers and phrases.",
                    planner_source="deterministic_fallback",
                ),
                SearchAction(
                    engine=SearchEngine.GOOGLE_AI_MODE.value,
                    purpose="disambiguate_product_and_collect_cited_urls",
                    query=_ai_mode_query(product, observations),
                    scope="country" if credit_number < 3 else "global",
                    language_code=product.language_code or "en",
                    country_code=product.country_code,
                    reason="Use cited sources and shopping results to resolve remaining ambiguity.",
                    planner_source="deterministic_fallback",
                ),
            ]
        )
        for action in choices:
            if action.engine not in available_engines:
                continue
            if action.signature() not in used_signatures:
                if fallback_reason:
                    return SearchAction(
                        **{
                            **action.to_dict(),
                            "reason": f"{action.reason} Planner fallback: {fallback_reason[:180]}",
                        }
                    )
                return action
        raise AdaptiveSearchError("No non-duplicate adaptive search action remains")

    def _parse_action(
        self,
        content: str,
        *,
        product: ProductQuery,
        available_engines: Sequence[str],
    ) -> SearchAction:
        payload = _json_object(content)
        engine = str(payload.get("engine") or "").strip().lower()
        if engine not in available_engines:
            raise ValueError(f"Planner selected unavailable engine: {engine}")
        action = SearchAction(
            engine=engine,
            purpose=str(payload.get("purpose") or "adaptive_product_url_discovery").strip(),
            query=str(payload.get("query") or "").strip(),
            scope=str(payload.get("scope") or "country").strip().lower(),
            language_code=str(payload.get("language_code") or product.language_code or "en").strip(),
            country_code=str(payload.get("country_code") or product.country_code).strip().upper(),
            page_token=str(payload.get("page_token") or "").strip(),
            image_url=str(payload.get("image_url") or "").strip(),
            lens_type=str(payload.get("lens_type") or "products").strip(),
            more_stores=bool(payload.get("more_stores", True)),
            expected_signals=tuple(
                str(item).strip()
                for item in payload.get("expected_signals") or []
                if str(item).strip()
            ),
            reason=str(payload.get("reason") or "").strip(),
            planner_source="llm",
        )
        SerpAPIMultiEngineClient._validate_action(action)
        return action

    def _available_engines(
        self,
        product: ProductQuery,
        handles: Sequence[SearchHandle],
    ) -> tuple[str, ...]:
        configured = tuple(
            item.strip()
            for item in os.getenv(
                "PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES",
                ",".join(self.allowed_engines),
            ).split(",")
            if item.strip()
        )
        allowed = [item for item in configured if item in self.allowed_engines]
        if not _first_handle(handles, "immersive_product_page_token"):
            allowed = [
                item
                for item in allowed
                if item != SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value
            ]
        if not _first_handle(handles, "image_url"):
            allowed = [item for item in allowed if item != SearchEngine.GOOGLE_LENS.value]
        native = _retailer_native_engine(product.retailer_name or "")
        for engine in (
            SearchEngine.AMAZON.value,
            SearchEngine.EBAY.value,
            SearchEngine.WALMART.value,
            SearchEngine.HOME_DEPOT.value,
        ):
            if engine != native:
                allowed = [item for item in allowed if item != engine]
        return tuple(allowed)

    def _prompt(
        self,
        *,
        product: ProductQuery,
        credit_number: int,
        credits_remaining: int,
        observations: Sequence[SearchObservation],
        handles: Sequence[SearchHandle],
        candidates: Sequence[URLCandidate],
        rejection_summary: Mapping[str, int],
        available_engines: Sequence[str],
    ) -> str:
        candidate_rows = [
            {
                "url": item.url[:240],
                "title": item.title[:160],
                "source_types": list(item.source_types)[:4],
                "best_position": item.best_position,
            }
            for item in candidates[: self.max_context_candidates]
        ]
        observation_rows = [
            {
                "credit": index + 1,
                "engine": item.action.engine,
                "purpose": item.action.purpose,
                "status": item.status,
                "external_urls": item.external_url_count,
                "handles": [
                    {"kind": h.kind, "title": h.title[:100]}
                    for h in item.handles[:5]
                ],
                "answer_summary": item.answer_summary[:400],
                "error": item.error[:180],
            }
            for index, item in enumerate(observations)
        ]
        handle_rows = [
            {
                "kind": item.kind,
                "value": item.value if item.kind != "immersive_product_page_token" else item.value[:80] + "…",
                "title": item.title[:120],
                "source_engine": item.source_engine,
            }
            for item in handles[:10]
        ]
        payload = {
            "objective": (
                "Use this SerpAPI credit to maximize the probability of obtaining a direct, "
                "durable, exact-product URL that can pass live scrape and browser validation."
            ),
            "product": product.to_dict(),
            "budget": {
                "credit_number": credit_number,
                "credits_remaining_including_this_one": credits_remaining,
                "maximum_total_credits": 3,
            },
            "available_engines": list(available_engines),
            "previous_observations": observation_rows,
            "available_followup_handles": handle_rows,
            "top_current_candidates": candidate_rows,
            "rejection_summary": dict(rejection_summary),
            "rules": [
                "Choose exactly one engine and one action.",
                "Do not invent URLs, tokens, identifiers, or image URLs.",
                "Use google_immersive_product only with a provided page token.",
                "Use google_lens only with a provided image URL.",
                "Prefer retailer-native search when the requested retailer has a supported native engine.",
                "Prefer Shopping to resolve commercial identity and immersive tokens.",
                "Prefer Immersive Product to expand a token into direct merchant links.",
                "Prefer Google Search for quoted EAN/model/direct-page recovery.",
                "Prefer AI Mode only when ambiguity remains and cited URLs are valuable.",
                "Do not repeat a previous engine/query/handle combination.",
            ],
            "output_schema": {
                "engine": "one available engine",
                "purpose": "short machine-readable purpose",
                "query": "query when required, otherwise empty",
                "scope": "country|global",
                "language_code": "two-letter language",
                "country_code": "two-letter country",
                "page_token": "provided token only when required",
                "image_url": "provided image URL only when required",
                "lens_type": "products|exact_matches|visual_matches",
                "more_stores": True,
                "expected_signals": ["signal"],
                "reason": "brief evidence-based rationale",
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are the budget-aware product URL search planner. You have at most three "
            "SerpAPI credits total. Each credit must be chosen adaptively from the evidence "
            "already obtained. Your job is not to answer the product question; your job is "
            "to choose the next SerpAPI engine and parameters that are most likely to yield "
            "a direct external exact-product URL. Return one strict JSON object only."
        )


def _json_object(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Planner response must be a JSON object")
    return value


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_external_candidate(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host:
        return False
    blocked = (
        "serpapi.com",
        "google.com",
        "googleusercontent.com",
        "gstatic.com",
        "youtube.com",
        "youtu.be",
    )
    return not any(host == item or host.endswith("." + item) for item in blocked)


def _first_handle(
    handles: Sequence[SearchHandle],
    kind: str,
) -> SearchHandle | None:
    return next((item for item in handles if item.kind == kind and item.value), None)


def _identity_query(product: ProductQuery) -> str:
    parts = []
    if product.ean:
        parts.append(product.ean)
    parts.append(product.main_text)
    if product.retailer_name:
        parts.append(product.retailer_name)
    return " ".join(str(item).strip() for item in parts if str(item).strip())


def _google_exact_query(product: ProductQuery) -> str:
    parts = []
    if product.ean:
        parts.append(f'"{product.ean}"')
    main = " ".join(product.main_text.split())
    if main:
        parts.append(f'"{main}"')
    if product.retailer_name:
        parts.append(f'"{product.retailer_name}"')
    parts.extend(["product", "-search", "-category"])
    return " ".join(parts)


def _ai_mode_query(
    product: ProductQuery,
    observations: Sequence[SearchObservation],
) -> str:
    prior = ", ".join(
        f"{item.action.engine}:{item.external_url_count} urls"
        for item in observations[-2:]
    )
    return (
        "Identify the exact commercial product and provide direct retailer or manufacturer "
        f"product-page URLs. Product: {product.main_text}. "
        f"EAN/GTIN: {product.ean or 'not provided'}. "
        f"Requested retailer: {product.retailer_name or 'any'}. "
        f"Country: {product.country_code}. Prior search outcome: {prior or 'none'}."
    )


def _retailer_native_engine(retailer: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", retailer.lower())
    if "amazon" in normalized:
        return SearchEngine.AMAZON.value
    if "ebay" in normalized:
        return SearchEngine.EBAY.value
    if "walmart" in normalized:
        return SearchEngine.WALMART.value
    if "homedepot" in normalized:
        return SearchEngine.HOME_DEPOT.value
    return ""


def _amazon_domain(country: str) -> str:
    return {
        "us": "amazon.com",
        "gb": "amazon.co.uk",
        "uk": "amazon.co.uk",
        "de": "amazon.de",
        "fr": "amazon.fr",
        "it": "amazon.it",
        "es": "amazon.es",
        "ca": "amazon.ca",
        "mx": "amazon.com.mx",
        "jp": "amazon.co.jp",
        "in": "amazon.in",
        "au": "amazon.com.au",
        "br": "amazon.com.br",
        "nl": "amazon.nl",
        "se": "amazon.se",
        "pl": "amazon.pl",
        "sg": "amazon.sg",
        "ae": "amazon.ae",
        "sa": "amazon.sa",
    }.get(country.lower(), "amazon.com")


def _ebay_domain(country: str) -> str:
    return {
        "us": "ebay.com",
        "gb": "ebay.co.uk",
        "uk": "ebay.co.uk",
        "de": "ebay.de",
        "fr": "ebay.fr",
        "it": "ebay.it",
        "es": "ebay.es",
        "ca": "ebay.ca",
        "au": "ebay.com.au",
    }.get(country.lower(), "ebay.com")


def _walmart_domain(country: str) -> str:
    return "walmart.com.mx" if country.lower() == "mx" else "walmart.com"
