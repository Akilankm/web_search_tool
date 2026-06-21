from __future__ import annotations

import asyncio
import json
import re
import threading
from dataclasses import dataclass
from html import unescape
from typing import Any, Awaitable, Callable, Optional, TypeVar
from urllib.parse import urlparse

from loguru import logger

from src.serp_hybrid_url_finder.constants import (
    CRAWL_HEADLESS_DEFAULT,
    CRAWL_MARKDOWN_EXCERPT_CHARS,
    CRAWL_MAX_HTML_CHARS_FOR_VALIDATION,
    CRAWL_MIN_WORD_COUNT,
    CRAWL_PAGE_TIMEOUT_MS,
    CRAWL_USER_AGENT,
    CRAWL_VERBOSE_DEFAULT,
    HTTP_OK_STATUS_MAX_EXCLUSIVE,
    HTTP_OK_STATUS_MIN,
    JSONLD_ATTRIBUTE_SKIP_KEYS,
    JSONLD_EAN_KEYS,
    MIN_TOKEN_LENGTH_FOR_TEXT_MATCH,
    NON_PRODUCT_PATH_KEYWORDS,
    PRODUCT_PATH_KEYWORDS,
    RICHNESS_DESCRIPTION_FULL_CREDIT_CHARS,
    RICHNESS_DESCRIPTION_MAX_CHARS,
    RICHNESS_FIELD_WEIGHTS,
    RICHNESS_IMAGES_FULL_CREDIT_COUNT,
    RICHNESS_MAX_IMAGE_URLS,
    RICHNESS_MAX_SPEC_KEY_CHARS,
    RICHNESS_MAX_SPEC_ROWS,
    RICHNESS_MAX_SPEC_VALUE_CHARS,
    RICHNESS_SCORE_ROUND_DIGITS,
    RICHNESS_SPEC_TABLE_MAX_CELLS,
    RICHNESS_SPECS_FULL_CREDIT_COUNT,
    SOFT_BLOCK_HTTP_STATUSES,
    TOKEN_REGEX,
    VERIFICATION_TEXT_MAX_CHARS,
)
from src.serp_hybrid_url_finder.markets import MarketProfile, resolve_market_profile
from src.serp_hybrid_url_finder.models import ProductQuery, ScrapeResult

_T = TypeVar("_T")

