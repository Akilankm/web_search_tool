from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from product_url_v2.acquisition import product_fields
from product_url_v2.config import RuntimeConfig
from product_url_v2.models import (
    BrowserEvidence,
    CandidateAssessment,
    DeliveryDecision,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    Interpretation,
    PageEvidence,
    ProductInput,
    SearchResult,
    SourceRole,
)

_MARKETPLACE_HOSTS = ("amazon.", "ebay.", "aliexpress.", "temu.", "etsy.", "kaufland.")
_PRODUCT_TERMS = re.compile(r"add to cart|buy now|in stock|price|warenkorb|kaufen|lieferbar|ajouter au panier|acquista", re.I)


def assess_candidate(
    product: ProductInput,
    interpretation: Interpretation,
    search: SearchResult,
    page: PageEvidence,
    feature_set: Mapping[str, Any],
    config: RuntimeConfig,
    browser: BrowserEvidence | None = None,
) -> CandidateAssessment:
    url = page.final_url or search.url
    domain = (urlparse(url).hostname or "").lower().removeprefix("www.")
    fields = product_fields(page)
    combined = " ".join((page.title, page.description, page.visible_text[:100000], " ".join(str(value) for value in fields.values()))).casefold()
    support, conflicts, evidence = _identity_score(product, interpretation, combined, fields)
    identity = _identity_match(support, conflicts, config)
    direct_score = _direct_page_score(url, page, fields, combined)
    direct_gate = GateStatus.PASS if direct_score >= config.decision.minimum_direct_page_score else GateStatus.FAIL
    durable = _durability(page, url)
    country = _country_gate(product, domain, combined)
    retailer = _retailer_gate(product, domain, combined)
    source_role, authority = _source_role(product, interpretation, domain, combined)
    browser_access = browser.access if browser else GateStatus.NOT_ASSESSED
    browser_text = browser.visible_text if browser else ""
    extractable = GateStatus.PASS if page.fetch_status is GateStatus.PASS and bool(page.visible_text or page.jsonld_products) else GateStatus.FAIL
    if browser and browser.access is GateStatus.PASS and browser.visible_text:
        extractable = GateStatus.PASS
    coding = _coding_gate(feature_set, fields, combined + " " + browser_text.casefold())
    warnings: list[str] = []
    if browser_access is GateStatus.NOT_ASSESSED:
        warnings.append("Rendered browser accessibility was not assessed.")
    elif browser_access is GateStatus.FAIL:
        warnings.append("Automation browser failed; this does not prove a human cannot open the URL.")
    if coding is not GateStatus.PASS:
        warnings.append("The selected page may not contain every requested coding field.")
    if country is not GateStatus.PASS:
        warnings.append("Country-market alignment is not fully confirmed.")
    return CandidateAssessment(
        candidate_id=f"C-{abs(hash(url)) % 10_000_000:07d}",
        url=url,
        domain=domain,
        search_rank=search.position,
        search_support=max(0.0, min(1.0, 1.0 - ((search.position or 10) - 1) * 0.04)),
        source_role=source_role,
        identity_match=identity,
        identity_confidence=support,
        direct_product_page=direct_gate,
        direct_page_score=direct_score,
        durable_url=durable,
        country_match=country,
        retailer_match=retailer,
        browser_access=browser_access,
        text_extractable=extractable,
        coding_evidence_complete=coding,
        source_authority=authority,
        evidence=evidence | {"fields": fields, "page_title": page.title, "status_code": page.status_code},
        conflicts=tuple(conflicts),
        warnings=tuple(warnings),
    )


def apply_browser_evidence(candidate: CandidateAssessment, browser: BrowserEvidence) -> CandidateAssessment:
    warnings = [item for item in candidate.warnings if not item.startswith("Rendered browser") and not item.startswith("Automation browser")]
    if browser.access is GateStatus.FAIL:
        warnings.append("Automation browser failed; this does not prove a human cannot open the URL.")
    return replace(
        candidate,
        browser_access=browser.access,
        text_extractable=GateStatus.PASS if browser.access is GateStatus.PASS and bool(browser.visible_text) else candidate.text_extractable,
        warnings=tuple(warnings),
        evidence=dict(candidate.evidence) | {"browser": {"final_url": browser.final_url, "title": browser.title, "product_controls": list(browser.product_controls), "screenshot_path": browser.screenshot_path, "error": browser.error}},
    )


