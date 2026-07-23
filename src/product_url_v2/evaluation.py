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
from product_url_v2.search import explicit_identifier_from_url, is_product_like_url

_MARKETPLACE_HOSTS = ("amazon.", "ebay.", "aliexpress.", "temu.", "etsy.", "kaufland.")
_PRODUCT_TERMS = re.compile(
    r"add to cart|buy now|in stock|price|warenkorb|kaufen|lieferbar|ajouter au panier|acquista|"
    r"in den warenkorb|sofort-download|produktdetails|product details|isbn|ean|gtin",
    re.I,
)
_IDENTIFIER_PATTERN = re.compile(r"(?<!\d)(\d{8}|\d{12}|\d{13}|\d{14})(?!\d)")
_LABELED_IDENTIFIER_PATTERN = re.compile(
    r"(?:ean|isbn(?:-13)?|gtin(?:-8|-12|-13|-14)?)[^0-9]{0,16}(\d{8}|\d{12,14})",
    re.I,
)
_SOURCE_PRIORITY = {
    SourceRole.LOCAL_MANUFACTURER: 6,
    SourceRole.GLOBAL_MANUFACTURER: 5,
    SourceRole.REQUESTED_RETAILER: 4,
    SourceRole.COUNTRY_RETAILER: 3,
    SourceRole.GLOBAL_RETAILER: 2,
    SourceRole.MARKETPLACE: 1,
    SourceRole.UNKNOWN: 0,
}


def assess_candidate(
    product: ProductInput,
    interpretation: Interpretation,
    search: SearchResult,
    page: PageEvidence,
    feature_set: Mapping[str, Any],
    config: RuntimeConfig,
    browser: BrowserEvidence | None = None,
) -> CandidateAssessment:
    page_final_url = page.final_url or search.url
    url = page_final_url if is_product_like_url(page_final_url) else search.url
    domain = (urlparse(url).hostname or "").lower().removeprefix("www.")
    fields = product_fields(page)
    page_text = _identity_text(page.title, page.description, page.visible_text, fields)

    support, conflicts, identity_evidence = _identity_score(
        product,
        interpretation,
        page_text,
        fields,
        url,
        config,
    )
    exact_identifier_verified = bool(identity_evidence.get("exact_identifier_verified"))
    identity = _identity_match(product, support, conflicts, exact_identifier_verified, config)
    direct_score = _direct_page_score(url, page, fields, page_text, exact_identifier_verified)
    direct_gate = GateStatus.PASS if direct_score >= config.decision.minimum_direct_page_score else GateStatus.FAIL
    durable = _durability(page.fetch_status, url)
    country = _country_gate(product, domain, page_text)
    retailer = _retailer_gate(product, domain, page_text)
    source_role, authority = _source_role(product, interpretation, domain, page_text, fields, search)
    browser_access = browser.access if browser else GateStatus.NOT_ASSESSED
    extractable = (
        GateStatus.PASS
        if page.fetch_status is GateStatus.PASS and bool(page.visible_text.strip() or page.jsonld_products)
        else GateStatus.FAIL
    )
    coding = _coding_gate(feature_set, fields, page_text)

    hard_url_blockers = _hard_url_blockers(
        product=product,
        search=search,
        page=page,
        url=url,
        direct_gate=direct_gate,
        durable=durable,
        exact_identifier_verified=exact_identifier_verified,
        conflicts=conflicts,
    )
    warnings = _candidate_warnings(
        product=product,
        identity=identity,
        exact_identifier_verified=exact_identifier_verified,
        page=page,
        browser_access=browser_access,
        extractable=extractable,
        coding=coding,
        country=country,
        retailer=retailer,
    )

    evidence = identity_evidence | {
        "fields": fields,
        "required_identifier": product.ean or "",
        "exact_identifier_verified": exact_identifier_verified,
        "page_identity_text": page_text[:200000],
        "page_title": page.title,
        "status_code": page.status_code,
        "search_url": search.url,
        "search_title": search.title,
        "search_snippet": search.snippet,
        "search_source_section": search.source_section,
        "search_engine": search.engine,
        "search_product_like": bool(search.product_like),
        "page_final_url": page_final_url,
        "page_fetch_status": page.fetch_status.value,
        "page_fetch_error": page.fetch_error,
        "delivery_basis": "page_evidence" if page.fetch_status is GateStatus.PASS else "discovery_only",
        "hard_url_blockers": hard_url_blockers,
    }

    candidate = CandidateAssessment(
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
        evidence=evidence,
        conflicts=tuple(dict.fromkeys(conflicts)),
        warnings=tuple(dict.fromkeys(warnings)),
    )
    if browser is not None:
        return apply_browser_evidence(product, interpretation, candidate, browser, config)
    return candidate