_TOKEN_PATTERN = re.compile(TOKEN_REGEX)
_TITLE_TAG_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_TAG_PATTERN = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_PATTERN = re.compile(r"<[^>]+>")
_JSONLD_PATTERN = re.compile(
    r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
_META_DESCRIPTION_PATTERN = re.compile(
    r"<meta[^>]+name\s*=\s*[\"']description[\"'][^>]*content\s*=\s*[\"'](.*?)[\"']",
    re.IGNORECASE | re.DOTALL,
)
_TABLE_ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TABLE_CELL_PATTERN = re.compile(r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>", re.IGNORECASE | re.DOTALL)
_DL_PAIR_PATTERN = re.compile(
    r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", re.IGNORECASE | re.DOTALL
)


class Crawl4AINotInstalledError(RuntimeError):
    """Raised when crawl4ai is required but not importable."""


def _run_coroutine_blocking(factory: Callable[[], Awaitable[_T]]) -> _T:
    """Run an async coroutine to completion from synchronous code.

    Works both in plain scripts and inside an already-running event loop
    (e.g. Jupyter). When a loop is already running we execute the coroutine in
    a dedicated worker thread with its own private event loop, so we never
    interfere with the caller's loop.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop running in this thread: safe to drive a fresh one.
        return asyncio.run(factory())

    result: dict[str, _T] = {}
    failure: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            result["value"] = asyncio.run(factory())
        except BaseException as exc:  # noqa: BLE001 - re-raised in caller thread
            failure["error"] = exc

    thread = threading.Thread(target=_worker, name="crawl4ai-scraper", daemon=True)
    thread.start()
    thread.join()

    if "error" in failure:
        raise failure["error"]
    return result["value"]


@dataclass
class CrawlScraper:
    """crawl4ai-powered scraper that verifies a URL is genuinely scrapable.

    For every URL handed to it, crawl4ai launches a real (headless) browser,
    fetches the page, and returns structured content. The resulting
    :class:`ScrapeResult` is the single source of truth the pipeline uses to
    guarantee that any URL it returns can actually be scraped.
    """

    headless: bool = CRAWL_HEADLESS_DEFAULT
    verbose: bool = CRAWL_VERBOSE_DEFAULT
    page_timeout_ms: int = CRAWL_PAGE_TIMEOUT_MS
    min_word_count: int = CRAWL_MIN_WORD_COUNT
    markdown_excerpt_chars: int = CRAWL_MARKDOWN_EXCERPT_CHARS
    user_agent: str = CRAWL_USER_AGENT
    # Optional explicit market profile. When None the profile is resolved per
    # product from its country_code, so language heuristics are never hardcoded.
    market_profile: Optional[MarketProfile] = None

    def scrape(self, url: str, product: ProductQuery) -> ScrapeResult:
        """Scrape a single URL with crawl4ai."""
        results = self.scrape_many([url], product)
        return results.get(url) or self._not_scraped(url, "no result produced")

    def scrape_many(self, urls: list[str], product: ProductQuery) -> dict[str, ScrapeResult]:
        """Scrape several URLs in one browser session, preserving input order."""
        unique = self._dedupe(urls)
        if not unique:
            return {}

        logger.info("Scraping {} URL(s) with crawl4ai", len(unique))
        try:
            return _run_coroutine_blocking(lambda: self._scrape_many_async(unique, product))
        except Crawl4AINotInstalledError:
            raise
        except Exception as exc:  # noqa: BLE001 - degrade gracefully, mark all failed
            logger.error("crawl4ai scrape batch failed: {}", exc)
            return {url: self._failed(url, str(exc)) for url in unique}

    async def _scrape_many_async(
        self,
        urls: list[str],
        product: ProductQuery,
    ) -> dict[str, ScrapeResult]:
        AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode = self._import_crawl4ai()

        profile = self.market_profile or resolve_market_profile(product.country_code)
        price_pattern = re.compile(profile.build_price_regex(), re.IGNORECASE)

        browser_config = BrowserConfig(
            headless=self.headless,
            verbose=self.verbose,
            user_agent=self.user_agent,
        )
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=self.page_timeout_ms,
            word_count_threshold=1,
            verbose=self.verbose,
        )

        results: dict[str, ScrapeResult] = {}
        async with AsyncWebCrawler(config=browser_config) as crawler:
            for url in urls:
                try:
                    raw = await crawler.arun(url=url, config=run_config)
                    results[url] = self._interpret(url, raw, product, profile, price_pattern)
                except Exception as exc:  # noqa: BLE001 - one bad URL must not kill the batch
                    logger.warning("crawl4ai could not scrape {}: {}", url, exc)
                    results[url] = self._failed(url, str(exc))
        return results

    # -- crawl4ai import -----------------------------------------------------

    @staticmethod
    def _import_crawl4ai() -> tuple[Any, Any, Any, Any]:
        try:
            from crawl4ai import (
                AsyncWebCrawler,
                BrowserConfig,
                CacheMode,
                CrawlerRunConfig,
            )
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise Crawl4AINotInstalledError(
                "crawl4ai is required for scrape verification. Install it with "
                "`pdm add crawl4ai nest-asyncio` (or `pip install crawl4ai`) and "
                "then provision the browser with `crawl4ai-setup` "
                "(or `python -m playwright install --with-deps chromium`)."
            ) from exc
        return AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

    # -- result interpretation ----------------------------------------------

    def _interpret(
        self,
        url: str,
        raw: Any,
        product: ProductQuery,
        profile: MarketProfile,
        price_pattern: "re.Pattern[str]",
    ) -> ScrapeResult:
        raw = self._unwrap(raw)
        if raw is None:
            return self._failed(url, "empty crawl result")

        success = bool(getattr(raw, "success", False))
        status_code = self._coerce_int(getattr(raw, "status_code", None))
        final_url = str(getattr(raw, "url", "") or url)
        error = getattr(raw, "error_message", None) or None

        markdown_text = self._extract_markdown(raw)
        html = self._extract_html(raw)
        title = self._extract_title(raw, html)
        h1 = self._extract_h1(html)

        internal_links, external_links = self._extract_links(raw)
        image_count = self._extract_image_count(raw)

        # Structured data (JSON-LD) is the most authoritative identity + richness source.
        structured = self._extract_structured_product(html)
        structured_eans = tuple(structured.get("eans", ()))
        structured_name = structured.get("name", "")
        availability = structured.get("availability", "")
        page_product_name = structured_name or h1 or title

        verification_text = self._build_verification_text(
            page_product_name, title, h1, markdown_text, final_url
        )
        has_price = bool(structured.get("has_price")) or self._detect_price(
            markdown_text, html, price_pattern
        )

        # -- information richness (how much product data the page yields) -----
        brand = structured.get("brand", "")
        manufacturer = structured.get("manufacturer", "")
        description = (
            structured.get("description", "") or self._extract_meta_description(html)
        )[:RICHNESS_DESCRIPTION_MAX_CHARS]
        price = structured.get("price")
        currency = structured.get("currency", "")
        image_urls = tuple(structured.get("image_urls", ()))[:RICHNESS_MAX_IMAGE_URLS]
        specs = self._merge_specs(
            structured.get("specs", {}), self._extract_spec_table(html)
        )
        attributes = dict(structured.get("attributes", {}))

        word_count = len(markdown_text.split())
        markdown_chars = len(markdown_text)
        reachable = self._is_reachable(status_code, success)
        contains_ean = self._contains_ean(f"{markdown_text} {html}", product.ean)
        looks_home = self._looks_like_homepage(final_url)
        looks_product = self._looks_like_product_page(final_url, html, markdown_text, profile)
        is_soft_404 = self._detect_soft_404(
            title, h1, markdown_text, has_price, status_code, profile
        )
        overlap = self._text_overlap(
            product.main_text,
            " ".join([final_url, page_product_name, markdown_text[:5000]]),
        )

        richness_score = self._compute_richness_score(
            specs=specs,
            attributes=attributes,
            brand=brand,
            manufacturer=manufacturer,
            structured_eans=structured_eans,
            description=description,
            has_price=bool(has_price or price is not None),
            image_urls=image_urls,
            image_count=image_count,
            availability=availability,
            page_product_name=page_product_name,
        )

        has_content = (
            word_count >= self.min_word_count
            or markdown_chars >= self.min_word_count * 4
        )
        is_scrapable = bool(success and reachable and has_content and not is_soft_404)

        return ScrapeResult(
            url=url,
            scraped=True,
            success=success,
            reachable=reachable,
            is_scrapable=is_scrapable,
            status_code=status_code,
            final_url=final_url,
            title=title,
            h1=h1,
            page_product_name=page_product_name,
            structured_eans=structured_eans,
            has_price=has_price,
            availability=availability,
            price=price,
            currency=currency,
            brand=brand,
            manufacturer=manufacturer,
            description=description,
            specs=specs,
            image_urls=image_urls,
            attributes=attributes,
            richness_score=richness_score,
            markdown_excerpt=markdown_text[: self.markdown_excerpt_chars],
            markdown_chars=markdown_chars,
            word_count=word_count,
            internal_link_count=internal_links,
            external_link_count=external_links,
            image_count=image_count,
            looks_like_homepage=looks_home,
            looks_like_product_page=looks_product,
            is_soft_404=is_soft_404,
            contains_ean=contains_ean,
            text_overlap=round(overlap, 4),
            verification_text=verification_text,
            error=error if not is_scrapable else None,
        )

    @staticmethod
    def _unwrap(raw: Any) -> Any:
        # Some crawl4ai versions return a list / container for a single arun call.
        if isinstance(raw, list):
            return raw[0] if raw else None
        return raw

    def _extract_markdown(self, raw: Any) -> str:
        md = getattr(raw, "markdown", None)
        if md is None:
            return ""
        if isinstance(md, str):
            return md
        for attr in ("raw_markdown", "fit_markdown", "markdown"):
            value = getattr(md, attr, None)
            if value:
                return str(value)
        return str(md)

    def _extract_html(self, raw: Any) -> str:
        html = getattr(raw, "cleaned_html", None) or getattr(raw, "html", None) or ""
        return str(html)[:CRAWL_MAX_HTML_CHARS_FOR_VALIDATION]

    def _extract_title(self, raw: Any, html: str) -> str:
        metadata = getattr(raw, "metadata", None)
        if isinstance(metadata, dict):
            title = metadata.get("title")
            if title:
                return re.sub(r"\s+", " ", str(title)).strip()

        match = _TITLE_TAG_PATTERN.search(html or "")
        if match:
            return unescape(re.sub(r"\s+", " ", match.group(1)).strip())
        return ""

    def _extract_h1(self, html: str) -> str:
        match = _H1_TAG_PATTERN.search(html or "")
        if not match:
            return ""
        text = _TAG_STRIP_PATTERN.sub(" ", match.group(1))
        return unescape(re.sub(r"\s+", " ", text).strip())[:300]

    def _extract_structured_product(self, html: str) -> dict[str, Any]:
        """Parse JSON-LD product structured data for identity + richness signals."""
        result: dict[str, Any] = {
            "name": "",
            "eans": [],
            "has_price": False,
            "availability": "",
            "brand": "",
            "manufacturer": "",
            "description": "",
            "price": None,
            "currency": "",
            "image_urls": [],
            "specs": {},
            "attributes": {},
        }
        if not html:
            return result

        eans: list[str] = []
        images: list[str] = []
        for block in _JSONLD_PATTERN.findall(html):
            data = self._safe_json(block)
            if data is None:
                continue
            for node in self._iter_jsonld_products(data):
                if not isinstance(node, dict):
                    continue
                if not result["name"]:
                    name = node.get("name")
                    if isinstance(name, str) and name.strip():
                        result["name"] = re.sub(r"\s+", " ", name).strip()[:300]
                if not result["brand"]:
                    result["brand"] = self._jsonld_text(node.get("brand"))[:160]
                if not result["manufacturer"]:
                    result["manufacturer"] = self._jsonld_text(node.get("manufacturer"))[:160]
                if not result["description"]:
                    desc = node.get("description")
                    if isinstance(desc, str) and desc.strip():
                        result["description"] = re.sub(r"\s+", " ", desc).strip()
                self._collect_image_urls(node.get("image"), images)
                for key in JSONLD_EAN_KEYS:
                    value = node.get(key)
                    if value is None:
                        continue
                    digits = re.sub(r"\D", "", str(value))
                    if 8 <= len(digits) <= 14:
                        eans.append(digits)
                offers = node.get("offers")
                self._read_offers(offers, result)
                self._collect_structured_attributes(node, result)

        result["eans"] = list(dict.fromkeys(eans))
        result["image_urls"] = list(dict.fromkeys(images))
        return result

    @staticmethod
    def _safe_json(block: str) -> Any:
        text = (block or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return None

    def _iter_jsonld_products(self, data: Any):
        """Yield candidate product nodes from arbitrary JSON-LD structures."""
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                graph = node.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
                node_type = node.get("@type")
                types = node_type if isinstance(node_type, list) else [node_type]
                if any(isinstance(t, str) and "product" in t.lower() for t in types):
                    yield node
                else:
                    # Still inspect nested dicts/lists for embedded products.
                    for value in node.values():
                        if isinstance(value, (dict, list)):
                            stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)

    def _read_offers(self, offers: Any, result: dict[str, Any]) -> None:
        if isinstance(offers, list):
            for offer in offers:
                self._read_offers(offer, result)
            return
        if not isinstance(offers, dict):
            return
        price_value = offers.get("price")
        if price_value is None:
            price_value = offers.get("lowPrice")
        if price_value is not None:
            result["has_price"] = True
            if result.get("price") is None:
                parsed = self._coerce_price(price_value)
                if parsed is not None:
                    result["price"] = parsed
        currency = offers.get("priceCurrency")
        if isinstance(currency, str) and currency.strip() and not result.get("currency"):
            result["currency"] = currency.strip()[:8]
        spec = offers.get("priceSpecification")
        if isinstance(spec, dict):
            if result.get("price") is None:
                parsed = self._coerce_price(spec.get("price"))
                if parsed is not None:
                    result["price"] = parsed
                    result["has_price"] = True
            cur = spec.get("priceCurrency")
            if isinstance(cur, str) and cur.strip() and not result.get("currency"):
                result["currency"] = cur.strip()[:8]
        availability = offers.get("availability")
        if isinstance(availability, str) and availability and not result["availability"]:
            result["availability"] = availability.rsplit("/", 1)[-1]

    @staticmethod
    def _jsonld_text(value: Any) -> str:
        """Best-effort display string from a JSON-LD scalar / node / list."""
        if isinstance(value, str):
            return re.sub(r"\s+", " ", value).strip()
        if isinstance(value, dict):
            for key in ("name", "@value", "value", "legalName"):
                inner = value.get(key)
                if isinstance(inner, str) and inner.strip():
                    return re.sub(r"\s+", " ", inner).strip()
        if isinstance(value, list):
            for item in value:
                text = CrawlScraper._jsonld_text(item)
                if text:
                    return text
        return ""

    @staticmethod
    def _collect_image_urls(value: Any, into: list[str]) -> None:
        if isinstance(value, str):
            if value.strip():
                into.append(value.strip())
        elif isinstance(value, dict):
            url = value.get("url") or value.get("contentUrl")
            if isinstance(url, str) and url.strip():
                into.append(url.strip())
        elif isinstance(value, list):
            for item in value:
                CrawlScraper._collect_image_urls(item, into)

    def _collect_structured_attributes(self, node: dict, result: dict[str, Any]) -> None:
        """Map additionalProperty -> specs and other scalar props -> attributes."""
        specs: dict[str, str] = result["specs"]
        attributes: dict[str, Any] = result["attributes"]

        additional = node.get("additionalProperty")
        for prop in additional if isinstance(additional, list) else []:
            if not isinstance(prop, dict):
                continue
            key = prop.get("name") or prop.get("propertyID")
            val = prop.get("value")
            if isinstance(key, str) and key.strip() and val is not None:
                self._put_spec(specs, key, val)

        for key, val in node.items():
            if not isinstance(key, str) or key.lower() in JSONLD_ATTRIBUTE_SKIP_KEYS:
                continue
            if isinstance(val, (str, int, float, bool)) and str(val).strip():
                if len(attributes) >= RICHNESS_MAX_SPEC_ROWS:
                    break
                attributes.setdefault(key, str(val)[:RICHNESS_MAX_SPEC_VALUE_CHARS])

    @staticmethod
    def _put_spec(specs: dict[str, str], key: Any, value: Any) -> None:
        if len(specs) >= RICHNESS_MAX_SPEC_ROWS:
            return
        clean_key = re.sub(r"\s+", " ", str(key)).strip()[:RICHNESS_MAX_SPEC_KEY_CHARS]
        clean_val = re.sub(r"\s+", " ", str(value)).strip()[:RICHNESS_MAX_SPEC_VALUE_CHARS]
        if clean_key and clean_val:
            specs.setdefault(clean_key, clean_val)

    @staticmethod
    def _merge_specs(primary: dict[str, str], secondary: dict[str, str]) -> dict[str, str]:
        merged = dict(primary)
        for key, val in secondary.items():
            if len(merged) >= RICHNESS_MAX_SPEC_ROWS:
                break
            merged.setdefault(key, val)
        return merged

    @staticmethod
    def _coerce_price(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = re.sub(r"[^\d.,]", "", str(value).strip())
        if not cleaned:
            return None
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".") if re.search(r",\d{1,2}$", cleaned) else cleaned.replace(",", "")
        try:
            return round(float(cleaned), 2)
        except ValueError:
            return None

    def _extract_spec_table(self, html: str) -> dict[str, str]:
        """Heuristically parse spec tables and definition lists into key->value."""
        specs: dict[str, str] = {}
        if not html:
            return specs
        for row in _TABLE_ROW_PATTERN.findall(html):
            cells = _TABLE_CELL_PATTERN.findall(row)
            if not 2 <= len(cells) <= RICHNESS_SPEC_TABLE_MAX_CELLS:
                continue
            key = self._strip_html(cells[0])
            value = self._strip_html(cells[1])
            if key and value and key.lower() != value.lower():
                self._put_spec(specs, key, value)
            if len(specs) >= RICHNESS_MAX_SPEC_ROWS:
                return specs
        for key_html, value_html in _DL_PAIR_PATTERN.findall(html):
            key = self._strip_html(key_html)
            value = self._strip_html(value_html)
            if key and value:
                self._put_spec(specs, key, value)
            if len(specs) >= RICHNESS_MAX_SPEC_ROWS:
                break
        return specs

    @staticmethod
    def _strip_html(fragment: str) -> str:
        text = _TAG_STRIP_PATTERN.sub(" ", fragment or "")
        return unescape(re.sub(r"\s+", " ", text).strip())

    @staticmethod
    def _extract_meta_description(html: str) -> str:
        if not html:
            return ""
        match = _META_DESCRIPTION_PATTERN.search(html)
        if not match:
            return ""
        return unescape(re.sub(r"\s+", " ", match.group(1)).strip())

    @staticmethod
    def _compute_richness_score(
        *,
        specs: dict[str, str],
        attributes: dict[str, Any],
        brand: str,
        manufacturer: str,
        structured_eans: tuple[str, ...],
        description: str,
        has_price: bool,
        image_urls: tuple[str, ...],
        image_count: int,
        availability: str,
        page_product_name: str,
    ) -> float:
        spec_total = len(specs) + len(attributes)
        image_total = len(image_urls) or min(image_count, RICHNESS_IMAGES_FULL_CREDIT_COUNT)
        credits = {
            "specs": min(1.0, spec_total / RICHNESS_SPECS_FULL_CREDIT_COUNT),
            "brand": 1.0 if brand else 0.0,
            "manufacturer": 1.0 if manufacturer else 0.0,
            "structured_ean": 1.0 if structured_eans else 0.0,
            "description": min(1.0, len(description) / RICHNESS_DESCRIPTION_FULL_CREDIT_CHARS),
            "price": 1.0 if has_price else 0.0,
            "images": min(1.0, image_total / RICHNESS_IMAGES_FULL_CREDIT_COUNT),
            "availability": 1.0 if availability else 0.0,
            "product_name": 1.0 if page_product_name else 0.0,
        }
        score = sum(
            RICHNESS_FIELD_WEIGHTS.get(field, 0.0) * credit
            for field, credit in credits.items()
        )
        return round(score, RICHNESS_SCORE_ROUND_DIGITS)

    def _build_verification_text(
        self, name: str, title: str, h1: str, markdown_text: str, url: str
    ) -> str:
        parts = [name, title, h1, url, markdown_text]
        text = " \n".join(part for part in parts if part)
        return text[:VERIFICATION_TEXT_MAX_CHARS]

    @staticmethod
    def _detect_price(markdown_text: str, html: str, pattern: "re.Pattern[str]") -> bool:
        sample = f"{markdown_text[:8000]} {html[:8000]}"
        return bool(pattern.search(sample))

    @staticmethod
    def _detect_soft_404(
        title: str,
        h1: str,
        markdown_text: str,
        has_price: bool,
        status_code: Optional[int],
        profile: MarketProfile,
    ) -> bool:
        heading = f"{title} {h1}".lower()
        if any(phrase in heading for phrase in profile.soft_404_title_phrases):
            return True

        body = markdown_text[:6000].lower()
        phrase_hits = sum(1 for phrase in profile.soft_404_phrases if phrase in body)
        if phrase_hits >= 1 and not has_price:
            return True
        # Multiple explicit not-found phrases is conclusive even with stray price-like text.
        return phrase_hits >= 2

    @staticmethod
    def _extract_links(raw: Any) -> tuple[int, int]:
        links = getattr(raw, "links", None) or {}
        if not isinstance(links, dict):
            return 0, 0
        internal = links.get("internal") or []
        external = links.get("external") or []
        return len(internal), len(external)

    @staticmethod
    def _extract_image_count(raw: Any) -> int:
        media = getattr(raw, "media", None) or {}
        if not isinstance(media, dict):
            return 0
        return len(media.get("images") or [])

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_reachable(status_code: Optional[int], success: bool) -> bool:
        if status_code is None:
            return success
        if HTTP_OK_STATUS_MIN <= status_code < HTTP_OK_STATUS_MAX_EXCLUSIVE:
            return True
        return status_code in SOFT_BLOCK_HTTP_STATUSES

    @staticmethod
    def _contains_ean(text: str, ean: Optional[str]) -> bool:
        if not ean:
            return False
        target = re.sub(r"\D", "", ean)
        if not target:
            return False
        haystack = re.sub(r"\D", "", text or "")
        return target in haystack

    @staticmethod
    def _looks_like_homepage(url: str) -> bool:
        parsed = urlparse(url)
        return not parsed.path.strip("/")

    @staticmethod
    def _looks_like_product_page(
        url: str, html: str, markdown_text: str, profile: MarketProfile
    ) -> bool:
        parsed = urlparse(url)
        full = f"{parsed.path.lower()}?{parsed.query.lower()}"

        if any(term in full for term in NON_PRODUCT_PATH_KEYWORDS):
            return False
        if any(term in full for term in PRODUCT_PATH_KEYWORDS):
            return True

        lowered = f"{html} {markdown_text}".lower()
        if (
            "schema.org/product" in lowered
            or '"@type":"product"' in lowered
            or '"@type": "product"' in lowered
            or 'property="og:type" content="product"' in lowered
        ):
            return True
        return any(phrase in lowered for phrase in profile.add_to_cart_phrases)

    def _text_overlap(self, main_text: str, evidence_text: str) -> float:
        tokens = {
            token.lower()
            for token in _TOKEN_PATTERN.findall(main_text or "")
            if len(token) >= MIN_TOKEN_LENGTH_FOR_TEXT_MATCH
        }
        if not tokens:
            return 0.0
        evidence = (evidence_text or "").lower()
        matches = sum(1 for token in tokens if token in evidence)
        return matches / max(len(tokens), 1)

    # -- non-scraped / failed results ---------------------------------------

    @staticmethod
    def _failed(url: str, error: str) -> ScrapeResult:
        return ScrapeResult(
            url=url,
            scraped=True,
            success=False,
            reachable=False,
            is_scrapable=False,
            status_code=None,
            final_url=None,
            error=error,
        )

    @staticmethod
    def _not_scraped(url: str, error: str) -> ScrapeResult:
        return ScrapeResult(
            url=url,
            scraped=False,
            success=False,
            reachable=False,
            is_scrapable=False,
            status_code=None,
            final_url=None,
            error=error,
        )

    @staticmethod
    def _dedupe(urls: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                ordered.append(url)
        return ordered