def choose_delivery(candidates: Sequence[CandidateAssessment]) -> DeliveryDecision:
    strict = [item for item in candidates if item.strictly_verified]
    if strict:
        selected = max(strict, key=_rank)
        return DeliveryDecision(
            DeliveryStatus.VERIFIED,
            selected.url,
            selected.candidate_id,
            selected.identity_confidence,
            True,
            ("Exact product identity passed strict gates.", "Direct product page, durable URL, browser access, extraction and coding evidence passed."),
            selected.warnings,
        )
    review = [item for item in candidates if item.review_eligible]
    if review:
        selected = max(review, key=_rank)
        reasons = ["Strongest real direct product URL retained for human review."]
        if selected.identity_match is IdentityMatch.EXACT:
            reasons.append("Identity evidence supports the exact product, but one or more operational gates remain incomplete.")
        elif selected.identity_match is IdentityMatch.PROBABLE:
            reasons.append("Product identity is probable but unresolved evidence remains.")
        else:
            reasons.append("Product identity requires reviewer confirmation.")
        return DeliveryDecision(DeliveryStatus.REVIEW_REQUIRED, selected.url, selected.candidate_id, selected.identity_confidence, False, tuple(reasons), selected.warnings)
    return DeliveryDecision(
        DeliveryStatus.FAILED,
        None,
        None,
        0.0,
        False,
        ("No direct product-page candidate survived explicit wrong-product, wrong-page or transient-URL blockers after the bounded recovery campaign.",),
    )


def _identity_score(product: ProductInput, interpretation: Interpretation, text: str, fields: Mapping[str, str]) -> tuple[float, list[str], dict[str, Any]]:
    weighted = 0.0
    possible = 0.0
    matched: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []
    weights = {"ean": 5.0, "model": 4.0, "brand": 2.0, "quantity": 2.5, "size": 2.5, "pack_configuration": 3.0, "product_name": 2.0, "language": 0.5}
    for signal in interpretation.signals:
        weight = weights.get(signal.field, 1.0) * max(0.4, signal.confidence)
        possible += weight
        value = signal.value.casefold()
        field_values = " ".join(str(item) for key, item in fields.items() if key == signal.field or (signal.field == "ean" and key.startswith("gtin"))).casefold()
        present = value in text or value in field_values
        if present:
            weighted += weight
            matched.append(f"{signal.field}={signal.value}")
        elif signal.exact and signal.field in {"ean", "model", "quantity", "size", "pack_configuration"}:
            missing.append(f"{signal.field}={signal.value}")
    if product.ean:
        gtins = " ".join(value for key, value in fields.items() if key.startswith("gtin"))
        numeric_text = re.sub(r"\D", "", text)
        if gtins and product.ean not in re.sub(r"\D", "", gtins):
            conflicts.append("EAN/GTIN conflict")
        elif product.ean not in numeric_text and not gtins:
            missing.append(f"ean={product.ean}")
    support = weighted / possible if possible else 0.0
    if matched and not conflicts:
        support = min(1.0, support + 0.08)
    if missing:
        support = max(0.0, support - min(0.25, len(missing) * 0.04))
    if conflicts:
        support = min(support, 0.15)
    return support, conflicts, {"matched_signals": matched, "missing_signals": missing, "identity_conflicts": conflicts}


def _identity_match(score: float, conflicts: Sequence[str], config: RuntimeConfig) -> IdentityMatch:
    if conflicts or score <= config.decision.wrong_product_threshold:
        return IdentityMatch.MISMATCH
    if score >= config.decision.verified_identity_threshold:
        return IdentityMatch.EXACT
    if score >= config.decision.review_identity_threshold:
        return IdentityMatch.PROBABLE
    return IdentityMatch.UNVERIFIED


