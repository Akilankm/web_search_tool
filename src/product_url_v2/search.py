from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from product_url_v2.config import RuntimeConfig
from product_url_v2.interpretation import build_search_context
from product_url_v2.models import (
    Interpretation,
    ProductInput,
    SearchAction,
    SearchObservation,
    SearchResult,
)


_BLOCKED_HOSTS = {
    "google.com", "www.google.com", "serpapi.com", "www.serpapi.com",
    "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com",
    "youtube.com", "www.youtube.com", "tiktok.com", "www.tiktok.com",
}
_TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "ref", "tag"}
_INDIRECT_PATH_HINTS = ("/search", "/category", "/categories", "/collections", "/blog", "/news", "/support", "/help")
_PRODUCT_PATH_HINTS = ("/product", "/products", "/item", "/p/", "/dp/", "/sku", "/shop/")


class SearchClient(Protocol):
    def execute(self, action: SearchAction, product: ProductInput) -> SearchObservation: ...


@dataclass(slots=True)
class SerpAPIClient:
    api_key: str
    timeout_seconds: int = 45
    max_retries: int = 2
    results_per_search: int = 20
    endpoint: str = "https://serpapi.com/search.json"
    session: requests.Session | None = None

    @classmethod
    def from_env(cls, config: RuntimeConfig) -> "SerpAPIClient":
        key = str(os.getenv("SERPAPI_API_KEY") or "").strip()
        if not key:
            raise ValueError("SERPAPI_API_KEY is required")
        return cls(
            api_key=key,
            timeout_seconds=config.request_timeout_seconds,
            max_retries=config.search.max_retries,
            results_per_search=config.search.results_per_search,
        )

    def execute(self, action: SearchAction, product: ProductInput) -> SearchObservation:
        session = self.session or requests.Session()
        params = self._params(action, product)
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = session.get(self.endpoint, params=params, timeout=self.timeout_seconds)
                response.raise_for_status()
                payload = response.json()
                if payload.get("error"):
                    raise RuntimeError(str(payload["error"]))
                return parse_serpapi_response(action, payload)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
        return SearchObservation(action, "ERROR", (), error=f"{type(last_error).__name__}: {last_error}")

    def _params(self, action: SearchAction, product: ProductInput) -> dict[str, Any]:
        params: dict[str, Any] = {"api_key": self.api_key, "engine": action.engine, "output": "json", "no_cache": "true", "device": "desktop"}
        if action.engine == "google_immersive_product":
            params.update({"page_token": action.page_token, "more_stores": "true"})
            return params
        params["q"] = action.query
        params["hl"] = product.language_code or "en"
        if action.scope == "country":
            params["gl"] = product.country_code.lower()
        if action.engine == "google":
            params["num"] = self.results_per_search
        return params


@dataclass(frozen=True, slots=True)
class SearchCampaign:
    actions: tuple[SearchAction, ...]
    observations: tuple[SearchObservation, ...]
    candidates: tuple[SearchResult, ...]


class InformationGainSearchPlanner:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def run(self, product: ProductInput, interpretation: Interpretation, client: SearchClient) -> SearchCampaign:
        observations: list[SearchObservation] = []
        actions: list[SearchAction] = []
        signatures: set[str] = set()
        handles: list[str] = []
        for credit in range(1, self.config.search.credit_limit + 1):
            action = self.plan(credit, product, interpretation, handles, signatures)
            if action.signature in signatures:
                raise RuntimeError(f"duplicate paid search action rejected: {action.signature}")
            signatures.add(action.signature)
            actions.append(action)
            observation = client.execute(action, product)
            observations.append(observation)
            handles.extend(result.page_token for result in observation.results if result.page_token)
        return SearchCampaign(tuple(actions), tuple(observations), deduplicate_results(observations))

    def plan(
        self,
        credit: int,
        product: ProductInput,
        interpretation: Interpretation,
        handles: Sequence[str],
        used_signatures: set[str],
    ) -> SearchAction:
        context = build_search_context(product, interpretation)
        anchors = [str(item) for item in context["exact_anchors"]]
        quoted_text = f'"{interpretation.normalized_text}"'
        retailer = f' "{product.retailer_name}"' if product.retailer_name else ""
        final_credit = credit == self.config.search.credit_limit
        if credit == 1 and not final_credit:
            query = " ".join(dict.fromkeys([*(f'"{item}"' for item in anchors), quoted_text])).strip()
            return SearchAction(credit, "google", "ESTABLISH_IDENTITY", "country", query=query + retailer, rationale="Use exact identifiers and submitted wording before broadening.")
        if not final_credit:
            uncertainty = interpretation.unresolved_discriminators[0] if interpretation.unresolved_discriminators else "variant"
            fresh_handle = next((item for item in handles if f"google_immersive_product|{item}" not in used_signatures), "")
            if fresh_handle:
                return SearchAction(credit, "google_immersive_product", "RESOLVE_UNCERTAINTY", "country", page_token=fresh_handle, target_uncertainty=uncertainty, rationale="Expand a concrete product entity to compare seller and variant evidence.")
            negatives = " ".join(_negative_query(item) for item in interpretation.negative_constraints)
            query = f'{quoted_text} "{uncertainty.replace("_", " ")}" {negatives}'.strip()
            return SearchAction(credit, "google_shopping", "RESOLVE_UNCERTAINTY", "country", query=query, target_uncertainty=uncertainty, rationale="Spend the middle credit on the highest-risk product distinction.")
        fresh_handle = next((item for item in handles if f"google_immersive_product|{item}" not in used_signatures), "")
        if fresh_handle:
            return SearchAction(credit, "google_immersive_product", "MANDATORY_URL_RECOVERY", "global", page_token=fresh_handle, rationale="Recover direct seller URLs from a distinct product entity.")
        query = f'{quoted_text} {" ".join(anchors)} official manufacturer retailer product page'.strip()
        return SearchAction(credit, "google_ai_mode", "MANDATORY_URL_RECOVERY", "global", query=query, rationale="Final credit is reserved for direct external product URL recovery.")


