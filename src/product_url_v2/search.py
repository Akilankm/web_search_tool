from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, Sequence
from urllib.parse import parse_qs, urlparse

import requests

from product_url_v2.contracts import ProductInput
from product_url_v2.interpretation import InterpretationResult, SearchContextPacket, build_search_context
from product_url_v2.metrics import canonical_url
from product_url_v2.policy import is_structurally_product_like_url


class SearchEngine(str, Enum):
    GOOGLE = "google"
    GOOGLE_SHOPPING = "google_shopping"
    GOOGLE_AI_MODE = "google_ai_mode"
    GOOGLE_IMMERSIVE_PRODUCT = "google_immersive_product"


class SearchScope(str, Enum):
    COUNTRY = "country"
    GLOBAL = "global"


class SearchPurpose(str, Enum):
    ESTABLISH_IDENTITY = "ESTABLISH_IDENTITY"
    RESOLVE_UNCERTAINTY = "RESOLVE_UNCERTAINTY"
    MANDATORY_URL_RECOVERY = "MANDATORY_URL_RECOVERY"


@dataclass(frozen=True, slots=True)
class SearchAction:
    credit_number: int
    engine: SearchEngine
    purpose: SearchPurpose
    scope: SearchScope
    query: str = ""
    page_token: str = ""
    country_code: str = ""
    language_code: str = ""
    more_stores: bool = True
    target_uncertainty: str = ""
    expected_signals: tuple[str, ...] = ()
    rationale: str = ""
    planner_source: str = "DETERMINISTIC"

    def __post_init__(self) -> None:
        if self.credit_number < 1:
            raise ValueError("credit_number must be at least 1")
        if self.engine is SearchEngine.GOOGLE_IMMERSIVE_PRODUCT:
            if not self.page_token.strip():
                raise ValueError("google_immersive_product requires page_token")
        elif not self.query.strip():
            raise ValueError(f"{self.engine.value} requires a query")
        if self.scope is SearchScope.COUNTRY:
            if len(self.country_code.strip()) != 2:
                raise ValueError("country search requires a two-letter country_code")

    @property
    def signature(self) -> str:
        return "|".join(
            (
                self.engine.value,
                self.scope.value,
                " ".join(self.query.lower().split()),
                self.page_token.strip(),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["engine"] = self.engine.value
        payload["purpose"] = self.purpose.value
        payload["scope"] = self.scope.value
        return payload


@dataclass(frozen=True, slots=True)
class SearchHandle:
    kind: str
    value: str
    source_engine: SearchEngine
    title: str = ""

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.value.strip():
            raise ValueError("search handle kind and value are required")


@dataclass(frozen=True, slots=True)
class SearchResultRecord:
    url: str
    title: str
    snippet: str
    source_section: str
    position: int | None
    query: str
    structurally_product_like: bool

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("search result URL must be absolute HTTP(S)")
        if self.position is not None and self.position < 1:
            raise ValueError("position must be at least 1")


@dataclass(frozen=True, slots=True)
class SearchObservation:
    action: SearchAction
    status: str
    search_id: str | None
    raw_result_count: int
    results: tuple[SearchResultRecord, ...]
    handles: tuple[SearchHandle, ...] = ()
    answer_summary: str = ""
    error: str = ""

    @property
    def direct_candidates(self) -> tuple[SearchResultRecord, ...]:
        return tuple(item for item in self.results if item.structurally_product_like)

    def compact_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "status": self.status,
            "search_id": self.search_id,
            "raw_result_count": self.raw_result_count,
            "external_result_count": len(self.results),
            "direct_candidate_count": len(self.direct_candidates),
            "handles": [asdict(item) | {"source_engine": item.source_engine.value} for item in self.handles],
            "answer_summary": self.answer_summary[:1000],
            "error": self.error[:500],
        }


@dataclass(frozen=True, slots=True)
class SearchCampaignResult:
    actions: tuple[SearchAction, ...]
    observations: tuple[SearchObservation, ...]
    direct_candidates: tuple[SearchResultRecord, ...]
    handles: tuple[SearchHandle, ...]
    credits_used: int
    credit_limit: int


@dataclass(frozen=True, slots=True)
class SerpAPIConfigV2:
    api_key: str
    endpoint: str = "https://serpapi.com/search.json"
    timeout_seconds: float = 45.0
    max_retries: int = 2
    num_results: int = 20
    no_cache: bool = True
    device: str = "desktop"

    @classmethod
    def from_env(cls) -> "SerpAPIConfigV2":
        api_key = str(os.getenv("SERPAPI_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("SERPAPI_API_KEY is required")
        return cls(
            api_key=api_key,
            endpoint=str(os.getenv("SERPAPI_ENDPOINT") or cls.endpoint).strip(),
            timeout_seconds=float(os.getenv("SERPAPI_TIMEOUT_SECONDS") or 45),
            max_retries=max(1, min(5, int(os.getenv("SERPAPI_MAX_RETRIES") or 2))),
            num_results=max(5, min(100, int(os.getenv("SERPAPI_NUM_RESULTS") or 20))),
            no_cache=str(os.getenv("SERPAPI_NO_CACHE") or "true").lower() in {"1", "true", "yes", "on"},
            device=str(os.getenv("SERPAPI_DEVICE") or "desktop").strip(),
        )


class SearchClient(Protocol):
    def execute(self, action: SearchAction, product: ProductInput) -> SearchObservation: ...


class StructuredSearchReasoner(Protocol):
    def choose_search_action(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class SerpAPIClientV2:
    def __init__(
        self,
        config: SerpAPIConfigV2,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.parser = SerpAPIResponseParserV2()

    def execute(self, action: SearchAction, product: ProductInput) -> SearchObservation:
        params = self._params(action, product)
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                response = self.session.get(
                    self.config.endpoint,
                    params=params,
                    timeout=self.config.timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("error"):
                    raise RuntimeError(str(payload["error"]))
                return self.parser.parse(action, payload)
            except Exception as exc:  # network boundary; converted into observed error
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
        return SearchObservation(
            action=action,
            status="ERROR",
            search_id=None,
            raw_result_count=0,
            results=(),
            error=f"{type(last_error).__name__}: {last_error}",
        )

    def _params(self, action: SearchAction, product: ProductInput) -> dict[str, Any]:
        params: dict[str, Any] = {
            "api_key": self.config.api_key,
            "engine": action.engine.value,
            "output": "json",
            "device": self.config.device,
        }
        if self.config.no_cache:
            params["no_cache"] = "true"
        if action.engine is SearchEngine.GOOGLE_IMMERSIVE_PRODUCT:
            params["page_token"] = action.page_token
            params["more_stores"] = "true" if action.more_stores else "false"
            return params

        params["q"] = action.query
        params["hl"] = action.language_code or product.language_code or "en"
        if action.scope is SearchScope.COUNTRY:
            params["gl"] = (action.country_code or product.country_code).lower()
        if action.engine is SearchEngine.GOOGLE:
            params["num"] = self.config.num_results
        return params


class SerpAPIResponseParserV2:
    _SECTIONS: dict[SearchEngine, tuple[str, ...]] = {
        SearchEngine.GOOGLE: (
            "organic_results",
            "shopping_results",
            "inline_shopping_results",
            "product_results",
            "product_sites",
            "knowledge_graph",
        ),
        SearchEngine.GOOGLE_SHOPPING: (
            "shopping_results",
            "categorized_shopping_results",
            "inline_shopping_results",
        ),
        SearchEngine.GOOGLE_AI_MODE: (
            "references",
            "quick_results",
            "shopping_results",
        ),
        SearchEngine.GOOGLE_IMMERSIVE_PRODUCT: ("product_results",),
    }
    _URL_KEYS = (
        "link",
        "product_link",
        "url",
        "website",
        "source_link",
        "product_page_url",
    )

    def parse(self, action: SearchAction, payload: Mapping[str, Any]) -> SearchObservation:
        metadata = payload.get("search_metadata") or {}
        results: list[SearchResultRecord] = []
        handles: list[SearchHandle] = []
        raw_count = 0
        for section in self._SECTIONS[action.engine]:
            value = payload.get(section)
            if value is None:
                continue
            records = tuple(self._records(value))
            raw_count += len(records)
            for record in records:
                handles.extend(self._handles(record, action.engine))
                results.extend(self._result_records(record, action, section))
        return SearchObservation(
            action=action,
            status=str(metadata.get("status") or "SUCCESS").upper(),
            search_id=str(metadata.get("id") or "") or None,
            raw_result_count=raw_count,
            results=self._deduplicate_results(results),
            handles=self._deduplicate_handles(handles),
            answer_summary=str(
                payload.get("reconstructed_markdown")
                or payload.get("answer")
                or ""
            ),
        )

    def _result_records(
        self,
        record: Mapping[str, Any],
        action: SearchAction,
        section: str,
    ) -> list[SearchResultRecord]:
        title = str(record.get("title") or record.get("name") or record.get("product_title") or "")
        snippet = str(
            record.get("snippet")
            or record.get("description")
            or record.get("source")
            or record.get("brand")
            or ""
        )
        position = self._positive_int(record.get("position") or record.get("rank"))
        output: list[SearchResultRecord] = []
        for key in self._URL_KEYS:
            raw_url = record.get(key)
            if not isinstance(raw_url, str):
                continue
            url = canonical_url(raw_url)
            if not url or not self._external(url):
                continue
            output.append(
                SearchResultRecord(
                    url=url,
                    title=title,
                    snippet=snippet,
                    source_section=f"{action.engine.value}:{section}",
                    position=position,
                    query=action.query or action.purpose.value,
                    structurally_product_like=is_structurally_product_like_url(url),
                )
            )
        return output

    @staticmethod
    def _records(value: Any) -> Iterable[Mapping[str, Any]]:
        if isinstance(value, Mapping):
            yield value
            for nested in value.values():
                yield from SerpAPIResponseParserV2._records(nested)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                yield from SerpAPIResponseParserV2._records(item)

    @staticmethod
    def _handles(record: Mapping[str, Any], engine: SearchEngine) -> list[SearchHandle]:
        title = str(record.get("title") or record.get("name") or "")
        output: list[SearchHandle] = []
        for key in ("immersive_product_page_token", "page_token"):
            value = str(record.get(key) or "").strip()
            if value:
                output.append(SearchHandle("immersive_product_page_token", value, engine, title))
        serpapi_link = str(record.get("serpapi_link") or "")
        if serpapi_link:
            token = parse_qs(urlparse(serpapi_link).query).get("page_token", [""])[0]
            if token:
                output.append(SearchHandle("immersive_product_page_token", token, engine, title))
        return output

    @staticmethod
    def _deduplicate_results(results: Sequence[SearchResultRecord]) -> tuple[SearchResultRecord, ...]:
        by_url: dict[str, SearchResultRecord] = {}
        for item in results:
            previous = by_url.get(item.url)
            if previous is None or len(item.title) + len(item.snippet) > len(previous.title) + len(previous.snippet):
                by_url[item.url] = item
        return tuple(by_url.values())

    @staticmethod
    def _deduplicate_handles(handles: Sequence[SearchHandle]) -> tuple[SearchHandle, ...]:
        output: list[SearchHandle] = []
        seen: set[tuple[str, str]] = set()
        for item in handles:
            key = (item.kind, item.value)
            if key not in seen:
                seen.add(key)
                output.append(item)
        return tuple(output)

    @staticmethod
    def _external(url: str) -> bool:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        blocked = ("google.com", "googleusercontent.com", "serpapi.com", "gstatic.com")
        return bool(host and not any(host == value or host.endswith("." + value) for value in blocked))

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            integer = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return integer if integer >= 1 else None


class InformationGainSearchPlanner:
    """Choose each paid search action from the current hypothesis state."""

    def __init__(
        self,
        *,
        reasoner: StructuredSearchReasoner | None = None,
        require_reasoner: bool = False,
        credit_limit: int = 3,
    ) -> None:
        if not 1 <= credit_limit <= 10:
            raise ValueError("credit_limit must be between 1 and 10")
        self.reasoner = reasoner
        self.require_reasoner = require_reasoner
        self.credit_limit = credit_limit

    def choose(
        self,
        *,
        product: ProductInput,
        interpretation: InterpretationResult,
        credit_number: int,
        observations: Sequence[SearchObservation],
        handles: Sequence[SearchHandle],
        used_signatures: set[str],
    ) -> SearchAction:
        if not 1 <= credit_number <= self.credit_limit:
            raise ValueError("credit_number is outside the configured budget")
        context = build_search_context(interpretation)
        if self.reasoner is not None:
            try:
                payload = self.reasoning_payload(
                    product=product,
                    context=context,
                    credit_number=credit_number,
                    observations=observations,
                    handles=handles,
                    used_signatures=used_signatures,
                )
                raw = self.reasoner.choose_search_action(payload)
                action = self._parse_reasoned_action(raw, product, credit_number)
                if action.signature in used_signatures:
                    raise ValueError("reasoner returned a duplicate search action")
                if credit_number == self.credit_limit and action.purpose is not SearchPurpose.MANDATORY_URL_RECOVERY:
                    raise ValueError("final credit must be mandatory URL recovery")
                return action
            except Exception:
                if self.require_reasoner:
                    raise
        action = self._deterministic_action(
            product=product,
            context=context,
            credit_number=credit_number,
            handles=handles,
        )
        if action.signature in used_signatures:
            action = self._duplicate_recovery(product, context, credit_number, handles)
        if action.signature in used_signatures:
            raise ValueError("no non-duplicate search action remains")
        return action

    def _deterministic_action(
        self,
        *,
        product: ProductInput,
        context: SearchContextPacket,
        credit_number: int,
        handles: Sequence[SearchHandle],
    ) -> SearchAction:
        token = self._first_token(handles)
        language = product.language_code or "en"
        if credit_number == 1:
            query = self._identity_query(product, context)
            engine = SearchEngine.GOOGLE if any(anchor.isdigit() for anchor in context.exact_anchors) else SearchEngine.GOOGLE_SHOPPING
            return SearchAction(
                credit_number=credit_number,
                engine=engine,
                purpose=SearchPurpose.ESTABLISH_IDENTITY,
                scope=SearchScope.COUNTRY,
                query=query,
                country_code=product.country_code,
                language_code=language,
                expected_signals=("EXACT_IDENTIFIER", "MODEL", "DIRECT_PRODUCT_URL"),
                rationale="Establish exact commercial identity from the strongest supplied and extracted anchors.",
            )
        if credit_number == self.credit_limit:
            if token:
                return SearchAction(
                    credit_number=credit_number,
                    engine=SearchEngine.GOOGLE_IMMERSIVE_PRODUCT,
                    purpose=SearchPurpose.MANDATORY_URL_RECOVERY,
                    scope=SearchScope.GLOBAL,
                    page_token=token,
                    language_code=language,
                    expected_signals=("DIRECT_MERCHANT_URL", "DURABLE_PRODUCT_PAGE"),
                    rationale="Expand the real product token into direct merchant URLs on the final credit.",
                )
            return SearchAction(
                credit_number=credit_number,
                engine=SearchEngine.GOOGLE_AI_MODE,
                purpose=SearchPurpose.MANDATORY_URL_RECOVERY,
                scope=SearchScope.GLOBAL,
                query=self._recovery_query(product, context),
                language_code=language,
                expected_signals=("REAL_EXTERNAL_URL", "DIRECT_PRODUCT_PAGE"),
                rationale="Use the final credit to recover a real direct manufacturer or retailer URL.",
            )
        if token:
            return SearchAction(
                credit_number=credit_number,
                engine=SearchEngine.GOOGLE_IMMERSIVE_PRODUCT,
                purpose=SearchPurpose.RESOLVE_UNCERTAINTY,
                scope=SearchScope.COUNTRY,
                page_token=token,
                country_code=product.country_code,
                language_code=language,
                target_uncertainty=self._top_uncertainty(context),
                expected_signals=("MERCHANT_VARIANTS", "PACK_CONFIGURATION", "DIRECT_PRODUCT_URL"),
                rationale="Expand the product token to compare merchant titles and pack configurations.",
            )
        return SearchAction(
            credit_number=credit_number,
            engine=SearchEngine.GOOGLE,
            purpose=SearchPurpose.RESOLVE_UNCERTAINTY,
            scope=SearchScope.COUNTRY,
            query=self._uncertainty_query(product, context),
            country_code=product.country_code,
            language_code=language,
            target_uncertainty=self._top_uncertainty(context),
            expected_signals=("DISCRIMINATING_VARIANT_EVIDENCE", "DIRECT_PRODUCT_URL"),
            rationale="Target the highest-risk unresolved identity discriminator rather than repeating broad discovery.",
        )

    def reasoning_payload(
        self,
        *,
        product: ProductInput,
        context: SearchContextPacket,
        credit_number: int,
        observations: Sequence[SearchObservation],
        handles: Sequence[SearchHandle],
        used_signatures: set[str],
    ) -> dict[str, Any]:
        return {
            "objective": "Choose one SerpAPI action that maximally reduces exact-product URL uncertainty.",
            "credit": {
                "number": credit_number,
                "limit": self.credit_limit,
                "remaining_including_this": self.credit_limit - credit_number + 1,
                "final_credit_requires_mandatory_url_recovery": credit_number == self.credit_limit,
            },
            "product": asdict(product),
            "search_context": context.to_dict(),
            "previous_observations": [item.compact_dict() for item in observations],
            "available_handles": [
                {"kind": item.kind, "value": item.value, "title": item.title, "source_engine": item.source_engine.value}
                for item in handles
            ],
            "used_signatures": sorted(used_signatures),
            "allowed_engines": [item.value for item in SearchEngine],
            "rules": [
                "Choose exactly one action.",
                "Do not invent URLs, page tokens, identifiers, brands, variants or pack configurations.",
                "Target the highest-severity unresolved discriminator.",
                "Use immersive product only with an available page token.",
                "Do not repeat an engine/query/token signature.",
                "The final credit must have purpose MANDATORY_URL_RECOVERY.",
            ],
            "output_schema": {
                "engine": "google|google_shopping|google_ai_mode|google_immersive_product",
                "purpose": "ESTABLISH_IDENTITY|RESOLVE_UNCERTAINTY|MANDATORY_URL_RECOVERY",
                "scope": "country|global",
                "query": "required except immersive product",
                "page_token": "provided token only",
                "target_uncertainty": "specific discriminator",
                "expected_signals": ["signal"],
                "rationale": "evidence-based reason",
            },
        }

    def _parse_reasoned_action(
        self,
        raw: Mapping[str, Any],
        product: ProductInput,
        credit_number: int,
    ) -> SearchAction:
        engine = SearchEngine(str(raw.get("engine") or "").strip().lower())
        purpose = SearchPurpose(str(raw.get("purpose") or "").strip().upper())
        scope = SearchScope(str(raw.get("scope") or "country").strip().lower())
        return SearchAction(
            credit_number=credit_number,
            engine=engine,
            purpose=purpose,
            scope=scope,
            query=str(raw.get("query") or "").strip(),
            page_token=str(raw.get("page_token") or "").strip(),
            country_code=product.country_code if scope is SearchScope.COUNTRY else "",
            language_code=product.language_code or "en",
            target_uncertainty=str(raw.get("target_uncertainty") or "").strip(),
            expected_signals=tuple(str(item).strip() for item in raw.get("expected_signals") or [] if str(item).strip()),
            rationale=str(raw.get("rationale") or "").strip(),
            planner_source="REASONING_MODEL",
        )

    def _duplicate_recovery(
        self,
        product: ProductInput,
        context: SearchContextPacket,
        credit_number: int,
        handles: Sequence[SearchHandle],
    ) -> SearchAction:
        purpose = SearchPurpose.MANDATORY_URL_RECOVERY if credit_number == self.credit_limit else SearchPurpose.RESOLVE_UNCERTAINTY
        return SearchAction(
            credit_number=credit_number,
            engine=SearchEngine.GOOGLE_AI_MODE,
            purpose=purpose,
            scope=SearchScope.GLOBAL if credit_number == self.credit_limit else SearchScope.COUNTRY,
            query=self._recovery_query(product, context) + f" search-step-{credit_number}",
            country_code="" if credit_number == self.credit_limit else product.country_code,
            language_code=product.language_code or "en",
            target_uncertainty=self._top_uncertainty(context),
            expected_signals=("CITED_DIRECT_PRODUCT_URL",),
            rationale="Use a distinct cited-source surface after a duplicate action was rejected.",
        )

    @staticmethod
    def _first_token(handles: Sequence[SearchHandle]) -> str:
        return next((item.value for item in handles if item.kind == "immersive_product_page_token" and item.value), "")

    @staticmethod
    def _top_uncertainty(context: SearchContextPacket) -> str:
        return context.unresolved_discriminators[0] if context.unresolved_discriminators else "exact product identity and pack configuration"

    @staticmethod
    def _quoted_terms(values: Sequence[str]) -> str:
        return " ".join(f'"{value}"' for value in values if value)

    def _identity_query(self, product: ProductInput, context: SearchContextPacket) -> str:
        anchors = self._quoted_terms(context.exact_anchors)
        main = f'"{product.main_text}"'
        retailer = f' "{product.retailer_name}"' if product.retailer_name else ""
        return " ".join(value for value in (anchors, main, retailer, "product") if value).strip()

    def _uncertainty_query(self, product: ProductInput, context: SearchContextPacket) -> str:
        anchors = self._quoted_terms(context.exact_anchors)
        discriminator = self._top_uncertainty(context)
        exclusions = " ".join(f'-"{item}"' for item in context.excluded_interpretations[:4])
        return f'{anchors} "{product.main_text}" {discriminator} {exclusions} product'.strip()

    def _recovery_query(self, product: ProductInput, context: SearchContextPacket) -> str:
        anchors = self._quoted_terms(context.exact_anchors)
        known = " ".join(value for _, value in context.known_facts)
        exclusions = " ".join(f'-"{item}"' for item in context.excluded_interpretations[:4])
        return (
            f'{anchors} "{product.main_text}" {known} {exclusions} '
            "direct official manufacturer or retailer product page URL"
        ).strip()


class SearchCampaign:
    """Execute the complete bounded search budget and preserve every observation."""

    def __init__(self, client: SearchClient, planner: InformationGainSearchPlanner) -> None:
        self.client = client
        self.planner = planner

    def run(
        self,
        product: ProductInput,
        interpretation: InterpretationResult,
    ) -> SearchCampaignResult:
        observations: list[SearchObservation] = []
        actions: list[SearchAction] = []
        handles: list[SearchHandle] = []
        used_signatures: set[str] = set()
        for credit_number in range(1, self.planner.credit_limit + 1):
            action = self.planner.choose(
                product=product,
                interpretation=interpretation,
                credit_number=credit_number,
                observations=observations,
                handles=handles,
                used_signatures=used_signatures,
            )
            if action.signature in used_signatures:
                raise RuntimeError("duplicate search action escaped planner validation")
            used_signatures.add(action.signature)
            actions.append(action)
            observation = self.client.execute(action, product)
            observations.append(observation)
            handles = self._merge_handles(handles, observation.handles)

        direct_by_url: dict[str, SearchResultRecord] = {}
        for observation in observations:
            for item in observation.direct_candidates:
                previous = direct_by_url.get(item.url)
                if previous is None or (item.position or 9999) < (previous.position or 9999):
                    direct_by_url[item.url] = item
        return SearchCampaignResult(
            actions=tuple(actions),
            observations=tuple(observations),
            direct_candidates=tuple(direct_by_url.values()),
            handles=tuple(handles),
            credits_used=len(actions),
            credit_limit=self.planner.credit_limit,
        )

    @staticmethod
    def _merge_handles(
        current: Sequence[SearchHandle],
        additions: Sequence[SearchHandle],
    ) -> list[SearchHandle]:
        output = list(current)
        seen = {(item.kind, item.value) for item in output}
        for item in additions:
            key = (item.kind, item.value)
            if key not in seen:
                seen.add(key)
                output.append(item)
        return output