def _direct_page_score(url: str, page: PageEvidence, fields: Mapping[str, str], text: str) -> float:
    score = 0.0
    path = urlparse(url).path.casefold()
    if page.jsonld_products:
        score += 0.45
    if fields.get("price"):
        score += 0.15
    if fields.get("product_name"):
        score += 0.10
    if _PRODUCT_TERMS.search(text):
        score += 0.15
    if any(token in path for token in ("/product", "/products", "/item", "/p/", "/dp/", "/sku", "/shop/")):
        score += 0.15
    if page.metadata.get("og:type", "").casefold() == "product":
        score += 0.20
    if path in {"", "/"} or any(token in path for token in ("/search", "/category", "/collections")):
        score -= 0.50
    return max(0.0, min(1.0, score))


def _durability(page: PageEvidence, url: str) -> GateStatus:
    if page.fetch_status is GateStatus.FAIL:
        return GateStatus.NOT_ASSESSED
    if any(token in url.casefold() for token in ("session=", "token=", "redirect=", "google.com/url")):
        return GateStatus.FAIL
    return GateStatus.PASS


def _country_gate(product: ProductInput, domain: str, text: str) -> GateStatus:
    cc = product.country_code.casefold()
    if domain.endswith(f".{cc}") or f"/{cc}/" in text[:5000] or f" {cc.upper()} " in text[:5000].upper():
        return GateStatus.PASS
    return GateStatus.NOT_ASSESSED


def _retailer_gate(product: ProductInput, domain: str, text: str) -> GateStatus:
    if not product.retailer_name:
        return GateStatus.NOT_ASSESSED
    tokens = [token.casefold() for token in re.findall(r"\w+", product.retailer_name) if len(token) > 2]
    if any(token in domain or token in text[:10000] for token in tokens):
        return GateStatus.PASS
    return GateStatus.FAIL


def _source_role(product: ProductInput, interpretation: Interpretation, domain: str, text: str) -> tuple[SourceRole, int]:
    if any(host in domain for host in _MARKETPLACE_HOSTS):
        return SourceRole.MARKETPLACE, 45
    retailer = _retailer_gate(product, domain, text)
    if retailer is GateStatus.PASS:
        return SourceRole.REQUESTED_RETAILER, 85
    brand = interpretation.strongest("brand")
    if brand and len(brand.value) > 3 and brand.value.casefold() in domain.replace("-", ""):
        country = _country_gate(product, domain, text)
        return (SourceRole.LOCAL_MANUFACTURER, 100) if country is GateStatus.PASS else (SourceRole.GLOBAL_MANUFACTURER, 95)
    country = _country_gate(product, domain, text)
    return (SourceRole.COUNTRY_RETAILER, 75) if country is GateStatus.PASS else (SourceRole.GLOBAL_RETAILER, 65)


def _coding_gate(feature_set: Mapping[str, Any], fields: Mapping[str, str], text: str) -> GateStatus:
    required = [str(item) for item in feature_set.get("required_fields") or []]
    missing = []
    for name in required:
        if fields.get(name):
            continue
        if name == "brand" and re.search(r"\bbrand\b", text, flags=re.I):
            continue
        missing.append(name)
    return GateStatus.PASS if not missing else GateStatus.FAIL


def _rank(candidate: CandidateAssessment) -> tuple[float, ...]:
    return (
        1.0 if candidate.identity_match is IdentityMatch.EXACT else 0.7 if candidate.identity_match is IdentityMatch.PROBABLE else 0.2,
        candidate.identity_confidence,
        candidate.direct_page_score,
        float(candidate.source_authority) / 100.0,
        1.0 if candidate.country_match is GateStatus.PASS else 0.0,
        1.0 if candidate.retailer_match is GateStatus.PASS else 0.0,
        1.0 if candidate.browser_access is GateStatus.PASS else 0.0,
        candidate.search_support,
        float(-(candidate.search_rank or 9999)),
    )
