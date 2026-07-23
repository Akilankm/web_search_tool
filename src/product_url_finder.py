from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig


@dataclass(frozen=True)
class Settings:
    serpapi_api_key: str
    serp_calls: int = 3
    serp_results_per_call: int = 10
    crawl_candidates: int = 5
    artifact_root: Path = Path("data/artifacts")
    llm_enabled: bool = False
    llm_required: bool = False
    llm_api_key: str = ""
    llm_api_version: str = "2024-10-21"
    llm_endpoint: str = ""
    llm_deployment: str = ""
    llm_consumer_id: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            serpapi_api_key=_env("SERPAPI_API_KEY"),
            serp_calls=_env_int("SERP_CALL_BUDGET", 3, 1, 5),
            serp_results_per_call=_env_int("SERP_RESULTS_PER_CALL", 10, 3, 20),
            crawl_candidates=_env_int("CRAWL_CANDIDATE_BUDGET", 5, 1, 10),
            artifact_root=Path(_env("ARTIFACT_ROOT", "data/artifacts")),
            llm_enabled=_env_bool("PRODUCT_URL_REASONING_ENABLED", False),
            llm_required=_env_bool("PRODUCT_URL_REASONING_REQUIRED", False),
            llm_api_key=_env("PCA_LLM_API_KEY"),
            llm_api_version=_env("PCA_LLM_API_VERSION", "2024-10-21"),
            llm_endpoint=_env("PCA_LLM_ENDPOINT"),
            llm_deployment=_env("PCA_LLM_DEPLOYMENT"),
            llm_consumer_id=_env("PCA_LLM_CONSUMER_ID"),
        )

    def validate(self) -> None:
        if not self.serpapi_api_key:
            raise ValueError("SERPAPI_API_KEY is required.")
        if self.llm_enabled:
            missing = [
                name for name, value in {
                    "PCA_LLM_API_KEY": self.llm_api_key,
                    "PCA_LLM_API_VERSION": self.llm_api_version,
                    "PCA_LLM_ENDPOINT": self.llm_endpoint,
                    "PCA_LLM_DEPLOYMENT": self.llm_deployment,
                    "PCA_LLM_CONSUMER_ID": self.llm_consumer_id,
                }.items() if not value
            ]
            if missing and self.llm_required:
                raise ValueError("Missing required PCA LLM settings: " + ", ".join(missing))


@dataclass(frozen=True)
class ProductInput:
    main_text: str
    country_code: str
    ean: str | None = None
    retailer_name: str | None = None
    row_id: str | None = None

    def normalized(self) -> "ProductInput":
        main_text = " ".join(self.main_text.split())
        country_code = self.country_code.strip().upper()
        ean = re.sub(r"\D", "", self.ean or "") or None
        retailer = " ".join((self.retailer_name or "").split()) or None
        row_id = (self.row_id or _safe_id(main_text))[:80]
        if not main_text:
            raise ValueError("main_text is mandatory.")
        if not re.fullmatch(r"[A-Z]{2}", country_code):
            raise ValueError("country_code must contain exactly two letters.")
        if ean and len(ean) not in {8, 12, 13, 14}:
            raise ValueError("ean must contain 8, 12, 13, or 14 digits.")
        return ProductInput(main_text, country_code, ean, retailer, row_id)


