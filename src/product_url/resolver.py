from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

SERPAPI_URL = "https://serpapi.com/search.json"
TRACKING = {"fbclid", "gclid", "ref", "source", "srsltid"}
BAD_PAGE = re.compile(r"/(search|suche|category|collection|login|cart)(/|$)", re.I)
PRODUCT_CUE = re.compile(r"add to cart|buy now|warenkorb|kaufen|price|preis|in stock|auf lager|product details", re.I)


@dataclass(frozen=True)
class ProductInput:
    main_text: str
    country_code: str
    ean: str | None = None
    retailer_name: str | None = None
    row_id: str | None = None

    def __post_init__(self) -> None:
        text = " ".join(str(self.main_text or "").split())
        country = str(self.country_code or "").strip().upper()
        ean = re.sub(r"\D", "", str(self.ean or "")) or None
        retailer = " ".join(str(self.retailer_name or "").split()) or None
        if not text:
            raise ValueError("main_text is mandatory")
        if not re.fullmatch(r"[A-Z]{2}", country):
            raise ValueError("country_code must contain exactly two letters")
        if ean and len(ean) not in {8, 12, 13, 14}:
            raise ValueError("ean must contain 8, 12, 13, or 14 digits")
        row_id = str(self.row_id or "").strip() or "ROW-" + hashlib.sha1(
            f"{text}|{country}|{ean}|{retailer}".encode()
        ).hexdigest()[:10]
        for name, value in {
            "main_text": text,
            "country_code": country,
            "ean": ean,
            "retailer_name": retailer,
            "row_id": row_id,
        }.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True)
class Budgets:
    searches: int = 3
    search_results: int = 10
    crawls: int = 6
    llm_calls: int = 2

    def __post_init__(self) -> None:
        values = asdict(self).values()
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("budgets must be non-negative integers")
        if self.searches < 1 or self.crawls < 1:
            raise ValueError("searches and crawls must be at least 1")


