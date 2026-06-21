from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Sentinel strings from pandas/CSV that should be treated as "no value"
_BLANK_STRINGS: frozenset[str] = frozenset({"", "none", "nan", "null", "n/a", "na"})


def _clean_str(val: Any) -> Optional[str]:
    """Normalise any pandas-style null (NaN, None, 'None', 'nan', '') to None."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    s = str(val).strip()
    return None if s.lower() in _BLANK_STRINGS else (s or None)


def _clean_ean(val: Any) -> Optional[str]:
    """Like _clean_str but also strips the trailing .0 pandas adds to numeric EANs."""
    s = _clean_str(val)
    if s is None:
        return None
    # pandas reads integer EANs as float64 → "196214141070.0" → "196214141070"
    if s.endswith(".0"):
        s = s[:-2]
    return s or None


@dataclass(frozen=True)
class ProductQuery:
    """Input contract for one product URL lookup.

    Required:
        main_text:    Product title / description. Strongest discovery signal.
        country_code: Target market (e.g. "CZ", "DE", "US"). Drives the SerpAPI
                      ``gl`` parameter, query planning and country scoring.

    Optional:
        retailer_name: Preferred retailer. Biases candidate selection when given.
        ean:           EAN / GTIN barcode. Strongest identity evidence when given.
        language_code: Language override (e.g. "de" for German in Switzerland).
                      If None, auto-derived from country_code via mapping.
        region:        Region/subdivision for multi-language countries 
                      (e.g. "Romandy" for French-speaking Switzerland).
    """

    main_text: str
    country_code: str
    row_id: str = "demo-001"
    retailer_name: Optional[str] = None
    ean: Optional[str] = None
    language_code: Optional[str] = None
    region: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.main_text or not self.main_text.strip():
            raise ValueError("main_text is mandatory and cannot be empty.")
        if not self.country_code or not self.country_code.strip():
            raise ValueError("country_code is mandatory and cannot be empty.")
        # Sanitize optional fields so pandas NaN / float EANs / "None" strings
        # never leak into query strings or comparison logic.
        object.__setattr__(self, "ean", _clean_ean(self.ean))
        object.__setattr__(self, "retailer_name", _clean_str(self.retailer_name))
        object.__setattr__(self, "language_code", _clean_str(self.language_code))
        object.__setattr__(self, "region", _clean_str(self.region))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_id": self.row_id,
            "main_text": self.main_text,
            "ean": self.ean,
            "retailer_name": self.retailer_name,
            "country_code": self.country_code,
            "language_code": self.language_code,
            "region": self.region,
        }


@dataclass(frozen=True)
class BudgetState:
    """Per-product external call budget usage."""

    organic_used: int = 0
    ai_mode_used: int = 0
    max_organic: int = 2
    max_ai_mode: int = 2

    @property
    def organic_remaining(self) -> int:
        return max(0, self.max_organic - self.organic_used)

    @property
    def ai_mode_remaining(self) -> int:
        return max(0, self.max_ai_mode - self.ai_mode_used)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "organic_used": self.organic_used,
            "organic_remaining": self.organic_remaining,
            "max_organic": self.max_organic,
            "ai_mode_used": self.ai_mode_used,
            "ai_mode_remaining": self.ai_mode_remaining,
            "max_ai_mode": self.max_ai_mode,
        }


@dataclass(frozen=True)
class OrganicSearchResult:
    """One organic result from SerpAPI Google Search."""

    url: str
    title: str = ""
    snippet: str = ""
    displayed_link: str = ""
    source: str = ""
    position: Optional[int] = None
    query: str = ""
    search_id: Optional[str] = None
    search_status: str = "Unknown"


@dataclass(frozen=True)
class OrganicSearchResponse:
    """Normalized organic search response."""

    query: str
    search_id: Optional[str]
    status: str
    results: List[OrganicSearchResult]
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIReference:
    """One source/reference returned by SerpAPI AI Mode."""

    title: str = ""
    link: str = ""
    source: str = ""
    snippet: str = ""


@dataclass(frozen=True)
class SerpAIResponse:
    """Normalized SerpAPI AI Mode response."""

    query: str
    status: str
    search_id: Optional[str]
    markdown: str
    text_blocks: List[Any] = field(default_factory=list)
    references: List[AIReference] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class URLCandidate:
    """Candidate URL with evidence from organic and/or AI Mode."""

    url: str
    title: str = ""
    snippet: str = ""
    domain: str = ""
    source_types: tuple[str, ...] = ()
    best_position: Optional[int] = None
    organic_count: int = 0
    ai_reference_count: int = 0
    ai_declared_final: bool = False
    query_sources: tuple[str, ...] = ()

    def evidence_text(self) -> str:
        return " ".join([self.url, self.title, self.snippet, self.domain])


@dataclass(frozen=True)
class AIMatchEvidence:
    final_url: Optional[str]
    match_decision: str
    confidence_reason: str
    ean_evidence: str
    title_evidence: str
    retailer_evidence: str
    country_evidence: str
    product_page_evidence: str
    rejected_candidates: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_url": self.final_url,
            "match_decision": self.match_decision,
            "confidence_reason": self.confidence_reason,
            "ean_evidence": self.ean_evidence,
            "title_evidence": self.title_evidence,
            "retailer_evidence": self.retailer_evidence,
            "country_evidence": self.country_evidence,
            "product_page_evidence": self.product_page_evidence,
            "rejected_candidates": self.rejected_candidates,
        }


@dataclass(frozen=True)
class ScrapeResult:
    """Result of scraping one URL with crawl4ai.

    Proves a URL is genuinely reachable and returns real, product-like content,
    and carries the structured signals (product name, structured EANs, price,
    soft-404 detection) that the identity verifier needs to decide whether the
    scraped page is actually THE requested product.
    """

    url: str
    scraped: bool                 # crawl4ai actually executed for this URL
    success: bool                 # crawl4ai reported a successful crawl
    reachable: bool               # HTTP status looked alive (2xx/3xx or soft-block)
    is_scrapable: bool            # final verdict: scraped AND real content returned
    status_code: Optional[int]
    final_url: Optional[str]
    title: str = ""
    h1: str = ""
    page_product_name: str = ""           # best on-page product name (JSON-LD > H1 > title)
    structured_eans: tuple[str, ...] = ()  # gtin/ean/mpn from JSON-LD structured data
    has_price: bool = False
    availability: str = ""

    # -- information richness (drives "how much product data can be scraped") --
    price: Optional[float] = None                          # numeric price when extractable
    currency: str = ""                                     # ISO/code or symbol of the price
    brand: str = ""                                        # brand name
    manufacturer: str = ""                                 # manufacturer name
    description: str = ""                                  # product description (capped)
    specs: Dict[str, str] = field(default_factory=dict)    # human-facing spec key->value
    image_urls: tuple[str, ...] = ()                       # product image URLs
    attributes: Dict[str, Any] = field(default_factory=dict)  # other structured properties
    richness_score: float = 0.0                            # 0..1 information-richness score

    markdown_excerpt: str = ""
    markdown_chars: int = 0
    word_count: int = 0
    internal_link_count: int = 0
    external_link_count: int = 0
    image_count: int = 0
    looks_like_homepage: bool = False
    looks_like_product_page: bool = False
    is_soft_404: bool = False
    contains_ean: bool = False
    text_overlap: float = 0.0
    verification_text: str = field(default="", repr=False)  # large text body, not serialized
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "scraped": self.scraped,
            "success": self.success,
            "reachable": self.reachable,
            "is_scrapable": self.is_scrapable,
            "status_code": self.status_code,
            "final_url": self.final_url,
            "title": self.title,
            "h1": self.h1,
            "page_product_name": self.page_product_name,
            "structured_eans": list(self.structured_eans),
            "has_price": self.has_price,
            "availability": self.availability,
            "price": self.price,
            "currency": self.currency,
            "brand": self.brand,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "specs": dict(self.specs),
            "image_urls": list(self.image_urls),
            "attributes": dict(self.attributes),
            "richness_score": self.richness_score,
            "markdown_chars": self.markdown_chars,
            "word_count": self.word_count,
            "internal_link_count": self.internal_link_count,
            "external_link_count": self.external_link_count,
            "image_count": self.image_count,
            "looks_like_homepage": self.looks_like_homepage,
            "looks_like_product_page": self.looks_like_product_page,
            "is_soft_404": self.is_soft_404,
            "contains_ean": self.contains_ean,
            "text_overlap": self.text_overlap,
            "error": self.error,
        }


@dataclass(frozen=True)
class MatchVerification:
    """Verdict on whether a scraped page is genuinely the requested product.

    This is the layer that distinguishes a *correct* URL from a merely
    *scrapable* one. It cross-checks the scraped content against the requested
    identity: EAN/GTIN, distinctive title tokens, pack-size / quantity, brand
    and page type (real PDP vs soft-404).
    """

    url: str
    identity_status: str          # VERIFIED | PROBABLE | WEAK | MISMATCH | UNVERIFIED
    ean_check: str                # MATCHED | CONFLICT | ABSENT | NOT_PROVIDED
    title_check: str              # STRONG | PARTIAL | WEAK
    quantity_check: str           # MATCHED | CONFLICT | UNKNOWN | NOT_APPLICABLE
    brand_check: str              # MATCHED | ABSENT | NOT_APPLICABLE
    page_type_check: str          # PRODUCT_DETAIL | SOFT_404 | NON_PRODUCT | UNKNOWN
    title_match_score: float
    requested_quantity: Optional[str] = None
    page_quantity: Optional[str] = None
    requested_ean: Optional[str] = None
    page_eans: tuple[str, ...] = ()
    matched_tokens: tuple[str, ...] = ()
    missing_tokens: tuple[str, ...] = ()
    justifications: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()

    @property
    def is_acceptable(self) -> bool:
        """True only for verdicts the pipeline may return (subject to config)."""
        return self.identity_status in {"VERIFIED", "PROBABLE"}

    @property
    def has_hard_justification(self) -> bool:
        """True when a high-confidence claim is backed by hard evidence."""
        if self.ean_check == "MATCHED":
            return True
        return self.quantity_check == "MATCHED" and self.title_check == "STRONG"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "identity_status": self.identity_status,
            "ean_check": self.ean_check,
            "title_check": self.title_check,
            "quantity_check": self.quantity_check,
            "brand_check": self.brand_check,
            "page_type_check": self.page_type_check,
            "title_match_score": self.title_match_score,
            "requested_quantity": self.requested_quantity,
            "page_quantity": self.page_quantity,
            "requested_ean": self.requested_ean,
            "page_eans": list(self.page_eans),
            "matched_tokens": list(self.matched_tokens),
            "missing_tokens": list(self.missing_tokens),
            "justifications": list(self.justifications),
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class ConfidenceComponent:
    """One decomposed contributor to the final confidence score."""

    name: str
    raw_score: float
    weight: float
    contribution: float
    justification: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "raw_score": round(self.raw_score, 4),
            "weight": round(self.weight, 4),
            "contribution": round(self.contribution, 4),
            "justification": self.justification,
        }


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Full, auditable decomposition of a candidate's confidence.

    Designed to be submitted for downstream validation: it shows every scoring
    component and its contribution, every cap applied (with reason), the base
    vs final confidence, and the resulting validation status.
    """

    base_confidence: float
    final_confidence: float
    validation_status: str
    components: tuple[ConfidenceComponent, ...] = ()
    caps_applied: tuple[Dict[str, Any], ...] = ()
    justification_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_confidence": round(self.base_confidence, 4),
            "final_confidence": round(self.final_confidence, 4),
            "validation_status": self.validation_status,
            "components": [component.to_dict() for component in self.components],
            "caps_applied": list(self.caps_applied),
            "justification_summary": self.justification_summary,
        }


