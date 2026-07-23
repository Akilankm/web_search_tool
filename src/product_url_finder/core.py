from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI


@dataclass(frozen=True)
class ProductInput:
    main_text: str
    country_code: str
    ean: str | None = None
    retailer_name: str | None = None
    row_id: str = "ROW-1"

    def __post_init__(self) -> None:
        main_text = " ".join(self.main_text.split())
        country = self.country_code.strip().upper()
        ean = re.sub(r"\D", "", self.ean or "") or None
        retailer = " ".join((self.retailer_name or "").split()) or None
        row_id = re.sub(r"[^A-Za-z0-9._-]+", "-", self.row_id.strip()).strip("-") or "ROW-1"

        if not main_text:
            raise ValueError("main_text is mandatory")
        if not re.fullmatch(r"[A-Z]{2}", country):
            raise ValueError("country_code must contain exactly two letters")
        if ean and len(ean) not in {8, 12, 13, 14}:
            raise ValueError("ean must contain 8, 12, 13, or 14 digits")

        object.__setattr__(self, "main_text", main_text)
        object.__setattr__(self, "country_code", country)
        object.__setattr__(self, "ean", ean)
        object.__setattr__(self, "retailer_name", retailer)
        object.__setattr__(self, "row_id", row_id)


@dataclass(frozen=True)
class Budget:
    search_calls: int = 3
    crawl_pages: int = 5
    llm_calls: int = 2

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class Settings:
    serpapi_api_key: str
    llm_api_key: str
    llm_api_version: str
    llm_endpoint: str
    llm_deployment: str
    llm_consumer_id: str
    artifact_root: Path = Path("data/artifacts")

    @classmethod
    def from_env(cls, env_file: str | Path = ".env") -> "Settings":
        load_dotenv(env_file, override=False)
        values = {
            "SERPAPI_API_KEY": os.getenv("SERPAPI_API_KEY", "").strip(),
            "PCA_LLM_API_KEY": os.getenv("PCA_LLM_API_KEY", "").strip(),
            "PCA_LLM_API_VERSION": os.getenv("PCA_LLM_API_VERSION", "").strip(),
            "PCA_LLM_ENDPOINT": os.getenv("PCA_LLM_ENDPOINT", "").strip(),
            "PCA_LLM_DEPLOYMENT": os.getenv("PCA_LLM_DEPLOYMENT", "").strip(),
            "PCA_LLM_CONSUMER_ID": os.getenv("PCA_LLM_CONSUMER_ID", "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise EnvironmentError("Missing .env values: " + ", ".join(missing))
        return cls(
            serpapi_api_key=values["SERPAPI_API_KEY"],
            llm_api_key=values["PCA_LLM_API_KEY"],
            llm_api_version=values["PCA_LLM_API_VERSION"],
            llm_endpoint=values["PCA_LLM_ENDPOINT"],
            llm_deployment=values["PCA_LLM_DEPLOYMENT"],
            llm_consumer_id=values["PCA_LLM_CONSUMER_ID"],
            artifact_root=Path(os.getenv("PRODUCT_URL_ARTIFACT_ROOT", "data/artifacts")),
        )

    def llm_client(self) -> AsyncAzureOpenAI:
        return AsyncAzureOpenAI(
            api_key=self.llm_api_key,
            api_version=self.llm_api_version,
            azure_endpoint=self.llm_endpoint,
            azure_deployment=self.llm_deployment,
            default_headers={"X-NIQ-CIS-Consumer": self.llm_consumer_id},
            max_retries=2,
        )


@dataclass
class RunTrace:
    search_used: int = 0
    crawl_used: int = 0
    llm_used: int = 0
    events: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.events.append(message)
        print(message)


async def resolve_product(
    product: ProductInput,
    *,
    settings: Settings | None = None,
    budget: Budget = Budget(),
) -> dict[str, Any]:
    """Resolve one product using only LLM reasoning, SerpAPI, and Crawl4AI."""
    settings = settings or Settings.from_env()
    trace = RunTrace()
    artifact_dir = settings.artifact_root / product.row_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_json(artifact_dir / "input.json", asdict(product))

    interpretation = await _interpret(product, settings, budget, trace)
    _write_json(artifact_dir / "interpretation.json", interpretation)

    searches = _build_queries(product, interpretation)[: budget.search_calls]
    search_results = []
    for index, query in enumerate(searches, start=1):
        trace.log(f"SEARCH {index}/{len(searches)}: {query}")
        search_results.extend(_serpapi_search(query, product.country_code, settings))
        trace.search_used += 1
    search_results = _deduplicate_search_results(search_results)
    _write_json(artifact_dir / "search_results.json", search_results)

    urls = [item["url"] for item in search_results[: budget.crawl_pages]]
    trace.log(f"CRAWL: {len(urls)} candidate page(s)")
    crawled = await _crawl_urls(urls)
    trace.crawl_used = len(crawled)
    _write_json(artifact_dir / "crawled_candidates.json", crawled)

    decision = await _decide(product, interpretation, crawled, settings, budget, trace)
    decision["row_id"] = product.row_id
    decision["main_text"] = product.main_text
    decision["country_code"] = product.country_code
    decision["retailer_name"] = product.retailer_name or ""
    decision["ean"] = product.ean or ""
    decision["candidate_urls"] = [item["url"] for item in crawled]
    decision["budget"] = asdict(budget)
    decision["usage"] = {
        "search_calls": trace.search_used,
        "crawl_pages": trace.crawl_used,
        "llm_calls": trace.llm_used,
    }
    decision["artifact_dir"] = str(artifact_dir)
    decision["trace"] = trace.events

    _validate_decision(decision, crawled)
    _write_json(artifact_dir / "result.json", decision)
    (artifact_dir / "trace.md").write_text(
        "# Product URL trace\n\n" + "\n".join(f"- {event}" for event in trace.events),
        encoding="utf-8",
    )
    return decision


async def resolve_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    *,
    settings: Settings | None = None,
    budget: Budget = Budget(),
) -> pd.DataFrame:
    """Resolve a CSV sequentially and checkpoint after every row."""
    settings = settings or Settings.from_env()
    source = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    source.columns = [column.strip().lower() for column in source.columns]
    missing = {"main_text", "country_code"} - set(source.columns)
    if missing:
        raise ValueError(f"Missing mandatory columns: {sorted(missing)}")

    products = []
    for index, row in source.iterrows():
        products.append(
            ProductInput(
                row_id=(row.get("row_id") or f"ROW-{index + 1:06d}"),
                main_text=row["main_text"],
                country_code=row["country_code"],
                ean=row.get("ean") or None,
                retailer_name=row.get("retailer_name") or row.get("retailer") or None,
            )
        )
    row_ids = [item.row_id for item in products]
    if len(row_ids) != len(set(row_ids)):
        raise ValueError("row_id values must be unique")

    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, product in enumerate(products, start=1):
        print(f"\n[{index}/{len(products)}] {product.row_id}: {product.main_text}")
        try:
            result = await resolve_product(product, settings=settings, budget=budget)
        except Exception as exc:
            result = {
                "row_id": product.row_id,
                "main_text": product.main_text,
                "country_code": product.country_code,
                "retailer_name": product.retailer_name or "",
                "ean": product.ean or "",
                "candidate_urls": [],
                "product_url": "",
                "confidence": 0.0,
                "validation_status": "TECHNICAL_FAILURE",
                "identity_status": "UNVERIFIED",
                "retailer_check": "NOT_ASSESSED",
                "justification": f"{type(exc).__name__}: {exc}",
                "artifact_dir": "",
            }
        rows.append(_output_row(result))
        pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")
    return pd.DataFrame(rows)


async def _interpret(
    product: ProductInput,
    settings: Settings,
    budget: Budget,
    trace: RunTrace,
) -> dict[str, Any]:
    if trace.llm_used >= budget.llm_calls:
        return {"facts": {}, "unknowns": [], "queries": []}
    trace.log("LLM 1: interpret product identity and search anchors")
    prompt = {
        "main_text": product.main_text,
        "country_code": product.country_code,
        "ean": product.ean,
        "retailer_name": product.retailer_name,
    }
    response = await settings.llm_client().chat.completions.create(
        model=settings.llm_deployment,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract only product identity facts supported by the input. Never invent EAN, "
                    "model, pack count, retailer, or variant. Return JSON with facts, unknowns, "
                    "negative_constraints, and up to three concise web search queries."
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    trace.llm_used += 1
    return json.loads(response.choices[0].message.content or "{}")


def _build_queries(product: ProductInput, interpretation: dict[str, Any]) -> list[str]:
    queries = []
    if product.ean:
        queries.append(f'"{product.ean}"')
    if product.retailer_name:
        queries.append(f'site:{product.retailer_name} "{product.main_text}" {product.country_code}')
    queries.append(f'"{product.main_text}" {product.country_code} product')
    for query in interpretation.get("queries", []):
        if isinstance(query, str) and query.strip():
            queries.append(query.strip())
    return list(dict.fromkeys(queries))


def _serpapi_search(query: str, country_code: str, settings: Settings) -> list[dict[str, Any]]:
    response = requests.get(
        "https://serpapi.com/search.json",
        params={
            "engine": "google",
            "q": query,
            "gl": country_code.lower(),
            "num": 10,
            "api_key": settings.serpapi_api_key,
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(f"SerpAPI: {payload['error']}")
    rows = []
    for item in payload.get("organic_results", []):
        url = str(item.get("link") or "").strip()
        if _is_candidate_url(url):
            rows.append(
                {
                    "url": url,
                    "title": str(item.get("title") or ""),
                    "snippet": str(item.get("snippet") or ""),
                    "position": int(item.get("position") or 999),
                    "query": query,
                }
            )
    return rows


def _is_candidate_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    lowered = url.lower()
    rejected = ("/search", "?q=", "/category", "/collections", "/login", "/account")
    return not any(token in lowered for token in rejected)


def _deduplicate_search_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        url = row["url"].split("#", 1)[0]
        unique.setdefault(url, {**row, "url": url})
    return sorted(unique.values(), key=lambda item: item["position"])


async def _crawl_urls(urls: list[str]) -> list[dict[str, Any]]:
    if not urls:
        return []
    browser = BrowserConfig(headless=True, verbose=False)
    run = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=60_000)
    async with AsyncWebCrawler(config=browser) as crawler:
        results = await crawler.arun_many(urls, config=run)

    rows = []
    for requested_url, result in zip(urls, results):
        markdown = getattr(result, "markdown", "")
        if hasattr(markdown, "raw_markdown"):
            markdown = markdown.raw_markdown
        markdown = str(markdown or "")[:60_000]
        final_url = str(getattr(result, "url", "") or requested_url)
        rows.append(
            {
                "url": final_url,
                "requested_url": requested_url,
                "success": bool(getattr(result, "success", False)),
                "status_code": getattr(result, "status_code", None),
                "markdown": markdown,
                "error": str(getattr(result, "error_message", "") or ""),
            }
        )
    return rows


async def _decide(
    product: ProductInput,
    interpretation: dict[str, Any],
    crawled: list[dict[str, Any]],
    settings: Settings,
    budget: Budget,
    trace: RunTrace,
) -> dict[str, Any]:
    usable = [item for item in crawled if item["success"] and len(item["markdown"]) >= 100]
    if not usable:
        return _failed("No candidate produced usable rendered product content.")
    if trace.llm_used >= budget.llm_calls:
        return _failed("LLM budget exhausted before final verification.")

    trace.log("LLM 2: verify candidates and select the exact direct product page")
    compact = [
        {
            "url": item["url"],
            "status_code": item["status_code"],
            "content": item["markdown"][:12_000],
        }
        for item in usable
    ]
    response = await settings.llm_client().chat.completions.create(
        model=settings.llm_deployment,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Select a URL only when the rendered page is a direct product page for the exact "
                    "submitted product. A supplied EAN must match. Reject category, search, homepage, "
                    "wrong variant, wrong pack, wrong edition, and insufficient evidence. Return JSON: "
                    "product_url, confidence 0..1, validation_status VERIFIED|REVIEW_REQUIRED|FAILED, "
                    "identity_status EXACT|PROBABLE|MISMATCH|UNVERIFIED, retailer_check "
                    "MATCH|MISMATCH|NOT_ASSESSED, justification. FAILED must have empty product_url."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"input": asdict(product), "interpretation": interpretation, "candidates": compact},
                    ensure_ascii=False,
                ),
            },
        ],
    )
    trace.llm_used += 1
    result = json.loads(response.choices[0].message.content or "{}")
    return {
        "product_url": str(result.get("product_url") or "").strip(),
        "confidence": max(0.0, min(1.0, float(result.get("confidence") or 0.0))),
        "validation_status": str(result.get("validation_status") or "FAILED").upper(),
        "identity_status": str(result.get("identity_status") or "UNVERIFIED").upper(),
        "retailer_check": str(result.get("retailer_check") or "NOT_ASSESSED").upper(),
        "justification": str(result.get("justification") or "No justification returned."),
    }


