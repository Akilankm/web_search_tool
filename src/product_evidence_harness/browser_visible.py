from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha1
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger

from src.product_evidence_harness.contracts import CandidateScorecard, ProductQuery
from src.product_evidence_harness.llm.service import LLMService, get_llm_service
from src.product_evidence_harness.url_utils import normalize_url


BAD_PAGE_STATUSES = {
    "consent_wall": "BROWSER_OPENABLE_BUT_CONSENT_WALL",
    "login_wall": "BROWSER_OPENABLE_BUT_LOGIN_WALL",
    "access_blocked": "BROWSER_OPENABLE_BUT_ACCESS_BLOCKED",
    "homepage": "BROWSER_OPENABLE_BUT_REROUTED",
    "category_page": "BROWSER_OPENABLE_BUT_CATEGORY_PAGE",
    "search_results": "BROWSER_OPENABLE_BUT_SEARCH_RESULTS_PAGE",
    "not_product_page": "BROWSER_OPENABLE_BUT_NOT_PRODUCT_PAGE",
}


@dataclass(frozen=True)
class BrowserVisibleVerifierConfig:
    """Configuration for the user-visible product-content gate."""

    enabled: bool = True
    capture_enabled: bool = True
    llm_enabled: bool = False
    top_k: int = 5
    timeout_ms: int = 45000
    wait_ms: int = 1500
    min_token_overlap: float = 0.35
    min_title_overlap: float = 0.45
    min_llm_confidence: float = 0.70
    image_detail: str = "high"


@dataclass(frozen=True)
class BrowserVisibleProductVerdict:
    """Verdict for the content a normal user actually sees in a browser.

    This is intentionally different from URL reachability. A page can be browser
    openable while showing a homepage, consent wall, search page, access block,
    or a different product. Such pages must not survive as production champions.
    """

    url: str
    final_url: str
    status: str
    browser_visible_page_type: str
    user_visible_product_match: bool
    champion_should_survive_visible_check: bool
    user_visible_content_confidence: float
    product_content_visible: bool
    rerouted_or_not: bool
    reroute_type: str = "NONE"
    visible_title_match: bool = False
    visible_brand_match: bool = False
    visible_quantity_match: bool = False
    visible_product_page_confidence: float = 0.0
    screenshot_path: str = ""
    visible_text_excerpt_path: str = ""
    resolved_url_path: str = ""
    capture_status: str = "NOT_ATTEMPTED"
    llm_used: bool = False
    llm_status: str = "NOT_USED"
    llm_raw_response: str = ""
    evidence: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def failed(cls, url: str, *, status: str, reason: str, final_url: str | None = None) -> "BrowserVisibleProductVerdict":
        return cls(
            url=url,
            final_url=final_url or url,
            status=status,
            browser_visible_page_type="unknown",
            user_visible_product_match=False,
            champion_should_survive_visible_check=False,
            user_visible_content_confidence=0.0,
            product_content_visible=False,
            rerouted_or_not=bool(final_url and normalize_url(final_url) != normalize_url(url)),
            capture_status="FAILED",
            reasons=(reason,),
            error=reason,
        )