class ProductURLResolver:
    """Notebook runtime: interpret -> search -> crawl -> score -> decide."""

    def __init__(self, budgets: Budgets | None = None, artifact_root: str | Path = "data/artifacts") -> None:
        self.budgets = budgets or Budgets()
        self.artifact_root = Path(artifact_root)
        self.serp_key = os.getenv("SERPAPI_API_KEY", "").strip()
        self.use_llm = flag("PRODUCT_URL_REASONING_ENABLED", True)
        self.require_llm = flag("PRODUCT_URL_REASONING_REQUIRED", False)
        self._manager = self._crawler = self._crawl_config = None
        if not self.serp_key:
            raise EnvironmentError("SERPAPI_API_KEY is missing")
        missing = [name for name in PCA_ENV if not os.getenv(name, "").strip()]
        if self.use_llm and missing and self.require_llm:
            raise EnvironmentError("Missing PCA LLM values: " + ", ".join(missing))
        if missing:
            self.use_llm = False

    async def __aenter__(self) -> ProductURLResolver:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

        self._crawl_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=45_000,
            wait_until="domcontentloaded",
            remove_overlay_elements=True,
        )
        self._manager = AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False))
        self._crawler = await self._manager.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._manager:
            await self._manager.__aexit__(exc_type, exc, tb)

    async def resolve(self, product: ProductInput) -> dict[str, Any]:
        if not self._crawler:
            raise RuntimeError("Use ProductURLResolver inside 'async with'")
        usage = {"search_calls": 0, "crawl_calls": 0, "llm_calls": 0}
        errors: list[str] = []
        identity = self._interpret(product, usage, errors)
        queries = build_queries(product, identity, self.budgets.searches)
        candidates: dict[str, dict[str, Any]] = {}
        search_log = []
        for query in queries:
            usage["search_calls"] += 1
            search = serp_search(query, product.country_code, self.serp_key, self.budgets.search_results)
            search_log.append(search)
            if search["error"]:
                errors.append(search["error"])
            for item in search["results"]:
                url = canonical_url(item["url"])
                if url and is_candidate_url(url) and url not in candidates:
                    candidates[url] = {**item, "id": f"C{len(candidates)+1:02d}", "url": url, "query": query}
        ranked = sorted(candidates.values(), key=lambda item: discovery_score(product, identity, item), reverse=True)[: self.budgets.crawls]
        for item in ranked:
            usage["crawl_calls"] += 1
            await crawl(self._crawler, self._crawl_config, item)
            evaluate(product, identity, item)
        llm_choice = self._select_with_llm(product, identity, ranked, usage, errors)
        decision = decide(product, ranked, llm_choice, usage, errors)
        result = {
            "product": asdict(product),
            "budgets": asdict(self.budgets),
            "usage": usage,
            "identity": identity,
            "queries": queries,
            "search": search_log,
            "candidates": [without_page(item) for item in ranked],
            "llm_choice": llm_choice,
            "decision": decision,
        }
        folder = write_artifacts(self.artifact_root, result, ranked)
        result["artifact_dir"] = str(folder)
        result["output"] = output_row(product, ranked, decision, usage, folder)
        return result

    def _interpret(self, product: ProductInput, usage: dict[str, int], errors: list[str]) -> dict[str, Any]:
        base = {"canonical_name": product.main_text, "brand": "", "model": "", "key_terms": terms(product.main_text), "search_queries": [], "uncertainties": []}
        if not self.use_llm or self.budgets.llm_calls < 1:
            return base
        usage["llm_calls"] += 1
        try:
            value = pca_json(
                "Interpret vendor product text without internet. Never invent identifiers, retailer, model, pack count, variant, or URL. Return JSON with canonical_name, brand, model, key_terms, search_queries, uncertainties.",
                asdict(product),
            )
            for key in ("canonical_name", "brand", "model"):
                if clean(value.get(key)):
                    base[key] = clean(value[key])
            for key in ("key_terms", "search_queries", "uncertainties"):
                base[key] = unique([*base[key], *strings(value.get(key))])[:20]
        except Exception as exc:
            errors.append(f"LLM interpretation failed: {type(exc).__name__}: {exc}")
            if self.require_llm:
                raise
        return base

    def _select_with_llm(self, product: ProductInput, identity: dict[str, Any], candidates: list[dict[str, Any]], usage: dict[str, int], errors: list[str]) -> dict[str, Any]:
        empty = {"selected_candidate_id": "", "confidence": 0.0, "reasons": []}
        if not self.use_llm or self.budgets.llm_calls < 2 or not candidates:
            return empty
        usage["llm_calls"] += 1
        evidence = [{"id": x["id"], "url": x.get("final_url") or x["url"], "title": x.get("page_title") or x["title"], "identity_score": x["identity_score"], "product_page": x["product_page"], "identifier_match": x["identifier_match"], "blockers": x["blockers"], "excerpt": x.get("markdown", "")[:2000]} for x in candidates]
        try:
            value = pca_json(
                "Select only the exact direct product page from supplied crawl evidence. A supplied EAN must be present. Return JSON with selected_candidate_id, confidence, reasons. Select nothing when evidence is insufficient.",
                {"product": asdict(product), "identity": identity, "candidates": evidence},
            )
            selected = clean(value.get("selected_candidate_id"))
            if selected not in {x["id"] for x in candidates}:
                selected = ""
            return {"selected_candidate_id": selected, "confidence": probability(value.get("confidence")), "reasons": strings(value.get("reasons"))}
        except Exception as exc:
            errors.append(f"LLM selection failed: {type(exc).__name__}: {exc}")
            if self.require_llm:
                raise
            return empty


def build_queries(product: ProductInput, identity: dict[str, Any], limit: int) -> list[str]:
    queries = []
    anchor = product.ean or product.main_text
    if product.retailer_name:
        queries.append(f'"{anchor}" "{product.retailer_name}"')
    queries += [f'"{product.ean}"', f'"{product.ean}" "{product.main_text}"'] if product.ean else [f'"{product.main_text}"']
    if identity.get("brand") and identity.get("model"):
        queries.append(f'"{identity["brand"]}" "{identity["model"]}"')
    queries += strings(identity.get("search_queries"))
    output = []
    for query in unique(queries):
        if product.ean and product.ean not in query and len(output) < 2:
            continue
        output.append(query)
        if len(output) == limit:
            break
    return output


def serp_search(query: str, country: str, key: str, limit: int) -> dict[str, Any]:
    try:
        response = requests.get(SERPAPI_URL, params={"engine": "google", "q": query, "api_key": key, "gl": country.lower(), "num": limit, "device": "desktop"}, timeout=30)
        response.raise_for_status()
        results = []
        body = response.json()
        for section, source in (("organic_results", "organic"), ("shopping_results", "shopping"), ("inline_shopping_results", "shopping")):
            for item in body.get(section) or []:
                url = clean(item.get("link") or item.get("product_link"))
                if url:
                    results.append({"url": url, "title": clean(item.get("title")), "snippet": clean(item.get("snippet") or item.get("description")), "rank": int(item.get("position") or len(results)+1), "source": source})
                if len(results) >= limit:
                    break
        return {"query": query, "results": results[:limit], "error": ""}
    except Exception as exc:
        return {"query": query, "results": [], "error": f"SerpAPI failed: {type(exc).__name__}: {exc}"}