async def resolve_product(product: ProductInput, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or Settings.from_env()
    settings.validate()
    product = product.normalized()

    artifact_dir = settings.artifact_root / str(product.row_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_json(artifact_dir / "input.json", asdict(product))

    identity = _build_identity(product, settings)
    queries = _build_queries(product, identity)[: settings.serp_calls]
    searches = [_serp_search(query, product.country_code, settings) for query in queries]
    _write_json(artifact_dir / "searches.json", searches)

    candidate_urls = _collect_candidates(searches)[: settings.crawl_candidates]
    crawled = await _crawl_urls(candidate_urls)
    candidates = [
        _assess_candidate(product, identity, item, index + 1)
        for index, item in enumerate(crawled)
    ]
    candidates.sort(key=lambda item: item["score"], reverse=True)
    _write_json(artifact_dir / "candidates.json", candidates)

    selected = candidates[0] if candidates and candidates[0]["eligible"] else None
    result = {
        "row_id": product.row_id,
        "main_text": product.main_text,
        "country_code": product.country_code,
        "retailer_name": product.retailer_name or "",
        "ean": product.ean or "",
        "candidate_urls": [item["url"] for item in candidates],
        "product_url": selected["url"] if selected else "",
        "confidence": selected["confidence"] if selected else 0.0,
        "status": "VERIFIED" if selected else "REVIEW_REQUIRED",
        "identity_status": selected["identity_status"] if selected else "UNRESOLVED",
        "retailer_check": selected["retailer_check"] if selected else "NOT_ASSESSED",
        "justification": selected["justification"] if selected else _failure_reason(candidates),
        "artifact_dir": str(artifact_dir),
        "budgets": {
            "serp_calls_used": len(searches),
            "serp_call_budget": settings.serp_calls,
            "crawl_calls_used": len(crawled),
            "crawl_candidate_budget": settings.crawl_candidates,
        },
    }
    _write_json(artifact_dir / "result.json", result)
    (artifact_dir / "audit.md").write_text(
        _audit(product, identity, queries, candidates, result), encoding="utf-8"
    )
    return result


def _build_identity(product: ProductInput, settings: Settings) -> dict[str, Any]:
    identity = {
        "observed_text": product.main_text,
        "ean": product.ean,
        "retailer_name": product.retailer_name,
        "important_tokens": _tokens(product.main_text),
        "llm": {},
    }
    if not settings.llm_enabled:
        return identity
    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_key=settings.llm_api_key,
            api_version=settings.llm_api_version,
            azure_endpoint=settings.llm_endpoint,
            azure_deployment=settings.llm_deployment,
            default_headers={"X-NIQ-CIS-Consumer": settings.llm_consumer_id},
            max_retries=2,
        )
        response = client.chat.completions.create(
            model=settings.llm_deployment,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract product identity only from the supplied text. "
                        "Never invent an EAN, retailer, model, size, variant, pack count, or URL. "
                        "Return JSON with brand, product_name, model, variant, size, pack, "
                        "search_terms, and unknowns. Use null when unknown."
                    ),
                },
                {"role": "user", "content": json.dumps(asdict(product), ensure_ascii=False)},
            ],
        )
        identity["llm"] = json.loads(response.choices[0].message.content or "{}")
    except Exception as exc:
        if settings.llm_required:
            raise
        identity["llm_error"] = f"{type(exc).__name__}: {exc}"
    return identity


def _build_queries(product: ProductInput, identity: dict[str, Any]) -> list[str]:
    quoted = f'"{product.main_text}"'
    queries: list[str] = []
    if product.ean:
        queries.append(f'"{product.ean}" {quoted}')
    if product.retailer_name:
        queries.append(f'{quoted} "{product.retailer_name}" {product.country_code}')
    queries.append(f"{quoted} {product.country_code} product")
    terms = identity.get("llm", {}).get("search_terms") or []
    if isinstance(terms, list) and terms:
        queries.append(" ".join(str(item) for item in terms[:8]))
    return list(dict.fromkeys(queries))