def _validate_decision(decision: dict[str, Any], crawled: list[dict[str, Any]]) -> None:
    statuses = {"VERIFIED", "REVIEW_REQUIRED", "FAILED"}
    if decision["validation_status"] not in statuses:
        raise ValueError("Invalid validation_status from LLM")
    delivered = decision["validation_status"] in {"VERIFIED", "REVIEW_REQUIRED"}
    if delivered != bool(decision["product_url"]):
        raise ValueError("Delivered status and product_url are inconsistent")
    allowed_urls = {item["url"] for item in crawled if item["success"]}
    if decision["product_url"] and decision["product_url"] not in allowed_urls:
        raise ValueError("LLM selected a URL that was not successfully crawled")


def _failed(reason: str) -> dict[str, Any]:
    return {
        "product_url": "",
        "confidence": 0.0,
        "validation_status": "FAILED",
        "identity_status": "UNVERIFIED",
        "retailer_check": "NOT_ASSESSED",
        "justification": reason,
    }


def _output_row(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ROW_ID": result.get("row_id", ""),
        "MAIN_TEXT": result.get("main_text", ""),
        "COUNTRY": result.get("country_code", ""),
        "RETAILER": result.get("retailer_name", ""),
        "EAN": result.get("ean", ""),
        "CANDIDATE_URLS": " | ".join(result.get("candidate_urls", [])),
        "PRODUCT_URL": result.get("product_url", ""),
        "CONFIDENCE": result.get("confidence", 0.0),
        "VALIDATION_STATUS": result.get("validation_status", ""),
        "IDENTITY_STATUS": result.get("identity_status", ""),
        "RETAILER_CHECK": result.get("retailer_check", ""),
        "JUSTIFICATION": result.get("justification", ""),
        "ARTIFACT_DIR": result.get("artifact_dir", ""),
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
