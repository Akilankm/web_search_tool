from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from product_url_v2.config import AcquisitionConfig
from product_url_v2.models import GateStatus, PageEvidence, SearchResult
from product_url_v2.search import canonical_url
from product_url_v2.trace import page_evidence_summary

AcquisitionProgress = Callable[[str, Mapping[str, Any]], None]


@dataclass(slots=True)
class PageAcquirer:
    config: AcquisitionConfig
    timeout_seconds: int = 30
    session: requests.Session | None = None

    def acquire_many(
        self,
        candidates: Sequence[SearchResult],
        progress: AcquisitionProgress | None = None,
    ) -> dict[str, PageEvidence]:
        selected = self._select(candidates)
        if progress:
            progress(
                "ACQUISITION_PLAN",
                {
                    "submitted_candidate_count": len(candidates),
                    "selected_candidate_count": len(selected),
                    "max_candidates": self.config.max_candidates,
                    "max_per_domain": self.config.max_per_domain,
                    "max_workers": self.config.max_workers,
                    "selected_urls": [item.url for item in selected],
                },
            )
        output: dict[str, PageEvidence] = {}
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as pool:
            futures = {pool.submit(self.acquire, item.url): item.url for item in selected}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    evidence = future.result()
                except Exception as exc:
                    evidence = PageEvidence(
                        requested_url=url,
                        final_url=url,
                        status_code=None,
                        content_type="",
                        title="",
                        description="",
                        visible_text="",
                        jsonld_products=(),
                        metadata={},
                        links=(),
                        images=(),
                        fetch_status=GateStatus.FAIL,
                        fetch_error=f"{type(exc).__name__}: {exc}",
                    )
                output[url] = evidence
                if progress:
                    progress("PAGE_FETCHED", page_evidence_summary(evidence))
        return output

    def acquire(self, url: str) -> PageEvidence:
        started = time.perf_counter()
        session = self.session or requests.Session()
        response = session.get(
            url,
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5",
            },
            allow_redirects=True,
            stream=True,
        )
        content = _bounded_content(response, self.config.max_response_bytes)
        elapsed = int((time.perf_counter() - started) * 1000)
        content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        final_url = canonical_url(response.url) or url
        if response.status_code >= 400:
            return PageEvidence(
                url,
                final_url,
                response.status_code,
                content_type,
                "",
                "",
                "",
                (),
                {},
                (),
                (),
                GateStatus.FAIL,
                f"HTTP {response.status_code}",
                elapsed,
            )
        if content_type == "application/json":
            text = content.decode(response.encoding or "utf-8", errors="replace")
            return PageEvidence(
                url,
                final_url,
                response.status_code,
                content_type,
                "",
                "",
                text[:100000],
                (),
                {},
                (),
                (),
                GateStatus.PASS,
                elapsed_ms=elapsed,
            )
        if "html" not in content_type and not content.lstrip().startswith(b"<"):
            return PageEvidence(
                url,
                final_url,
                response.status_code,
                content_type,
                "",
                "",
                "",
                (),
                {},
                (),
                (),
                GateStatus.FAIL,
                "response is not HTML",
                elapsed,
            )
        return parse_html_evidence(url, final_url, response.status_code, content_type, content, elapsed)

    def _select(self, candidates: Sequence[SearchResult]) -> tuple[SearchResult, ...]:
        per_domain: dict[str, int] = {}
        selected: list[SearchResult] = []
        for item in sorted(candidates, key=lambda value: (value.position or 9999, value.url)):
            domain = (urlparse(item.url).hostname or "").lower().removeprefix("www.")
            if per_domain.get(domain, 0) >= self.config.max_per_domain:
                continue
            selected.append(item)
            per_domain[domain] = per_domain.get(domain, 0) + 1
            if len(selected) >= self.config.max_candidates:
                break
        return tuple(selected)


def parse_html_evidence(
    requested_url: str,
    final_url: str,
    status_code: int,
    content_type: str,
    content: bytes,
    elapsed_ms: int = 0,
) -> PageEvidence:
    soup = BeautifulSoup(content, "html.parser")
    for node in soup(["script", "style", "noscript", "template", "svg"]):
        if node.name != "script" or node.get("type") != "application/ld+json":
            node.decompose()
    title = " ".join((soup.title.get_text(" ", strip=True) if soup.title else "").split())
    metadata = _metadata(soup)
    description = metadata.get("description") or metadata.get("og:description") or ""
    visible_text = " ".join(soup.get_text(" ", strip=True).split())[:200000]
    products = tuple(_jsonld_products(soup))
    links = tuple(
        dict.fromkeys(
            canonical_url(urljoin(final_url, item.get("href")))
            for item in soup.find_all("a", href=True)
            if canonical_url(urljoin(final_url, item.get("href")))
        )
    )[:500]
    images = tuple(dict.fromkeys(urljoin(final_url, item.get("src")) for item in soup.find_all("img", src=True)))[:100]
    return PageEvidence(
        requested_url=requested_url,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        title=title,
        description=description,
        visible_text=visible_text,
        jsonld_products=products,
        metadata=metadata,
        links=links,
        images=images,
        fetch_status=GateStatus.PASS,
        elapsed_ms=elapsed_ms,
    )


def product_fields(evidence: PageEvidence) -> dict[str, str]:
    output: dict[str, str] = {}
    for product in evidence.jsonld_products:
        _set(output, "product_name", product.get("name"))
        brand = product.get("brand")
        if isinstance(brand, Mapping):
            brand = brand.get("name")
        _set(output, "brand", brand)
        for key in ("sku", "mpn", "gtin", "gtin8", "gtin12", "gtin13", "gtin14", "model", "color", "size"):
            _set(output, key, product.get(key))
        offers = product.get("offers")
        if isinstance(offers, Mapping):
            _set(output, "price", offers.get("price"))
            _set(output, "currency", offers.get("priceCurrency"))
            _set(output, "availability", offers.get("availability"))
    _set(output, "product_name", evidence.metadata.get("og:title") or evidence.title)
    _set(output, "brand", evidence.metadata.get("product:brand"))
    _set(output, "price", evidence.metadata.get("product:price:amount"))
    _set(output, "currency", evidence.metadata.get("product:price:currency"))
    return output


def _metadata(soup: BeautifulSoup) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in soup.find_all("meta"):
        key = item.get("property") or item.get("name") or item.get("itemprop")
        value = item.get("content")
        if key and value:
            output[str(key).strip().lower()] = " ".join(str(value).split())
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    if canonical and canonical.get("href"):
        output["canonical"] = str(canonical.get("href"))
    return output


def _jsonld_products(soup: BeautifulSoup) -> Iterable[dict[str, Any]]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        yield from _walk_products(payload)


def _walk_products(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, Mapping):
        kind = value.get("@type")
        kinds = {str(item).casefold() for item in kind} if isinstance(kind, list) else {str(kind).casefold()}
        if "product" in kinds:
            yield dict(value)
        for key, nested in value.items():
            if key != "@context":
                yield from _walk_products(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_products(item)


def _bounded_content(response: requests.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        remaining = limit - total
        if remaining <= 0:
            break
        chunks.append(chunk[:remaining])
        total += len(chunks[-1])
    return b"".join(chunks)


def _set(output: dict[str, str], key: str, value: Any) -> None:
    if key in output or value in (None, "", [], {}):
        return
    text = " ".join(str(value).split())
    if text:
        output[key] = text
