from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.product_evidence_harness.contracts import (
    CandidateScorecard,
    MatchVerification,
    ProductQuery,
    ScrapeResult,
    URLCandidate,
)
from src.product_evidence_harness.url_utils import domain_of, normalize_url


TRACKING_QUERY_NAMES = {
    "fbclid",
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_",
    "source",
    "campaign",
    "session",
    "sessionid",
    "sid",
}
TRACKING_QUERY_PREFIXES = ("utm_", "pk_", "ga_", "trk_")
IDENTITY_QUERY_NAMES = {
    "id",
    "item",
    "itemid",
    "pid",
    "product",
    "productid",
    "sku",
    "ean",
    "gtin",
    "variant",
}
BLOCKED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".mp4",
    ".avi",
    ".zip",
}
SOCIAL_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "reddit.com",
}
SEARCH_SEGMENTS = {
    "search",
    "suche",
    "buscar",
    "recherche",
    "ricerca",
    "hledat",
    "wyszukiwarka",
    "catalogsearch",
}
CATEGORY_SEGMENTS = {
    "category",
    "categories",
    "collection",
    "collections",
    "catalog",
    "shop",
    "products",
    "produkty",
    "kategorie",
    "brands",
    "brand",
    "offers",
    "deals",
}
PRODUCT_SEGMENTS = {
    "product",
    "produkt",
    "producto",
    "produit",
    "prodotto",
    "item",
    "p",
    "dp",
    "sku",
    "detail",
    "product-detail",
}
RELEVANCE_STOP_WORDS = {
    "and",
    "the",
    "with",
    "from",
    "for",
    "pack",
    "product",
    "toy",
    "new",
    "set",
}


@dataclass(frozen=True, slots=True)
class CandidateAdmission:
    original_url: str
    canonical_url: str
    domain: str
    url_type: str
    preflight_score: float
    identity_overlap: float
    ean_signal: bool
    retailer_signal: bool
    product_path_signal: bool
    admitted_for_scrape: bool
    admission_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContentUtility:
    fetch_success: bool
    content_extracted: bool
    probable_product_page: bool
    identity_evidence_sufficient: bool
    feature_evidence_count: int
    content_utility_score: float
    scrape_accepted: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonicalize_candidate_url(url: str) -> str:
    """Return a stable URL identity while preserving product-defining parameters."""
    normalized = normalize_url(url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        return ""
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")

    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        folded = key.strip().lower()
        if folded in TRACKING_QUERY_NAMES or folded.startswith(TRACKING_QUERY_PREFIXES):
            continue
        if folded in IDENTITY_QUERY_NAMES:
            kept.append((folded, value.strip()))
    query = urlencode(sorted(dict.fromkeys(kept)))
    return urlunparse((parsed.scheme.lower(), netloc, path, "", query, ""))


def classify_candidate_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = (parsed.path or "/").lower()
    suffix_match = re.search(r"(\.[a-z0-9]{2,5})$", path)
    suffix = suffix_match.group(1) if suffix_match else ""
    if suffix in BLOCKED_EXTENSIONS:
        return "DOCUMENT_OR_MEDIA"
    if any(host == item or host.endswith("." + item) for item in SOCIAL_DOMAINS):
        return "SOCIAL_OR_COMMUNITY"
    if path in {"", "/"}:
        return "HOMEPAGE"

    segments = [segment for segment in path.split("/") if segment]
    query_names = {key.lower() for key, _ in parse_qsl(parsed.query)}
    if any(segment in SEARCH_SEGMENTS for segment in segments) or "q" in query_names or "query" in query_names:
        return "SEARCH_RESULTS"
    if any(segment in CATEGORY_SEGMENTS for segment in segments):
        # A final long slug under /products/... or /shop/... can still be a PDP.
        final = segments[-1] if segments else ""
        if len(segments) >= 2 and len(final) >= 10 and re.search(r"[a-z0-9].*[-_]", final):
            return "PRODUCT_DETAIL_LIKELY"
        return "CATEGORY_OR_COLLECTION"
    if any(segment in PRODUCT_SEGMENTS for segment in segments):
        return "PRODUCT_DETAIL_LIKELY"
    if any(name in query_names for name in IDENTITY_QUERY_NAMES):
        return "PRODUCT_DETAIL_LIKELY"
    final = segments[-1] if segments else ""
    if len(segments) >= 2 and len(final) >= 10 and any(ch.isdigit() for ch in final):
        return "PRODUCT_DETAIL_LIKELY"
    if len(segments) >= 2 and len(final) >= 14 and ("-" in final or "_" in final):
        return "UNKNOWN_PRODUCT_LIKE"
    return "UNKNOWN"


def candidate_identity_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token
            for token in re.findall(r"[a-z0-9À-ž]+", (text or "").lower())
            if len(token) > 2 and token not in RELEVANCE_STOP_WORDS
        )
    )