async def crawl(crawler: Any, config: Any, item: dict[str, Any]) -> None:
    try:
        result = await crawler.arun(url=item["url"], config=config)
        metadata = getattr(result, "metadata", None) or {}
        item.update(crawl_success=bool(getattr(result, "success", False)), final_url=canonical_url(getattr(result, "url", "") or item["url"]), page_title=clean(metadata.get("title")), markdown=markdown(getattr(result, "markdown", "")), html=str(getattr(result, "cleaned_html", "") or getattr(result, "html", "") or ""), crawl_error=clean(getattr(result, "error_message", "")))
    except Exception as exc:
        item.update(crawl_success=False, final_url=item["url"], page_title="", markdown="", html="", crawl_error=f"{type(exc).__name__}: {exc}")


def evaluate(product: ProductInput, identity: dict[str, Any], item: dict[str, Any]) -> None:
    page = " ".join((item.get("page_title", ""), item["title"], item.get("markdown", ""), item.get("final_url") or item["url"]))
    score = min(1.0, 0.85 * coverage(product, identity, normalize(page)) + (0.15 if product.ean and contains_ean(page, product.ean) else 0.0))
    path = urlparse(item.get("final_url") or item["url"]).path
    identifier_match = contains_ean(page, product.ean) if product.ean else None
    product_page = bool(item.get("crawl_success") and not BAD_PAGE.search(path) and (re.search(r'"@type"\s*:\s*"(Product|Book|Toy|Offer)"', item.get("html", ""), re.I) or PRODUCT_CUE.search(page)))
    blockers = []
    if not item.get("crawl_success"):
        blockers.append("Crawl4AI could not retrieve the page")
    if product.ean and not identifier_match:
        blockers.append("Supplied EAN was not found")
    if not product_page:
        blockers.append("Not proven to be a direct product page")
    if score < 0.55:
        blockers.append("Identity evidence is too weak")
    item.update(identity_score=round(score, 4), product_page=product_page, identifier_match=identifier_match, retailer_match=(normalize(product.retailer_name) in normalize(page) if product.retailer_name else None), blockers=blockers, identity_status=("EXACT" if not blockers and score >= 0.75 else "POSSIBLE" if not blockers else "MISMATCH"))


def decide(product: ProductInput, candidates: list[dict[str, Any]], llm: dict[str, Any], usage: dict[str, int], errors: list[str]) -> dict[str, Any]:
    eligible = [item for item in candidates if not item.get("blockers")]
    selected = next((item for item in eligible if item["id"] == llm.get("selected_candidate_id")), None)
    selected = selected or (max(eligible, key=lambda item: (item["identity_score"], item.get("retailer_match") is True, -item["rank"])) if eligible else None)
    if not selected:
        return {"status": "TECHNICAL_FAILURE" if errors and not candidates else "FAILED", "product_url": "", "confidence": 0.0, "identity_status": "UNRESOLVED", "retailer_check": "NOT_PROVIDED" if not product.retailer_name else "NOT_VERIFIED", "justification": "No crawled candidate passed the minimum identity and direct-page gates.", "errors": errors, "usage": usage}
    confidence = selected["identity_score"]
    if llm.get("selected_candidate_id") == selected["id"] and llm.get("confidence"):
        confidence = round((confidence + llm["confidence"]) / 2, 4)
    reasons = llm.get("reasons") or [f"Identity score {selected['identity_score']:.2f}", "Crawl4AI retrieved a direct product page"]
    if product.ean:
        reasons.append("Supplied EAN was verified")
    return {"status": "VERIFIED" if selected["identity_score"] >= 0.75 else "REVIEW_REQUIRED", "product_url": selected.get("final_url") or selected["url"], "confidence": confidence, "identity_status": selected["identity_status"], "retailer_check": "NOT_PROVIDED" if not product.retailer_name else "PASS" if selected.get("retailer_match") else "FAIL", "justification": " ".join(reasons), "errors": errors, "usage": usage}


def output_row(product: ProductInput, candidates: list[dict[str, Any]], decision: dict[str, Any], usage: dict[str, int], folder: Path) -> dict[str, Any]:
    return {"ROW_ID": product.row_id, "MAIN_TEXT": product.main_text, "COUNTRY": product.country_code, "RETAILER": product.retailer_name or "", "EAN": product.ean or "", "PROP_PG_NAME": "", "CANDIDATE_URLS": " | ".join(item.get("final_url") or item["url"] for item in candidates), "PRODUCT_URL": decision["product_url"], "CONFIDENCE": decision["confidence"], "VALIDATION_STATUS": decision["status"], "IDENTITY_STATUS": decision["identity_status"], "RETAILER_CHECK": decision["retailer_check"], "JUSTIFICATION": decision["justification"], "SEARCH_CALLS": usage["search_calls"], "CRAWL_CALLS": usage["crawl_calls"], "LLM_CALLS": usage["llm_calls"], "ARTIFACT_DIR": str(folder), "ERRORS": " | ".join(decision.get("errors") or [])}


