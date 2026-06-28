from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from loguru import logger

from src.product_evidence_harness.constants import (
    ADD_TO_CART_PHRASES,
    EAN_REGEX,
    LISTING_URL_HINTS,
    PRODUCT_URL_HINTS,
    RICHNESS_FIELD_WEIGHTS,
    SOFT_404_PHRASES,
)
from src.product_evidence_harness.contracts import ProductQuery, ScrapeResult
from src.product_evidence_harness.url_utils import normalize_url


@dataclass
class CrawlScraper:
    headless: bool = True
    verbose: bool = False
    page_timeout_ms: int = 45000
    min_word_count: int = 20

    def scrape(self, url: str, *, product: Optional[ProductQuery] = None) -> ScrapeResult:
        if not url:
            return self._failed(url, "empty url")
        logger.info("Scraping URL | url={}", url)
        try:
            return self._scrape_with_crawl4ai(url, product=product)
        except Exception as exc:
            logger.warning("crawl4ai failed; falling back to requests | url={} | error={}", url, exc)
            try:
                return self._scrape_with_requests(url, product=product, prior_error=str(exc))
            except Exception as exc2:
                return self._failed(url, f"crawl4ai_error={exc}; requests_error={exc2}")

    def _scrape_with_crawl4ai(self, url: str, *, product: Optional[ProductQuery]) -> ScrapeResult:
        import nest_asyncio
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

        nest_asyncio.apply()

        async def _run() -> Any:
            browser_config = BrowserConfig(headless=self.headless, verbose=self.verbose)
            run_config = CrawlerRunConfig(page_timeout=self.page_timeout_ms)
            async with AsyncWebCrawler(config=browser_config) as crawler:
                return await crawler.arun(url=url, config=run_config)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run())
        markdown = getattr(result, "markdown", "") or ""
        html = getattr(result, "html", "") or ""
        status_code = getattr(result, "status_code", None)
        final_url = getattr(result, "url", None) or url
        success = bool(getattr(result, "success", False))
        return self._build_result(
            url=url,
            final_url=final_url,
            status_code=status_code,
            success=success,
            markdown=markdown,
            html=html,
            product=product,
            error=getattr(result, "error_message", None),
        )

    def _scrape_with_requests(self, url: str, *, product: Optional[ProductQuery], prior_error: str | None = None) -> ScrapeResult:
        response = requests.get(url, timeout=max(10, self.page_timeout_ms / 1000), headers={"User-Agent": "Mozilla/5.0 ProductEvidenceHarness/0.2"})
        html = response.text or ""
        text = self._html_to_text(html)
        result = self._build_result(
            url=url,
            final_url=response.url,
            status_code=response.status_code,
            success=response.ok,
            markdown=text,
            html=html,
            product=product,
            error=prior_error,
        )
        return result

    def _build_result(self, *, url: str, final_url: str | None, status_code: int | None, success: bool, markdown: str, html: str, product: Optional[ProductQuery], error: str | None = None) -> ScrapeResult:
        text = " ".join([markdown or "", self._html_to_text(html)[:5000]])
        word_count = len(re.findall(r"\w+", text))
        title = self._extract_title(html) or self._first_heading(markdown)
        h1 = self._extract_h1(html) or self._first_heading(markdown)
        jsonld = self._extract_jsonld(html)
        page_name = self._first_nonempty(
            self._jsonld_value(jsonld, "name"),
            self._meta(html, "og:title"),
            h1,
            title,
        )
        description = self._first_nonempty(
            self._jsonld_value(jsonld, "description"),
            self._meta(html, "description"),
            self._meta(html, "og:description"),
            self._paragraph_excerpt(markdown),
        )[:1000]
        brand = self._jsonld_nested_name(jsonld, "brand") or self._meta(html, "product:brand")
        manufacturer = self._jsonld_nested_name(jsonld, "manufacturer")
        specs = self._extract_specs(html, text)
        attributes = self._extract_label_values(html, text)
        gtin_evidence = [
            *self._jsonld_ean_evidence(jsonld),
            *self._gtin_evidence_from_mapping(specs, source_prefix="spec"),
            *self._gtin_evidence_from_mapping(attributes, source_prefix="attribute"),
            *self._gtin_evidence_from_labeled_text(text),
        ]
        eans = tuple(dict.fromkeys([e["value"] for e in gtin_evidence if e.get("value")]))
        if gtin_evidence:
            attributes = dict(attributes)
            attributes["gtin_evidence_json"] = json.dumps(gtin_evidence, ensure_ascii=False)[:2000]
        price, currency = self._extract_price(jsonld, html, text)
        availability = self._extract_availability(jsonld, html, text)
        image_urls = tuple(dict.fromkeys(self._extract_images(jsonld, html, base_url=final_url or url)))
        links = tuple(dict.fromkeys(self._extract_links(html, base_url=final_url or url)))
        is_soft_404 = self._looks_soft_404(text, title, status_code)
        looks_product = self._looks_product_page(final_url or url, text, jsonld)
        markdown_chars = len(markdown or "")
        contains_ean = bool(product and product.ean and product.ean in re.sub(r"\D", "", text))
        text_overlap = self._token_overlap(product.main_text if product else "", " ".join([page_name, title, h1, text[:3000]]))
        richness = self._compute_richness_score(
            specs=specs, attributes=attributes, brand=brand, manufacturer=manufacturer,
            structured_eans=eans, description=description, has_price=price is not None,
            image_urls=image_urls, image_count=len(image_urls), availability=availability,
            page_product_name=page_name,
        )
        reachable = status_code is None or 200 <= int(status_code) < 400
        is_scrapable = bool(success and reachable and not is_soft_404 and word_count >= self.min_word_count)
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
            page_product_name=page_name,
            structured_eans=eans,
            has_price=price is not None,
            price=price,
            currency=currency,
            brand=brand,
            manufacturer=manufacturer,
            description=description,
            specs=specs,
            attributes=attributes,
            availability=availability,
            image_urls=image_urls,
            richness_score=richness,
            markdown_excerpt=(markdown or text)[:2000],
            markdown_chars=markdown_chars,
            word_count=word_count,
            internal_link_count=sum(1 for link in links if urlparse(link).netloc == urlparse(final_url or url).netloc),
            external_link_count=sum(1 for link in links if urlparse(link).netloc != urlparse(final_url or url).netloc),
            image_count=len(image_urls),
            looks_like_homepage=self._looks_homepage(final_url or url),
            looks_like_product_page=looks_product,
            is_soft_404=is_soft_404,
            contains_ean=contains_ean,
            text_overlap=text_overlap,
            links=links,
            verification_text=text[:20000],
            error=error,
        )

    def _failed(self, url: str, error: str) -> ScrapeResult:
        return ScrapeResult(
            url=url,
            scraped=True,
            success=False,
            reachable=False,
            is_scrapable=False,
            status_code=None,
            final_url=url,
            error=error,
        )

    @staticmethod
    def _compute_richness_score(*, specs: dict[str, str], attributes: dict[str, Any], brand: str, manufacturer: str, structured_eans: tuple[str, ...], description: str, has_price: bool, image_urls: tuple[str, ...], image_count: int, availability: str, page_product_name: str) -> float:
        weights = RICHNESS_FIELD_WEIGHTS
        score = 0.0
        score += weights["specs"] * min(1.0, (len(specs or {}) + len(attributes or {})) / 6)
        score += weights["brand"] * bool(brand)
        score += weights["manufacturer"] * bool(manufacturer)
        score += weights["structured_eans"] * bool(structured_eans)
        score += weights["description"] * min(1.0, len(description or "") / 180)
        score += weights["price"] * bool(has_price)
        score += weights["images"] * min(1.0, max(image_count, len(image_urls or ())) / 3)
        score += weights["availability"] * bool(availability)
        score += weights["product_name"] * bool(page_product_name)
        return round(min(1.0, score), 4)

    def _extract_jsonld(self, html: str) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html or "", flags=re.I | re.S):
            try:
                payload = json.loads(unescape(raw.strip()))
                if isinstance(payload, dict):
                    blocks.append(payload)
                elif isinstance(payload, list):
                    blocks.extend([x for x in payload if isinstance(x, dict)])
            except Exception:
                continue
        return blocks

    def _jsonld_product_blocks(self, jsonld: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for item in jsonld:
            typ = item.get("@type") or item.get("type")
            if isinstance(typ, list):
                typ_text = " ".join(map(str, typ)).lower()
            else:
                typ_text = str(typ or "").lower()
            if "product" in typ_text:
                out.append(item)
            graph = item.get("@graph")
            if isinstance(graph, list):
                out.extend(self._jsonld_product_blocks([x for x in graph if isinstance(x, dict)]))
        return out or jsonld[:1]

    def _jsonld_value(self, jsonld: list[dict[str, Any]], key: str) -> str:
        for item in self._jsonld_product_blocks(jsonld):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _jsonld_nested_name(self, jsonld: list[dict[str, Any]], key: str) -> str:
        for item in self._jsonld_product_blocks(jsonld):
            value = item.get(key)
            if isinstance(value, dict):
                name = value.get("name")
                if name:
                    return str(name).strip()
            elif isinstance(value, str):
                return value.strip()
        return ""

    def _jsonld_ean_evidence(self, jsonld: list[dict[str, Any]]) -> list[dict[str, str]]:
        keys = ["gtin", "gtin8", "gtin12", "gtin13", "gtin14", "ean", "upc"]
        vals: list[dict[str, str]] = []
        for item in self._jsonld_product_blocks(jsonld):
            for key in keys:
                value = item.get(key)
                if value:
                    for gtin in re.findall(EAN_REGEX, str(value)):
                        vals.append({"value": gtin, "source": f"jsonld.{key}"})
        return vals

    def _extract_price(self, jsonld: list[dict[str, Any]], html: str, text: str) -> tuple[Optional[float], str]:
        for item in self._jsonld_product_blocks(jsonld):
            offers = item.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict):
                raw = offers.get("price")
                currency = str(offers.get("priceCurrency") or "")
                try:
                    return float(str(raw).replace(",", ".")), currency
                except Exception:
                    pass
        match = re.search(r"(€|\$|£|Kč|CZK|EUR|USD|COP)\s*([0-9][0-9\s.,]*)|([0-9][0-9\s.,]*)\s*(€|\$|£|Kč|CZK|EUR|USD|COP)", text or "", flags=re.I)
        if not match:
            return None, ""
        currency = match.group(1) or match.group(4) or ""
        amount = match.group(2) or match.group(3) or ""
        try:
            return float(amount.replace(" ", "").replace(",", ".")), currency
        except Exception:
            return None, currency


    def _extract_specs(self, html: str, text: str) -> dict[str, str]:
        specs: dict[str, str] = {}
        # HTML tables: <tr><th/td>Label</th><td>Value</td></tr>
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", flags=re.I | re.S):
            cells = re.findall(r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>", row, flags=re.I | re.S)
            if len(cells) >= 2:
                key = self._clean_cell(cells[0])
                val = self._clean_cell(" ".join(cells[1:]))
                if self._valid_kv(key, val):
                    specs.setdefault(key[:80], val[:250])
            if len(specs) >= 40:
                break
        # Definition lists: <dt>Label</dt><dd>Value</dd>
        for key, val in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html or "", flags=re.I | re.S):
            k = self._clean_cell(key); v = self._clean_cell(val)
            if self._valid_kv(k, v):
                specs.setdefault(k[:80], v[:250])
        # Visible label-value fallbacks.
        for key, val in re.findall(r"(?im)^\s*([A-Za-zÀ-ž0-9 /_.-]{2,40})\s*[:：]\s*([^\n]{2,160})$", text or ""):
            k = self._clean_cell(key); v = self._clean_cell(val)
            if self._valid_kv(k, v):
                specs.setdefault(k[:80], v[:250])
            if len(specs) >= 60:
                break
        return specs

    def _extract_label_values(self, html: str, text: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        # itemprop often exposes product attributes.
        for prop, value in re.findall(r"itemprop=[\"']([^\"']+)[\"'][^>]*(?:content=[\"']([^\"']+)[\"'])?", html or "", flags=re.I | re.S):
            if value and self._valid_kv(prop, value):
                attrs.setdefault(prop[:80], unescape(value.strip())[:250])
        for key, val in re.findall(r"data-(?:test|qa|spec|attribute|name)=[\"']([^\"']+)[\"'][^>]*>([^<]{2,160})<", html or "", flags=re.I | re.S):
            k = self._clean_cell(key); v = self._clean_cell(val)
            if self._valid_kv(k, v):
                attrs.setdefault(k[:80], v[:250])
        return attrs

    def _clean_cell(self, raw: str) -> str:
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw or "", flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return unescape(re.sub(r"\s+", " ", text)).strip(" :-–—\t\r\n")

    def _valid_kv(self, key: str, val: str) -> bool:
        if not key or not val or key == val:
            return False
        if len(key) > 80 or len(val) > 400:
            return False
        bad = {"home", "search", "menu", "login", "privacy", "newsletter"}
        return key.lower() not in bad

    def _gtin_evidence_from_mapping(self, mapping: dict[str, str], *, source_prefix: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for k, v in (mapping or {}).items():
            if re.search(r"gtin|ean|upc|barcode|čárový|kod|kód|artikelnummer", k or "", flags=re.I):
                for gtin in re.findall(EAN_REGEX, str(v)):
                    out.append({"value": gtin, "source": f"{source_prefix}.{k}"[:120]})
        return out

    def _gtin_evidence_from_labeled_text(self, text: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        # Only use visible GTIN-like numbers when they are near a product identifier label.
        for m in re.finditer(r"(?i)(gtin|ean|upc|barcode|bar code|artikelnummer|čárový\s*kód|kód)\s*[:#-]?\s*([0-9][0-9\s-]{7,20})", text or ""):
            label = m.group(1)
            for gtin in re.findall(EAN_REGEX, m.group(2)):
                out.append({"value": gtin, "source": f"visible_labeled.{label}"})
        return out

    def _extract_availability(self, jsonld: list[dict[str, Any]], html: str, text: str) -> str:
        for item in self._jsonld_product_blocks(jsonld):
            offers = item.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict):
                av = offers.get("availability") or offers.get("itemCondition")
                if av:
                    return str(av).rsplit("/", 1)[-1][:80]
        folded = (text or "").lower()[:4000]
        if any(x in folded for x in ["in stock", "available", "skladem", "auf lager", "disponible"]):
            return "IN_STOCK_SIGNAL"
        if any(x in folded for x in ["out of stock", "sold out", "vyprodano", "nicht verfügbar", "no disponible"]):
            return "OUT_OF_STOCK_SIGNAL"
        return ""

    def _extract_images(self, jsonld: list[dict[str, Any]], html: str, *, base_url: str) -> list[str]:
        images: list[str] = []
        for item in self._jsonld_product_blocks(jsonld):
            value = item.get("image")
            if isinstance(value, str):
                images.append(value)
            elif isinstance(value, list):
                images.extend([str(x) for x in value if isinstance(x, str)])
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html or "", flags=re.I):
            images.append(m.group(1))
        return [u for u in (normalize_url(urljoin(base_url, x)) for x in images) if u][:10]

    def _extract_links(self, html: str, *, base_url: str) -> list[str]:
        links = []
        for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\']', html or "", flags=re.I):
            url = normalize_url(urljoin(base_url, m.group(1)))
            if url:
                links.append(url)
        return links[:200]

    def _extract_title(self, html: str) -> str:
        m = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.I | re.S)
        return unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else ""

    def _extract_h1(self, html: str) -> str:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html or "", flags=re.I | re.S)
        return unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip()) if m else ""

    def _meta(self, html: str, name: str) -> str:
        patterns = [
            rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{re.escape(name)}["\']',
        ]
        for p in patterns:
            m = re.search(p, html or "", flags=re.I | re.S)
            if m:
                return unescape(m.group(1).strip())
        return ""

    def _html_to_text(self, html: str) -> str:
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html or "", flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        return unescape(re.sub(r"\s+", " ", text)).strip()

    def _first_heading(self, markdown: str) -> str:
        for line in (markdown or "").splitlines():
            clean = line.strip("# *\t ")
            if len(clean) > 3:
                return clean[:200]
        return ""

    def _paragraph_excerpt(self, markdown: str) -> str:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", markdown or "") if len(p.strip()) > 80]
        return paragraphs[0] if paragraphs else (markdown or "")[:500]

    def _looks_soft_404(self, text: str, title: str, status_code: int | None) -> bool:
        if status_code == 404:
            return True
        folded = f"{title} {text[:2000]}".lower()
        return any(phrase in folded for phrase in SOFT_404_PHRASES)

    def _looks_product_page(self, url: str, text: str, jsonld: list[dict[str, Any]]) -> bool:
        lower_url = (url or "").lower()
        if any(hint in lower_url for hint in LISTING_URL_HINTS):
            return False
        if any("product" in str(item.get("@type", "")).lower() for item in self._jsonld_product_blocks(jsonld)):
            return True
        folded = (text or "").lower()
        if any(phrase in folded for phrase in ADD_TO_CART_PHRASES):
            return True
        return any(hint in lower_url for hint in PRODUCT_URL_HINTS)

    def _looks_homepage(self, url: str) -> bool:
        parsed = urlparse(url or "")
        return parsed.path in {"", "/"}

    def _token_overlap(self, query: str, evidence: str) -> float:
        if not query or not evidence:
            return 0.0
        q = {t.lower() for t in re.findall(r"[a-zA-Z0-9À-ž]+", query) if len(t) >= 3}
        e = (evidence or "").lower()
        if not q:
            return 0.0
        return round(sum(1 for t in q if t in e) / len(q), 4)

    def _first_nonempty(self, *values: str) -> str:
        for value in values:
            if value and str(value).strip():
                return str(value).strip()
        return ""