@dataclass
class BrowserVisibleContentVerifier:
    """Verify that the browser-visible page content matches the intended product.

    The verifier uses multiple signals:
    - real browser screenshot and visible text when Playwright is available;
    - final resolved URL / reroute detection;
    - page title, body text, scrape metadata, product-page classifiers;
    - optional vision/text LLM adjudication over screenshot + visible text.
    """

    config: BrowserVisibleVerifierConfig = BrowserVisibleVerifierConfig()
    llm_service: LLMService | None = None

    def verify_card(
        self,
        product: ProductQuery,
        card: CandidateScorecard,
        *,
        output_dir: str | Path | None = None,
    ) -> BrowserVisibleProductVerdict:
        url = card.candidate.url
        scrape = card.scrape
        final_url = (scrape.final_url if scrape and scrape.final_url else url) or url
        output_path = Path(output_dir) if output_dir else None
        if output_path:
            output_path.mkdir(parents=True, exist_ok=True)

        capture = self._capture_browser(url, output_path=output_path) if self.config.capture_enabled else {}
        visible_text = capture.get("visible_text") or self._scrape_visible_text(card)
        page_title = capture.get("title") or (scrape.title if scrape else card.candidate.title) or ""
        final_url = capture.get("final_url") or final_url

        text_excerpt_path = ""
        resolved_url_path = ""
        if output_path:
            stem = self._safe_stem(url)
            text_excerpt_path = str(output_path / f"{stem}_visible_text.txt")
            resolved_url_path = str(output_path / f"{stem}_resolved_url.txt")
            Path(text_excerpt_path).write_text((visible_text or "")[:12000], encoding="utf-8")
            Path(resolved_url_path).write_text(final_url or "", encoding="utf-8")

        verdict = self._heuristic_verdict(
            product=product,
            card=card,
            visible_text=visible_text,
            page_title=page_title,
            final_url=final_url,
            screenshot_path=capture.get("screenshot_path", ""),
            visible_text_excerpt_path=text_excerpt_path,
            resolved_url_path=resolved_url_path,
            capture_status=capture.get("capture_status", "NOT_ATTEMPTED"),
            capture_error=capture.get("error", ""),
        )

        if self.config.llm_enabled:
            verdict = self._with_llm_verdict(product, card, verdict, visible_text=visible_text, page_title=page_title)

        if output_path:
            stem = self._safe_stem(url)
            self.write_verdict(output_path / f"{stem}_browser_visible_verdict.json", verdict)
            self.write_markdown(output_path / f"{stem}_browser_visible_verdict.md", product, verdict)
        return verdict

    @staticmethod
    def write_verdict(path: str | Path, verdict: BrowserVisibleProductVerdict) -> None:
        Path(path).write_text(json.dumps(verdict.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @staticmethod
    def write_markdown(path: str | Path, product: ProductQuery, verdict: BrowserVisibleProductVerdict) -> None:
        lines = [
            "# Browser-visible Product Content Verdict",
            "",
            "This artifact verifies what a normal browser user actually sees, not only whether the URL opens.",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Row ID | `{product.row_id}` |",
            f"| Main text | `{product.main_text}` |",
            f"| URL | {verdict.url} |",
            f"| Final/resolved URL | {verdict.final_url} |",
            f"| Status | `{verdict.status}` |",
            f"| Page type | `{verdict.browser_visible_page_type}` |",
            f"| User-visible product match | `{verdict.user_visible_product_match}` |",
            f"| Champion survives visible check | `{verdict.champion_should_survive_visible_check}` |",
            f"| Confidence | `{verdict.user_visible_content_confidence}` |",
            f"| Rerouted | `{verdict.rerouted_or_not}` |",
            f"| Reroute type | `{verdict.reroute_type}` |",
            f"| Screenshot | `{verdict.screenshot_path or 'None'}` |",
            f"| Visible text excerpt | `{verdict.visible_text_excerpt_path or 'None'}` |",
            "",
            "## Evidence",
            "",
        ]
        lines.extend(f"- {item}" for item in verdict.evidence or ("No evidence recorded.",))
        lines.extend(["", "## Reasons", ""])
        lines.extend(f"- {item}" for item in verdict.reasons or ("No reasons recorded.",))
        Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _capture_browser(self, url: str, *, output_path: Path | None) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {"capture_status": "PLAYWRIGHT_NOT_AVAILABLE", "error": str(exc)}

        screenshot_path = ""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout_ms)
                try:
                    page.wait_for_timeout(max(0, self.config.wait_ms))
                except Exception:
                    pass
                final_url = page.url
                title = page.title() or ""
                try:
                    visible_text = page.locator("body").inner_text(timeout=5000) or ""
                except Exception:
                    visible_text = ""
                if output_path:
                    screenshot_path = str(output_path / f"{self._safe_stem(url)}_browser_preview.png")
                    page.screenshot(path=screenshot_path, full_page=False)
                browser.close()
                return {
                    "capture_status": "CAPTURED",
                    "final_url": final_url,
                    "title": title,
                    "visible_text": visible_text,
                    "screenshot_path": screenshot_path,
                }
        except Exception as exc:
            logger.warning("Browser-visible capture failed | url={} | error={}", url, exc)
            return {"capture_status": "CAPTURE_FAILED", "error": str(exc)}

    def _heuristic_verdict(
        self,
        *,
        product: ProductQuery,
        card: CandidateScorecard,
        visible_text: str,
        page_title: str,
        final_url: str,
        screenshot_path: str,
        visible_text_excerpt_path: str,
        resolved_url_path: str,
        capture_status: str,
        capture_error: str,
    ) -> BrowserVisibleProductVerdict:
        scrape = card.scrape
        combined = " ".join([
            page_title or "",
            visible_text or "",
            scrape.page_product_name if scrape else "",
            scrape.description if scrape else "",
            " ".join((scrape.structured_eans or ())) if scrape else "",
        ])
        page_type = self._classify_visible_page(final_url=final_url, title=page_title, text=combined, scrape_product_page=bool(scrape and scrape.looks_like_product_page))
        token_overlap = self._token_overlap(product.main_text, combined)
        title_overlap = self._token_overlap(product.main_text, " ".join([page_title or "", scrape.page_product_name if scrape else ""]))
        ean_visible = bool(product.ean and product.ean in re.sub(r"\D", "", combined))
        brand_visible = bool(scrape and scrape.brand and scrape.brand.lower() in combined.lower())
        product_page_conf = self._product_page_confidence(page_type, combined, scrape)
        rerouted = self._rerouted(card.candidate.url, final_url, page_type)

        bad_status = BAD_PAGE_STATUSES.get(page_type)
        product_content_visible = bool(page_type == "product_page" and product_page_conf >= 0.45)
        visible_title_match = bool(title_overlap >= self.config.min_title_overlap or token_overlap >= self.config.min_token_overlap)
        user_match = bool(product_content_visible and not bad_status and (ean_visible or token_overlap >= self.config.min_token_overlap or visible_title_match))
        confidence = max(
            1.0 if ean_visible else 0.0,
            min(1.0, 0.35 * token_overlap + 0.25 * title_overlap + 0.25 * product_page_conf + (0.15 if brand_visible else 0.0)),
        )
        confidence = round(float(confidence), 4)

        if bad_status:
            status = bad_status
            user_match = False
        elif not product_content_visible:
            status = "BROWSER_OPENABLE_BUT_VISIBLE_CONTENT_INSUFFICIENT"
            user_match = False
        elif not user_match:
            status = "BROWSER_OPENABLE_BUT_WRONG_PRODUCT"
        else:
            status = "USER_VISIBLE_PRODUCT_PAGE_CONFIRMED"

        survives = bool(status == "USER_VISIBLE_PRODUCT_PAGE_CONFIRMED" and user_match and confidence >= 0.60 and not (rerouted and page_type != "product_page"))
        evidence = [
            f"capture_status={capture_status}",
            f"page_type={page_type}",
            f"token_overlap={token_overlap:.3f}",
            f"title_overlap={title_overlap:.3f}",
            f"product_page_confidence={product_page_conf:.3f}",
            f"ean_visible={ean_visible}",
            f"brand_visible={brand_visible}",
        ]
        reasons: list[str] = []
        if capture_error:
            reasons.append(f"browser_capture_issue={capture_error[:180]}")
        if bad_status:
            reasons.append(f"browser opened, but visible page type is `{page_type}`.")
        if rerouted:
            reasons.append("final resolved URL differs materially from candidate URL or looks rerouted.")
        if not user_match:
            reasons.append("visible text/screenshot evidence did not sufficiently match the requested product identity.")
        if user_match:
            reasons.append("visible page appears to show the requested product content.")

        return BrowserVisibleProductVerdict(
            url=card.candidate.url,
            final_url=final_url or card.candidate.url,
            status=status,
            browser_visible_page_type=page_type,
            user_visible_product_match=user_match,
            champion_should_survive_visible_check=survives,
            user_visible_content_confidence=confidence,
            product_content_visible=product_content_visible,
            rerouted_or_not=rerouted,
            reroute_type="VISIBLE_REROUTE_OR_SUBSTITUTION" if rerouted else "NONE",
            visible_title_match=visible_title_match,
            visible_brand_match=brand_visible,
            visible_quantity_match=True,
            visible_product_page_confidence=round(product_page_conf, 4),
            screenshot_path=screenshot_path,
            visible_text_excerpt_path=visible_text_excerpt_path,
            resolved_url_path=resolved_url_path,
            capture_status=capture_status,
            evidence=tuple(evidence),
            reasons=tuple(reasons),
            error=capture_error,
        )

    def _with_llm_verdict(self, product: ProductQuery, card: CandidateScorecard, verdict: BrowserVisibleProductVerdict, *, visible_text: str, page_title: str) -> BrowserVisibleProductVerdict:
        try:
            service = self.llm_service or get_llm_service()
        except Exception as exc:
            return self._replace(verdict, llm_status="LLM_NOT_AVAILABLE", reasons=verdict.reasons + (f"LLM not available: {exc}",))

        prompt = self._build_llm_prompt(product, card, verdict, visible_text=visible_text, page_title=page_title)
        try:
            response = service.predict(
                text=prompt,
                system_prompt="You are a strict browser-visible product page verifier. Return only JSON.",
                image=verdict.screenshot_path or None,
                image_detail=self.config.image_detail,
                response_format={"type": "json_object"},
                purpose="browser_visible_product_content_verification",
            )
            obj = self._loads_json(response.content)
            page_type = str(obj.get("browser_visible_page_type") or verdict.browser_visible_page_type)
            match = bool(obj.get("user_visible_product_match"))
            confidence = self._float01(obj.get("user_visible_content_confidence", verdict.user_visible_content_confidence))
            rerouted = bool(obj.get("rerouted_or_not", verdict.rerouted_or_not))
            status = str(obj.get("status") or ("USER_VISIBLE_PRODUCT_PAGE_CONFIRMED" if match else BAD_PAGE_STATUSES.get(page_type, "BROWSER_OPENABLE_BUT_WRONG_PRODUCT")))
            survives = bool(match and status == "USER_VISIBLE_PRODUCT_PAGE_CONFIRMED" and confidence >= self.config.min_llm_confidence)
            reasons = tuple(str(x)[:240] for x in obj.get("reasons", []) if str(x).strip()) or verdict.reasons
            return self._replace(
                verdict,
                status=status,
                browser_visible_page_type=page_type,
                user_visible_product_match=match,
                champion_should_survive_visible_check=survives,
                user_visible_content_confidence=confidence,
                rerouted_or_not=rerouted,
                reroute_type=str(obj.get("reroute_type") or verdict.reroute_type),
                llm_used=True,
                llm_status="USED",
                llm_raw_response=response.content[:4000],
                reasons=reasons,
            )
        except Exception as exc:
            logger.warning("Browser-visible LLM verification failed | url={} | error={}", card.candidate.url, exc)
            return self._replace(verdict, llm_status="LLM_FAILED", reasons=verdict.reasons + (f"LLM visible verifier failed: {exc}",))

    @staticmethod
    def _build_llm_prompt(product: ProductQuery, card: CandidateScorecard, verdict: BrowserVisibleProductVerdict, *, visible_text: str, page_title: str) -> str:
        scrape = card.scrape
        return f"""
Verify what the user actually sees in the browser for this champion candidate.

Intended product identity:
- row_id: {product.row_id}
- main_text: {product.main_text}
- country_code: {product.country_code}
- retailer_name: {product.retailer_name or ''}
- ean: {product.ean or ''}

Candidate URL: {card.candidate.url}
Final/resolved URL: {verdict.final_url}
Browser capture status: {verdict.capture_status}
Page title: {page_title}
Scrape product name: {(scrape.page_product_name if scrape else '')}
Scrape brand: {(scrape.brand if scrape else '')}
Scrape manufacturer: {(scrape.manufacturer if scrape else '')}
Scrape GTIN/EANs: {', '.join(scrape.structured_eans) if scrape else ''}

Visible text excerpt:
{(visible_text or '')[:6000]}

Return strict JSON with these keys:
- browser_visible_page_type: one of product_page, homepage, category_page, search_results, consent_wall, login_wall, access_blocked, not_product_page, unknown
- user_visible_product_match: boolean
- user_visible_content_confidence: number from 0 to 1
- product_content_visible: boolean
- rerouted_or_not: boolean
- reroute_type: NONE, VISIBLE_REROUTE_OR_SUBSTITUTION, GEO_REDIRECT, LOGIN_OR_CONSENT, ACCESS_BLOCK, OTHER
- visible_title_match: boolean
- visible_brand_match: boolean
- visible_quantity_match: boolean
- visible_product_page_confidence: number from 0 to 1
- status: USER_VISIBLE_PRODUCT_PAGE_CONFIRMED or a BROWSER_OPENABLE_BUT_* failure status
- reasons: short list of factual reasons based only on visible/scraped evidence
""".strip()

    @staticmethod
    def _replace(verdict: BrowserVisibleProductVerdict, **updates: Any) -> BrowserVisibleProductVerdict:
        data = verdict.to_dict()
        data.update(updates)
        if isinstance(data.get("evidence"), list):
            data["evidence"] = tuple(data["evidence"])
        if isinstance(data.get("reasons"), list):
            data["reasons"] = tuple(data["reasons"])
        return BrowserVisibleProductVerdict(**data)

    @staticmethod
    def _loads_json(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw or "", flags=re.S)
            if not match:
                raise
            return json.loads(match.group(0))

    @staticmethod
    def _float01(value: Any) -> float:
        try:
            x = float(value)
        except Exception:
            return 0.0
        return round(max(0.0, min(1.0, x)), 4)

    @staticmethod
    def _scrape_visible_text(card: CandidateScorecard) -> str:
        scrape = card.scrape
        if not scrape:
            return " ".join([card.candidate.title, card.candidate.snippet])
        return " ".join([
            scrape.title,
            scrape.h1,
            scrape.page_product_name,
            scrape.description,
            scrape.markdown_excerpt,
            scrape.verification_text[:8000],
        ])

    @staticmethod
    def _classify_visible_page(*, final_url: str, title: str, text: str, scrape_product_page: bool) -> str:
        folded = " ".join([final_url or "", title or "", text or ""]).lower()
        if any(x in folded for x in ("access denied", "captcha", "robot check", "verify you are human", "blocked")):
            return "access_blocked"
        if any(x in folded for x in ("sign in", "log in", "login", "account required")) and not scrape_product_page:
            return "login_wall"
        if any(x in folded for x in ("accept cookies", "cookie settings", "consent", "privacy choices")) and len(text.split()) < 180:
            return "consent_wall"
        url_path = urlparse(final_url or "").path.lower().strip("/")
        if not url_path or url_path in {"", "home", "homepage"}:
            return "homepage"
        if any(x in folded for x in ("search results", "results for", "we found", "no results", "sort by")) and not scrape_product_page:
            return "search_results"
        if any(x in folded for x in ("category", "department", "all products", "filter by", "shop by")) and not scrape_product_page:
            return "category_page"
        if scrape_product_page or any(x in folded for x in ("add to cart", "buy now", "availability", "in stock", "out of stock", "sku", "ean", "gtin", "product details")):
            return "product_page"
        return "not_product_page"

    @staticmethod
    def _product_page_confidence(page_type: str, text: str, scrape: Any) -> float:
        score = 0.0
        score += 0.45 if page_type == "product_page" else 0.0
        if scrape:
            score += 0.15 if scrape.looks_like_product_page else 0.0
            score += 0.10 if scrape.has_price else 0.0
            score += 0.10 if scrape.image_count > 0 else 0.0
            score += 0.10 if scrape.page_product_name else 0.0
            score += 0.10 if scrape.description else 0.0
        folded = (text or "").lower()
        score += 0.10 if any(x in folded for x in ("add to cart", "buy now", "product details", "availability")) else 0.0
        return min(1.0, score)

    @staticmethod
    def _token_overlap(expected: str, observed: str) -> float:
        expected_tokens = BrowserVisibleContentVerifier._tokens(expected)
        if not expected_tokens:
            return 0.0
        observed_tokens = set(BrowserVisibleContentVerifier._tokens(observed))
        if not observed_tokens:
            return 0.0
        return len(set(expected_tokens) & observed_tokens) / max(1, len(set(expected_tokens)))

    @staticmethod
    def _tokens(text: str) -> list[str]:
        stop = {"the", "and", "for", "with", "from", "product", "toy", "set", "pack", "pcs", "ks", "cm", "mm"}
        return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) >= 3 and t not in stop]

    @staticmethod
    def _rerouted(original_url: str, final_url: str, page_type: str) -> bool:
        if not final_url:
            return False
        original = normalize_url(original_url or "")
        final = normalize_url(final_url or "")
        if original == final:
            return False
        o = urlparse(original)
        f = urlparse(final)
        if o.netloc and f.netloc and o.netloc != f.netloc:
            return True
        if page_type in {"homepage", "category_page", "search_results", "consent_wall", "login_wall", "access_blocked"}:
            return True
        return False

    @staticmethod
    def _safe_stem(url: str) -> str:
        digest = sha1((url or "").encode("utf-8")).hexdigest()[:12]
        host = re.sub(r"[^a-zA-Z0-9]+", "_", urlparse(url or "").netloc)[:40] or "url"
        return f"{host}_{digest}"