class CandidatePrecisionGate:
    """Deterministic admission policy before full scraping and LLM browsing."""

    blocked_url_types = {
        "DOCUMENT_OR_MEDIA",
        "SOCIAL_OR_COMMUNITY",
        "HOMEPAGE",
        "SEARCH_RESULTS",
        "CATEGORY_OR_COLLECTION",
    }

    def __init__(
        self,
        *,
        minimum_score: float = 0.28,
        maximum_full_scrapes: int = 6,
        maximum_per_domain: int = 2,
    ) -> None:
        self.minimum_score = max(0.05, min(0.95, float(minimum_score)))
        self.maximum_full_scrapes = max(1, min(20, int(maximum_full_scrapes)))
        self.maximum_per_domain = max(1, min(5, int(maximum_per_domain)))

    def evaluate(self, product: ProductQuery, candidate: URLCandidate) -> CandidateAdmission:
        canonical = canonicalize_candidate_url(candidate.url)
        url_type = classify_candidate_url(canonical or candidate.url)
        evidence = " ".join(
            [canonical or candidate.url, candidate.title, candidate.snippet, candidate.domain]
        ).lower()
        tokens = candidate_identity_tokens(product.main_text)
        overlap = sum(1 for token in tokens if token in evidence) / max(1, len(tokens))
        digits = re.sub(r"\D", "", evidence)
        ean_signal = bool(product.ean and product.ean in digits)
        retailer_folded = re.sub(r"\W", "", (product.retailer_name or "").lower())
        retailer_signal = bool(
            retailer_folded and retailer_folded in re.sub(r"\W", "", evidence)
        )
        product_path_signal = url_type in {"PRODUCT_DETAIL_LIKELY", "UNKNOWN_PRODUCT_LIKE"}
        position_score = 1.0 / max(1, min(20, candidate.best_position or 20))
        source_score = min(1.0, len(candidate.source_types) / 3)
        score = (
            0.55 * overlap
            + 0.25 * float(ean_signal)
            + 0.08 * float(retailer_signal)
            + 0.07 * float(product_path_signal)
            + 0.03 * source_score
            + 0.02 * position_score
        )
        score = round(min(1.0, score), 4)

        if not canonical:
            admitted, reason = False, "SERP_REJECTED_INVALID_URL"
        elif url_type in self.blocked_url_types:
            admitted, reason = False, f"SERP_REJECTED_URL_TYPE:{url_type}"
        elif ean_signal:
            admitted, reason = True, "QUALIFIED_EXACT_EAN_SIGNAL"
        elif overlap < 0.18:
            admitted, reason = False, "SERP_REJECTED_LOW_IDENTITY_OVERLAP"
        elif score < self.minimum_score:
            admitted, reason = False, "SERP_REJECTED_LOW_PREFLIGHT_SCORE"
        elif not product_path_signal and overlap < 0.42:
            admitted, reason = False, "SERP_REJECTED_WEAK_PRODUCT_PAGE_SIGNAL"
        else:
            admitted, reason = True, "QUALIFIED_FOR_FULL_SCRAPE"

        return CandidateAdmission(
            original_url=candidate.url,
            canonical_url=canonical or candidate.url,
            domain=domain_of(canonical or candidate.url),
            url_type=url_type,
            preflight_score=score,
            identity_overlap=round(overlap, 4),
            ean_signal=ean_signal,
            retailer_signal=retailer_signal,
            product_path_signal=product_path_signal,
            admitted_for_scrape=admitted,
            admission_reason=reason,
        )

    def select_for_scrape(
        self,
        *,
        product: ProductQuery,
        candidates: Sequence[URLCandidate],
        already_scraped: Iterable[str],
        maximum_new: int,
    ) -> tuple[list[URLCandidate], dict[str, CandidateAdmission]]:
        already = {canonicalize_candidate_url(url) or url for url in already_scraped}
        evaluated = {candidate.url: self.evaluate(product, candidate) for candidate in candidates}
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                evaluated[candidate.url].admitted_for_scrape,
                evaluated[candidate.url].ean_signal,
                evaluated[candidate.url].preflight_score,
                -(candidate.best_position or 999),
            ),
            reverse=True,
        )
        selected: list[URLCandidate] = []
        domain_counts: dict[str, int] = {}
        limit = max(0, min(int(maximum_new), self.maximum_full_scrapes))
        for candidate in ranked:
            decision = evaluated[candidate.url]
            if len(selected) >= limit:
                break
            if not decision.admitted_for_scrape or decision.canonical_url in already:
                continue
            if domain_counts.get(decision.domain, 0) >= self.maximum_per_domain:
                evaluated[candidate.url] = CandidateAdmission(
                    **{
                        **decision.to_dict(),
                        "admitted_for_scrape": False,
                        "admission_reason": "QUALIFIED_NOT_SCRAPED_DOMAIN_DIVERSITY_CAP",
                    }
                )
                continue
            selected.append(candidate)
            domain_counts[decision.domain] = domain_counts.get(decision.domain, 0) + 1
        return selected, evaluated

    @staticmethod
    def content_utility(
        scrape: ScrapeResult | None,
        verification: MatchVerification | None,
        *,
        feature_evidence_count: int = 0,
    ) -> ContentUtility:
        if scrape is None:
            return ContentUtility(False, False, False, False, 0, 0.0, False, "NOT_SCRAPED")
        fetch_success = bool(scrape.success and scrape.reachable)
        content_extracted = bool(scrape.word_count >= 20 or scrape.markdown_chars >= 400)
        probable_product_page = bool(
            scrape.looks_like_product_page
            and not scrape.looks_like_homepage
            and not scrape.is_soft_404
        )
        identity_status = getattr(verification, "identity_status", "UNVERIFIED")
        identity_sufficient = identity_status in {"VERIFIED", "PROBABLE"}
        score = (
            0.15 * float(fetch_success)
            + 0.15 * float(content_extracted)
            + 0.25 * float(probable_product_page)
            + 0.30 * float(identity_sufficient)
            + 0.10 * min(1.0, max(0.0, scrape.richness_score))
            + 0.05 * min(1.0, feature_evidence_count / 3)
        )
        accepted = bool(
            fetch_success
            and content_extracted
            and probable_product_page
            and identity_status not in {"MISMATCH"}
            and score >= 0.48
        )
        if not fetch_success:
            reason = "SCRAPE_FAILED"
        elif not content_extracted:
            reason = "SCRAPE_LOW_CONTENT"
        elif not probable_product_page:
            reason = "PROBE_REJECTED_NON_PRODUCT"
        elif identity_status == "MISMATCH":
            reason = "IDENTITY_REJECTED"
        elif not accepted:
            reason = "SCRAPE_LOW_UTILITY"
        else:
            reason = "SCRAPE_ACCEPTED"
        return ContentUtility(
            fetch_success=fetch_success,
            content_extracted=content_extracted,
            probable_product_page=probable_product_page,
            identity_evidence_sufficient=identity_sufficient,
            feature_evidence_count=max(0, int(feature_evidence_count)),
            content_utility_score=round(score, 4),
            scrape_accepted=accepted,
            reason=reason,
        )


def browser_candidate_eligible(
    card: CandidateScorecard,
    *,
    coverage: float | None = None,
    missing_features: Sequence[str] = (),
) -> tuple[bool, str]:
    if card.scrape is None:
        return False, "BROWSER_REJECTED_NOT_SCRAPED"
    if card.hard_failures:
        return False, "BROWSER_REJECTED_HARD_FAILURE"
    utility = CandidatePrecisionGate.content_utility(card.scrape, card.verification)
    if not utility.scrape_accepted:
        return False, f"BROWSER_REJECTED_{utility.reason}"
    if card.verification and card.verification.identity_status == "MISMATCH":
        return False, "BROWSER_REJECTED_IDENTITY_MISMATCH"
    if coverage is not None and coverage >= 1.0 and not missing_features:
        return True, "BROWSER_VERIFY_COMPLETE_STATIC_CANDIDATE"
    return True, "BROWSER_ESCALATED_TO_RESOLVE_MISSING_EVIDENCE"