def apply_browser_evidence(
    product: ProductInput,
    interpretation: Interpretation,
    candidate: CandidateAssessment,
    browser: BrowserEvidence,
    config: RuntimeConfig,
) -> CandidateAssessment:
    browser_final = browser.final_url or candidate.url
    final_product_like = is_product_like_url(browser_final)
    browser_access = browser.access
    browser_text = _identity_text(browser.title, browser.visible_text)
    combined_text = " ".join(
        (
            str(candidate.evidence.get("page_identity_text") or ""),
            browser_text,
        )
    ).strip()
    fields = dict(candidate.evidence.get("fields") or {})

    support, new_conflicts, identity_evidence = _identity_score(
        product,
        interpretation,
        combined_text,
        fields,
        browser_final,
        config,
    )
    conflicts = list(candidate.conflicts)
    conflicts.extend(new_conflicts)
    if browser.access is GateStatus.PASS and not final_product_like:
        conflicts.append("Rendered browser redirected to a non-product page")
        browser_access = GateStatus.FAIL
    if browser.access is GateStatus.PASS and not browser.visible_text.strip():
        conflicts.append("Rendered browser returned no extractable product text")
        browser_access = GateStatus.FAIL

    exact_identifier_verified = bool(identity_evidence.get("exact_identifier_verified"))
    identity = _identity_match(product, support, conflicts, exact_identifier_verified, config)
    text_extractable = (
        GateStatus.PASS
        if browser_access is GateStatus.PASS and bool(browser.visible_text.strip())
        else GateStatus.FAIL
    )
    durable = _durability(browser_access, browser_final)
    direct_score = candidate.direct_page_score
    if browser_access is GateStatus.PASS:
        if exact_identifier_verified:
            direct_score = max(direct_score, 0.65)
        if browser.product_controls or _PRODUCT_TERMS.search(browser_text):
            direct_score = min(1.0, max(direct_score, 0.70))
    direct_gate = GateStatus.PASS if direct_score >= config.decision.minimum_direct_page_score else GateStatus.FAIL

    hard_blockers = list(candidate.hard_url_blockers)
    if browser_access is not GateStatus.PASS:
        hard_blockers.append("Selected URL did not pass rendered-browser accessibility.")
    if text_extractable is not GateStatus.PASS:
        hard_blockers.append("Selected URL did not expose scrapable rendered product text.")
    if direct_gate is not GateStatus.PASS:
        hard_blockers.append("Rendered page did not prove a direct product-detail page.")
    if product.ean and not exact_identifier_verified:
        hard_blockers.append(f"Rendered page did not confirm supplied EAN/GTIN {product.ean}.")
    hard_blockers.extend(conflicts)

    warnings = [
        item
        for item in candidate.warnings
        if not item.startswith("Rendered browser")
        and not item.startswith("Automation browser")
        and not item.startswith("Exact identifier")
    ]
    if browser_access is not GateStatus.PASS:
        warnings.append("Rendered browser could not confirm that a human-usable product page opens.")
    if product.ean and not exact_identifier_verified:
        warnings.append(f"Exact identifier {product.ean} was not found in the rendered product content.")

    final_url = browser_final if browser_access is GateStatus.PASS and final_product_like else candidate.url
    final_domain = (urlparse(final_url).hostname or "").lower().removeprefix("www.")
    evidence = dict(candidate.evidence) | identity_evidence | {
        "exact_identifier_verified": exact_identifier_verified,
        "hard_url_blockers": list(dict.fromkeys(hard_blockers)),
        "delivery_basis": "rendered_exact_product_page" if browser_access is GateStatus.PASS else "rejected_browser_evidence",
        "browser": {
            "final_url": browser.final_url,
            "title": browser.title,
            "visible_text_length": len(browser.visible_text),
            "product_controls": list(browser.product_controls),
            "screenshot_path": browser.screenshot_path,
            "error": browser.error,
        },
    }

    return replace(
        candidate,
        url=final_url,
        domain=final_domain,
        identity_match=identity,
        identity_confidence=support,
        direct_product_page=direct_gate,
        direct_page_score=direct_score,
        durable_url=durable,
        browser_access=browser_access,
        text_extractable=text_extractable,
        evidence=evidence,
        conflicts=tuple(dict.fromkeys(conflicts)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def choose_delivery(candidates: Sequence[CandidateAssessment]) -> DeliveryDecision:
    mapped = [item for item in candidates if item.mapping_eligible]
    if not mapped:
        reasons = [
            "No candidate satisfied the exact-and-usable product mapping contract.",
            "A final URL requires exact identity, a direct durable product page, rendered-browser access and scrapable product text.",
        ]
        if candidates:
            reasons.append("Discovery candidates were retained for audit but were not misrepresented as successful mappings.")
        else:
            reasons.append("The search campaign found no admissible direct-product candidate.")
        return DeliveryDecision(
            DeliveryStatus.FAILED,
            None,
            None,
            0.0,
            False,
            tuple(reasons),
        )

    selected = max(mapped, key=_rank)
    manufacturer = selected.source_role in {SourceRole.LOCAL_MANUFACTURER, SourceRole.GLOBAL_MANUFACTURER}
    reasons = [
        "The supplied product was mapped to one exact, browser-openable and scrapable direct product URL.",
        "Exact identity was established from page or rendered-page evidence, not from the search snippet alone.",
        "Manufacturer sources were ranked before retailer sources after all mandatory gates passed."
        if manufacturer
        else "No exact usable manufacturer page outranked this exact retailer product page.",
    ]
    if selected.strictly_verified:
        return DeliveryDecision(
            DeliveryStatus.VERIFIED,
            selected.url,
            selected.candidate_id,
            selected.identity_confidence,
            True,
            tuple(reasons),
            selected.warnings,
        )
    return DeliveryDecision(
        DeliveryStatus.REVIEW_REQUIRED,
        selected.url,
        selected.candidate_id,
        selected.identity_confidence,
        False,
        tuple(reasons + ["The URL mapping is valid; review is limited to secondary coding or market evidence."]),
        selected.warnings,
    )


def _identity_score(
    product: ProductInput,
    interpretation: Interpretation,
    text: str,
    fields: Mapping[str, str],
    url: str,
    config: RuntimeConfig,
) -> tuple[float, list[str], dict[str, Any]]:
    normalized_text = text.casefold()
    weighted = 0.0
    possible = 0.0
    matched: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []
    weights = {
        "ean": 8.0,
        "model": 5.0,
        "brand": 2.5,
        "quantity": 2.5,
        "size": 2.5,
        "pack_configuration": 3.0,
        "product_name": 3.0,
        "language": 0.5,
    }

    for signal in interpretation.signals:
        weight = weights.get(signal.field, 1.0) * max(0.4, signal.confidence)
        possible += weight
        value = signal.value.casefold()
        field_values = " ".join(
            str(item)
            for key, item in fields.items()
            if key == signal.field or (signal.field == "ean" and key.startswith(("gtin", "ean", "isbn")))
        ).casefold()
        if value and (value in normalized_text or value in field_values):
            weighted += weight
            matched.append(f"{signal.field}={signal.value}")
        elif signal.exact and signal.field in {"ean", "model", "quantity", "size", "pack_configuration"}:
            missing.append(f"{signal.field}={signal.value}")

    page_identifiers = _page_identifiers(text, fields)
    url_identifiers = explicit_identifier_from_url(url)
    required_identifier = product.ean or ""
    exact_identifier_verified = not bool(required_identifier)

    if required_identifier:
        exact_identifier_verified = required_identifier in page_identifiers
        explicit_field_identifiers = _field_identifiers(fields)
        conflicting_fields = sorted(value for value in explicit_field_identifiers if value != required_identifier)
        conflicting_url = sorted(value for value in url_identifiers if value != required_identifier)
        if conflicting_fields:
            conflicts.append(
                f"EAN/GTIN conflict: page exposes {', '.join(conflicting_fields)} instead of {required_identifier}"
            )
        if conflicting_url:
            conflicts.append(
                f"URL identifier conflict: path exposes {', '.join(conflicting_url)} instead of {required_identifier}"
            )
        if exact_identifier_verified:
            matched.append(f"ean={required_identifier}")
            weighted += weights["ean"]
            possible += weights["ean"]
        else:
            missing.append(f"ean={required_identifier}")

    support = weighted / possible if possible else 0.0
    if matched and not conflicts:
        support = min(1.0, support + 0.05)
    if missing:
        support = max(0.0, support - min(0.25, len(set(missing)) * 0.04))
    if required_identifier and exact_identifier_verified and not conflicts:
        support = max(support, 0.95)
    if required_identifier and not exact_identifier_verified:
        support = min(support, config.decision.review_identity_threshold - 0.01)
    if conflicts:
        support = min(support, 0.10)

    return support, conflicts, {
        "matched_signals": list(dict.fromkeys(matched)),
        "missing_signals": list(dict.fromkeys(missing)),
        "identity_conflicts": list(dict.fromkeys(conflicts)),
        "page_identifiers": sorted(page_identifiers),
        "url_identifiers": list(url_identifiers),
        "exact_identifier_verified": exact_identifier_verified,
    }


def _identity_match(
    product: ProductInput,
    score: float,
    conflicts: Sequence[str],
    exact_identifier_verified: bool,
    config: RuntimeConfig,
) -> IdentityMatch:
    if conflicts:
        return IdentityMatch.MISMATCH
    if product.ean and not exact_identifier_verified:
        return IdentityMatch.UNVERIFIED
    if score >= config.decision.verified_identity_threshold:
        return IdentityMatch.EXACT
    if score >= config.decision.review_identity_threshold:
        return IdentityMatch.PROBABLE
    return IdentityMatch.UNVERIFIED


def _direct_page_score(
    url: str,
    page: PageEvidence,
    fields: Mapping[str, str],
    text: str,
    exact_identifier_verified: bool,
) -> float:
    score = 0.0
    path = urlparse(url).path.casefold()
    if page.fetch_status is GateStatus.PASS:
        score += 0.10
    if page.jsonld_products:
        score += 0.35
    if exact_identifier_verified:
        score += 0.35
    if fields.get("price") or fields.get("availability"):
        score += 0.10
    if fields.get("product_name") or page.title:
        score += 0.10
    if _PRODUCT_TERMS.search(text):
        score += 0.10
    if any(token in path for token in ("/product", "/products", "/item", "/p/", "/dp/", "/sku", "/shop/", "/detail/")):
        score += 0.10
    if page.metadata.get("og:type", "").casefold() == "product":
        score += 0.15
    if path in {"", "/"} or any(token in path for token in ("/search", "/category", "/collections", "/login", "/consent")):
        score -= 0.60
    return max(0.0, min(1.0, score))


def _durability(access_status: GateStatus, url: str) -> GateStatus:
    lowered = url.casefold()
    if any(token in lowered for token in ("session=", "token=", "redirect=", "google.com/url", "serpapi.com")):
        return GateStatus.FAIL
    if access_status is not GateStatus.PASS:
        return GateStatus.NOT_ASSESSED
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


def _source_role(
    product: ProductInput,
    interpretation: Interpretation,
    domain: str,
    text: str,
    fields: Mapping[str, str],
    search: SearchResult,
) -> tuple[SourceRole, int]:
    if any(host in domain for host in _MARKETPLACE_HOSTS):
        return SourceRole.MARKETPLACE, 40

    retailer = _retailer_gate(product, domain, text)
    if retailer is GateStatus.PASS:
        return SourceRole.REQUESTED_RETAILER, 82

    manufacturer_names = [
        fields.get("brand", ""),
        fields.get("manufacturer", ""),
        fields.get("publisher", ""),
    ]
    brand_signal = interpretation.strongest("brand")
    if brand_signal:
        manufacturer_names.append(brand_signal.value)
    if _domain_matches_entity(domain, manufacturer_names):
        country = _country_gate(product, domain, text)
        return (SourceRole.LOCAL_MANUFACTURER, 100) if country is GateStatus.PASS else (SourceRole.GLOBAL_MANUFACTURER, 96)

    purpose = search.source_section.upper()
    if "MANUFACTURER" in purpose and re.search(r"manufacturer|hersteller|publisher|verlag", text, flags=re.I):
        country = _country_gate(product, domain, text)
        return (SourceRole.LOCAL_MANUFACTURER, 94) if country is GateStatus.PASS else (SourceRole.GLOBAL_MANUFACTURER, 90)

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
        1.0 if candidate.mapping_eligible else 0.0,
        float(_SOURCE_PRIORITY[candidate.source_role]),
        1.0 if candidate.country_match is GateStatus.PASS else 0.0,
        1.0 if candidate.retailer_match is GateStatus.PASS else 0.0,
        candidate.identity_confidence,
        candidate.direct_page_score,
        float(candidate.source_authority) / 100.0,
        candidate.search_support,
        float(-(candidate.search_rank or 9999)),
    )


def _hard_url_blockers(
    *,
    product: ProductInput,
    search: SearchResult,
    page: PageEvidence,
    url: str,
    direct_gate: GateStatus,
    durable: GateStatus,
    exact_identifier_verified: bool,
    conflicts: Sequence[str],
) -> list[str]:
    blockers: list[str] = []
    if not search.product_like or not is_product_like_url(search.url):
        blockers.append("Search result is not a structurally product-like external URL.")
    if page.fetch_status is not GateStatus.PASS:
        blockers.append("URL did not pass HTTP page acquisition.")
    if direct_gate is not GateStatus.PASS:
        blockers.append("Page did not pass direct product-detail verification.")
    if durable is not GateStatus.PASS:
        blockers.append("URL durability could not be confirmed.")
    if product.ean and not exact_identifier_verified:
        blockers.append(f"Page did not confirm supplied EAN/GTIN {product.ean}.")
    blockers.extend(conflicts)
    return list(dict.fromkeys(blockers))


def _candidate_warnings(
    *,
    product: ProductInput,
    identity: IdentityMatch,
    exact_identifier_verified: bool,
    page: PageEvidence,
    browser_access: GateStatus,
    extractable: GateStatus,
    coding: GateStatus,
    country: GateStatus,
    retailer: GateStatus,
) -> list[str]:
    warnings: list[str] = []
    if identity is not IdentityMatch.EXACT:
        warnings.append("Exact product identity has not yet passed.")
    if product.ean and not exact_identifier_verified:
        warnings.append(f"Exact identifier {product.ean} is absent from acquired page evidence.")
    if page.fetch_status is not GateStatus.PASS:
        warnings.append(f"Page acquisition did not pass: {page.fetch_error or page.fetch_status.value}.")
    if browser_access is not GateStatus.PASS:
        warnings.append("Rendered browser accessibility has not passed.")
    if extractable is not GateStatus.PASS:
        warnings.append("Scrapable product text has not passed.")
    if coding is not GateStatus.PASS:
        warnings.append("Some downstream coding fields are incomplete.")
    if country is not GateStatus.PASS:
        warnings.append("Country-market alignment is not fully confirmed.")
    if retailer is GateStatus.FAIL:
        warnings.append("Requested-retailer alignment did not pass.")
    return warnings


def _identity_text(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, Mapping):
            parts.extend(str(item) for item in value.values())
        elif value not in (None, ""):
            parts.append(str(value))
    return " ".join(" ".join(parts).split())


def _field_identifiers(fields: Mapping[str, str]) -> set[str]:
    values: set[str] = set()
    for key, value in fields.items():
        if not key.casefold().startswith(("gtin", "ean", "isbn")):
            continue
        digits = re.sub(r"\D", "", str(value))
        if len(digits) in {8, 12, 13, 14}:
            values.add(digits)
    return values


def _page_identifiers(text: str, fields: Mapping[str, str]) -> set[str]:
    values = _field_identifiers(fields)
    values.update(match.group(1) for match in _LABELED_IDENTIFIER_PATTERN.finditer(text))
    # JSON-LD and many retailer detail tables expose a bare identifier. Retain
    # valid-length values, but exact mapping still requires all other page gates.
    values.update(match.group(1) for match in _IDENTIFIER_PATTERN.finditer(text))
    return values


def _domain_matches_entity(domain: str, names: Sequence[str]) -> bool:
    compact_domain = re.sub(r"[^a-z0-9]", "", domain.casefold())
    for name in names:
        compact_name = re.sub(r"[^a-z0-9]", "", str(name).casefold())
        if len(compact_name) >= 4 and compact_name in compact_domain:
            return True
        tokens = [token for token in re.findall(r"[a-z0-9]+", str(name).casefold()) if len(token) >= 4]
        if any(token in compact_domain for token in tokens):
            return True
    return False