def _serp_search(query: str, country_code: str, settings: Settings) -> dict[str, Any]:
    response = requests.get(
        "https://serpapi.com/search.json",
        params={
            "engine": "google",
            "q": query,
            "gl": country_code.lower(),
            "num": settings.serp_results_per_call,
            "api_key": settings.serpapi_api_key,
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(f"SerpAPI error: {payload['error']}")
    return {
        "query": query,
        "organic_results": payload.get("organic_results", []),
        "shopping_results": payload.get("shopping_results", []),
    }


def _collect_candidates(searches: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for search in searches:
        for section in ("organic_results", "shopping_results"):
            for item in search.get(section, []):
                url = item.get("link") or item.get("product_link")
                if _usable_url(url):
                    urls.append(_strip_tracking(url))
    return list(dict.fromkeys(urls))


async def _crawl_urls(urls: list[str]) -> list[dict[str, Any]]:
    if not urls:
        return []
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=60_000,
        word_count_threshold=5,
        remove_overlay_elements=True,
    )
    output: list[dict[str, Any]] = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for url in urls:
            try:
                result = await crawler.arun(url=url, config=run_config)
                markdown = getattr(result.markdown, "raw_markdown", result.markdown)
                output.append({
                    "url": getattr(result, "url", url) or url,
                    "success": bool(result.success),
                    "markdown": str(markdown or "")[:120_000],
                    "cleaned_html": str(result.cleaned_html or "")[:120_000],
                    "metadata": dict(result.metadata or {}),
                    "error": str(result.error_message or ""),
                })
            except Exception as exc:
                output.append({
                    "url": url,
                    "success": False,
                    "markdown": "",
                    "cleaned_html": "",
                    "metadata": {},
                    "error": f"{type(exc).__name__}: {exc}",
                })
    return output


def _assess_candidate(
    product: ProductInput,
    identity: dict[str, Any],
    page: dict[str, Any],
    rank: int,
) -> dict[str, Any]:
    text = " ".join([
        str(page.get("metadata", {}).get("title", "")),
        page.get("markdown", ""),
        page.get("cleaned_html", ""),
        page.get("url", ""),
    ]).casefold()
    input_tokens = set(identity["important_tokens"])
    matched = {token for token in input_tokens if token in text}
    overlap = len(matched) / max(1, len(input_tokens))
    score = 0.0
    reasons: list[str] = []
    conflicts: list[str] = []

    if page.get("success"):
        score += 0.15
        reasons.append("Crawl4AI rendered the page successfully.")
    if product.ean:
        if product.ean in text:
            score += 0.55
            reasons.append("The supplied EAN is present on the page.")
        else:
            conflicts.append("The supplied EAN was not found on the rendered page.")
    score += min(0.25, overlap * 0.35)
    if overlap >= 0.6:
        reasons.append(f"{len(matched)} important input tokens matched.")

    path = urlparse(page["url"]).path.casefold()
    direct_page = len([part for part in path.split("/") if part]) >= 2
    if direct_page:
        score += 0.05
    else:
        conflicts.append("The URL does not look like a direct product page.")

    retailer_check = "NOT_ASSESSED"
    if product.retailer_name:
        retailer_tokens = _tokens(product.retailer_name)
        retailer_check = "PASS" if any(token in text for token in retailer_tokens) else "FAIL"
        if retailer_check == "PASS":
            score += 0.05
            reasons.append("Requested retailer evidence matched.")
        else:
            conflicts.append("Requested retailer evidence did not match.")

    score = round(min(score, 1.0), 4)
    eligible = (
        page.get("success")
        and direct_page
        and overlap >= 0.45
        and (not product.ean or product.ean in text)
        and retailer_check != "FAIL"
    )
    return {
        "rank": rank,
        "url": page["url"],
        "score": score,
        "confidence": round(score if eligible else min(score, 0.49), 4),
        "eligible": eligible,
        "identity_status": "EXACT" if eligible else "UNVERIFIED",
        "retailer_check": retailer_check,
        "matched_tokens": sorted(matched),
        "conflicts": conflicts,
        "crawl_error": page.get("error", ""),
        "justification": " ".join(reasons + conflicts),
    }


def _failure_reason(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "No usable product candidate URL was discovered."
    return "No candidate passed the minimum identity, direct-page, and rendered-content checks."


def _audit(
    product: ProductInput,
    identity: dict[str, Any],
    queries: list[str],
    candidates: list[dict[str, Any]],
    result: dict[str, Any],
) -> str:
    lines = [
        f"# Product URL resolution — {product.row_id}",
        "",
        f"- Main text: `{product.main_text}`",
        f"- Country: `{product.country_code}`",
        f"- EAN: `{product.ean or 'not provided'}`",
        f"- Retailer: `{product.retailer_name or 'not provided'}`",
        f"- Final status: `{result['status']}`",
        f"- Final URL: {result['product_url'] or 'None'}",
        "",
        "## Search queries",
        *[f"- `{query}`" for query in queries],
        "",
        "## Candidates",
        "",
        "| Score | Eligible | Identity | Retailer | URL |",
        "|---:|---|---|---|---|",
        *[
            f"| {item['score']:.4f} | {item['eligible']} | {item['identity_status']} | "
            f"{item['retailer_check']} | {item['url']} |"
            for item in candidates
        ],
        "",
        "## Identity used",
        "",
        "```json",
        json.dumps(identity, ensure_ascii=False, indent=2),
        "```",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
    ]
    return "\n".join(lines)


def _tokens(value: str) -> list[str]:
    stop = {
        "the", "and", "for", "with", "from", "this", "that", "der", "die", "das",
        "und", "mit", "pour", "avec", "product", "item", "pack",
    }
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", value.casefold())
        if token not in stop
    ]


def _usable_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    blocked = ("/search", "/category", "/collections", "/login", "/cart")
    return not any(part in parsed.path.casefold() for part in blocked)


def _strip_tracking(url: str) -> str:
    return url.split("?", 1)[0].rstrip("/")


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned[:60] or "product"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default)).strip()


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).casefold() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(_env(name, str(default)))))