def write_artifacts(root: Path, result: dict[str, Any], candidates: list[dict[str, Any]]) -> Path:
    folder = root / re.sub(r"[^A-Za-z0-9._-]+", "_", result["product"]["row_id"])
    pages = folder / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    for item in candidates:
        if item.get("markdown"):
            (pages / f"{item['id']}.md").write_text(item["markdown"][:100_000], encoding="utf-8")
    (folder / "run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    decision = result["decision"]
    lines = [f"# Product URL audit — {result['product']['row_id']}", "", f"- Input: `{result['product']['main_text']}`", f"- Status: `{decision['status']}`", f"- Product URL: {decision['product_url'] or 'None'}", f"- Usage: {result['usage']}", "", "| ID | Identity | Product page | EAN | URL |", "|---|---:|---|---|---|"]
    lines += [f"| {item['id']} | {item.get('identity_score', 0):.2f} | {item.get('product_page')} | {item.get('identifier_match')} | {item.get('final_url') or item['url']} |" for item in candidates]
    lines += ["", "## Decision", "", decision["justification"], "", "## Errors", ""] + ([f"- {error}" for error in decision.get("errors") or []] or ["- None"])
    (folder / "audit.md").write_text("\n".join(lines), encoding="utf-8")
    return folder


def canonical_url(raw: str) -> str:
    try:
        parsed = urlparse(clean(raw))
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_") and key.lower() not in TRACKING]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), re.sub(r"/{2,}", "/", parsed.path or "/"), "", urlencode(query), ""))


def is_candidate_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return bool(host and parsed.path not in {"", "/"} and not BAD_PAGE.search(parsed.path) and not any(value in host for value in ("google.", "youtube.", "facebook.", "instagram.")))


def discovery_score(product: ProductInput, identity: dict[str, Any], item: dict[str, Any]) -> float:
    text = normalize(f"{item['title']} {item['snippet']} {item['url']}")
    return coverage(product, identity, text) + 1 / max(item["rank"], 1) + (1 if product.ean and contains_ean(text, product.ean) else 0) + (0.25 if product.retailer_name and normalize(product.retailer_name) in text else 0)


def coverage(product: ProductInput, identity: dict[str, Any], text: str) -> float:
    wanted = unique([*strings(identity.get("key_terms")), *terms(product.main_text)])[:20]
    return 0.0 if not wanted else sum(normalize(term) in text for term in wanted) / len(wanted)


def pca_json(system: str, payload: dict[str, Any]) -> dict[str, Any]:
    from openai import AzureOpenAI

    deployment = os.getenv("PCA_LLM_DEPLOYMENT", "").strip()
    client = AzureOpenAI(api_key=os.getenv("PCA_LLM_API_KEY", "").strip(), api_version=os.getenv("PCA_LLM_API_VERSION", "").strip(), azure_endpoint=os.getenv("PCA_LLM_ENDPOINT", "").strip(), azure_deployment=deployment, default_headers={"X-NIQ-CIS-Consumer": os.getenv("PCA_LLM_CONSUMER_ID", "").strip()}, max_retries=int(os.getenv("PCA_LLM_MAX_RETRIES", "2")))
    response = client.chat.completions.create(model=deployment, temperature=0.0, response_format={"type": "json_object"}, messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
    value = json.loads(response.choices[0].message.content or "{}")
    if not isinstance(value, dict):
        raise ValueError("LLM response must be one JSON object")
    return value


def normalize(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def terms(value: str) -> list[str]:
    return unique(token for token in normalize(value).split() if len(token) >= 2)


def contains_ean(value: Any, ean: str) -> bool:
    return any(re.sub(r"\D", "", match) == ean for match in re.findall(r"(?:\d[\s._/-]*){8,14}", str(value or "")))


def markdown(value: Any) -> str:
    for name in ("fit_markdown", "raw_markdown"):
        text = getattr(value, name, None)
        if text:
            return str(text)
    return "" if value is None else str(value)


def without_page(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key not in {"markdown", "html"}}


def clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def strings(value: Any) -> list[str]:
    return unique(value) if isinstance(value, list) else []


def unique(values: Any) -> list[str]:
    output, seen = [], set()
    for value in values:
        text = clean(value)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            output.append(text)
    return output


def probability(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def flag(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    return default if not value else value in {"1", "true", "yes", "on"}


PCA_ENV = ["PCA_LLM_API_KEY", "PCA_LLM_API_VERSION", "PCA_LLM_ENDPOINT", "PCA_LLM_DEPLOYMENT", "PCA_LLM_CONSUMER_ID"]