def parse_serpapi_response(action: SearchAction, payload: Mapping[str, Any]) -> SearchObservation:
    sections = {
        "google": ("organic_results", "shopping_results", "inline_shopping_results", "product_results", "knowledge_graph"),
        "google_shopping": ("shopping_results", "categorized_shopping_results", "inline_shopping_results"),
        "google_ai_mode": ("references", "quick_results", "shopping_results"),
        "google_immersive_product": ("product_results",),
    }[action.engine]
    results: list[SearchResult] = []
    for section in sections:
        for record in _records(payload.get(section)):
            title = str(record.get("title") or record.get("name") or record.get("product_title") or "")
            snippet = str(record.get("snippet") or record.get("description") or record.get("source") or record.get("brand") or "")
            position = _positive_int(record.get("position") or record.get("rank"))
            token = _page_token(record)
            for key in ("link", "product_link", "url", "website", "source_link", "product_page_url"):
                raw = record.get(key)
                if not isinstance(raw, str):
                    continue
                url = canonical_url(raw)
                if not url or not is_external_url(url):
                    continue
                results.append(SearchResult(url, title, snippet, f"{action.engine}:{section}", action.engine, action.query or action.purpose, position, is_product_like_url(url), token))
            if token and not any(item.page_token == token for item in results):
                placeholder = f"https://serpapi.local/entity/{token}"
                results.append(SearchResult(placeholder, title, snippet, f"{action.engine}:{section}:handle", action.engine, action.query or action.purpose, position, False, token))
    metadata = payload.get("search_metadata") if isinstance(payload.get("search_metadata"), Mapping) else {}
    return SearchObservation(
        action=action,
        status=str(metadata.get("status") or "SUCCESS").upper(),
        results=_dedupe_search_results(results),
        search_id=str(metadata.get("id") or "") or None,
        answer_summary=str(payload.get("reconstructed_markdown") or payload.get("answer") or ""),
    )


def deduplicate_results(observations: Sequence[SearchObservation]) -> tuple[SearchResult, ...]:
    selected: dict[str, SearchResult] = {}
    for observation in observations:
        for item in observation.results:
            if not item.product_like or item.url.startswith("https://serpapi.local/"):
                continue
            current = selected.get(item.url)
            if current is None or (item.position or 9999) < (current.position or 9999):
                selected[item.url] = item
    return tuple(sorted(selected.values(), key=lambda item: (item.position or 9999, item.url)))


def canonical_url(value: str) -> str:
    try:
        parsed = urlparse(value.strip())
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname.lower().removeprefix("www.")
    port = f":{parsed.port}" if parsed.port and parsed.port not in {80, 443} else ""
    query = [(key, val) for key, values in parse_qs(parsed.query, keep_blank_values=True).items() if key.lower() not in _TRACKING_KEYS for val in values]
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), host + port, path, "", urlencode(query, doseq=True), ""))


def is_external_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return bool(host and host not in _BLOCKED_HOSTS and not host.endswith(".google.com"))


def is_product_like_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.casefold()
    if not is_external_url(url) or path in {"", "/"}:
        return False
    if path.endswith((".pdf", ".jpg", ".jpeg", ".png", ".webp", ".svg", ".doc", ".docx")):
        return False
    if any(hint in path for hint in _INDIRECT_PATH_HINTS):
        return False
    if any(hint in path for hint in _PRODUCT_PATH_HINTS):
        return True
    segments = [item for item in path.split("/") if item]
    return len(segments) >= 2 and bool(re.search(r"[a-z].*\d|\d.*[a-z]", segments[-1], flags=re.I))


def _negative_query(value: str) -> str:
    cleaned = re.sub(r"^not\s+", "", value.strip(), flags=re.I)
    cleaned = re.sub(r"\s+unless\s+evidenced$", "", cleaned, flags=re.I)
    return f'-"{cleaned}"' if cleaned else ""


def _records(value: Any):
    if isinstance(value, Mapping):
        yield value
        for nested in value.values():
            yield from _records(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _records(item)


def _page_token(record: Mapping[str, Any]) -> str:
    for key in ("immersive_product_page_token", "page_token"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    link = str(record.get("serpapi_link") or "")
    return parse_qs(urlparse(link).query).get("page_token", [""])[0] if link else ""


def _positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 else None


def _dedupe_search_results(items: Sequence[SearchResult]) -> tuple[SearchResult, ...]:
    output: dict[tuple[str, str], SearchResult] = {}
    for item in items:
        output[(item.url, item.page_token)] = item
    return tuple(output.values())