@dataclass(frozen=True)
class ScoredURLCandidate:
    candidate: URLCandidate
    confidence: float
    is_exact_product_match: bool
    reason: str
    score_breakdown: Dict[str, float]
    scrape: Optional[ScrapeResult] = None
    verification: Optional[MatchVerification] = None
    confidence_breakdown: Optional[ConfidenceBreakdown] = None
    retailer_check: str = "NOT_PROVIDED"  # MATCHED | ALTERNATIVE | NOT_PROVIDED
    country_check: str = "NOT_PROVIDED"   # MATCHED | ALTERNATIVE | NOT_PROVIDED


@dataclass(frozen=True)
class ProductURLMatch:
    """Final one-URL output."""

    row_id: str
    main_text: str
    ean: Optional[str]
    retailer_name: Optional[str]
    country_code: Optional[str]

    product_url: Optional[str]
    confidence: float
    is_exact_product_match: bool
    match_reason: str

    # Identity verification + submission status.
    validation_status: str        # VERIFIED | NEEDS_REVIEW | REJECTED | NO_MATCH
    identity_status: str          # VERIFIED | PROBABLE | WEAK | MISMATCH | UNVERIFIED | NONE
    justification: str            # consolidated, human-readable evidence (required if high conf)
    ean_check: str
    title_check: str
    quantity_check: str
    page_type_check: str
    retailer_check: str           # MATCHED | ALTERNATIVE | NOT_PROVIDED
    country_check: str            # MATCHED | ALTERNATIVE | NOT_PROVIDED
    requested_quantity: Optional[str]
    page_quantity: Optional[str]
    blocking_reasons: str

    ai_match_decision: str
    ai_confidence_reason: str
    ean_evidence: str
    title_evidence: str
    retailer_evidence: str
    country_evidence: str
    product_page_evidence: str

    organic_calls_used: int
    ai_mode_calls_used: int
    repair_used: bool
    is_scrapable: bool
    scrape_status_code: Optional[int]
    scrape_word_count: int
    scrape_markdown_chars: int
    scrape_final_url: Optional[str]

    # Information richness — how many useful product attributes were extracted
    # from the verified page (drives selection among correct, scrapable pages).
    richness_score: float = 0.0
    price: Optional[float] = None
    currency: str = ""
    brand: str = ""
    manufacturer: str = ""
    description: str = ""
    specs_count: int = 0
    image_count: int = 0
    specs: Dict[str, str] = field(default_factory=dict)
    image_urls: tuple[str, ...] = ()

    confidence_breakdown: Optional[ConfidenceBreakdown] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_id": self.row_id,
            "main_text": self.main_text,
            "ean": self.ean,
            "retailer_name": self.retailer_name,
            "country_code": self.country_code,
            "product_url": self.product_url,
            "confidence": self.confidence,
            "validation_status": self.validation_status,
            "identity_status": self.identity_status,
            "is_exact_product_match": self.is_exact_product_match,
            "justification": self.justification,
            "match_reason": self.match_reason,
            "ean_check": self.ean_check,
            "title_check": self.title_check,
            "quantity_check": self.quantity_check,
            "page_type_check": self.page_type_check,
            "retailer_check": self.retailer_check,
            "country_check": self.country_check,
            "requested_quantity": self.requested_quantity,
            "page_quantity": self.page_quantity,
            "blocking_reasons": self.blocking_reasons,
            "ai_match_decision": self.ai_match_decision,
            "ai_confidence_reason": self.ai_confidence_reason,
            "ean_evidence": self.ean_evidence,
            "title_evidence": self.title_evidence,
            "retailer_evidence": self.retailer_evidence,
            "country_evidence": self.country_evidence,
            "product_page_evidence": self.product_page_evidence,
            "organic_calls_used": self.organic_calls_used,
            "ai_mode_calls_used": self.ai_mode_calls_used,
            "repair_used": self.repair_used,
            "is_scrapable": self.is_scrapable,
            "scrape_status_code": self.scrape_status_code,
            "scrape_word_count": self.scrape_word_count,
            "scrape_markdown_chars": self.scrape_markdown_chars,
            "scrape_final_url": self.scrape_final_url,
            "richness_score": self.richness_score,
            "price": self.price,
            "currency": self.currency,
            "brand": self.brand,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "specs_count": self.specs_count,
            "image_count": self.image_count,
            "specs": dict(self.specs),
            "image_urls": list(self.image_urls),
            "confidence_breakdown": (
                self.confidence_breakdown.to_dict() if self.confidence_breakdown else None
            ),
        }


@dataclass(frozen=True)
class PipelineTrace:
    product_query: ProductQuery
    budget: BudgetState
    organic_queries: List[str]
    organic_responses: List[OrganicSearchResponse]
    candidates: List[URLCandidate]
    ai_validation_query: str
    ai_validation_response: SerpAIResponse
    ai_validation_evidence: AIMatchEvidence
    repair_query: Optional[str]
    repair_response: Optional[SerpAIResponse]
    repair_evidence: Optional[AIMatchEvidence]
    scored_candidates: List[ScoredURLCandidate]
    scrapes: Dict[str, ScrapeResult]
    verifications: Dict[str, MatchVerification]
    best_match: ProductURLMatch
