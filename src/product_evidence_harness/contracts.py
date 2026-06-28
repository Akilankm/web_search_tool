from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional

from src.product_evidence_harness.constants import (
    CHECK_UNKNOWN, COUNTRY_NOT_PROVIDED, RETAILER_NOT_PROVIDED,
)

_BLANK_STRINGS = frozenset({"", "none", "nan", "null", "n/a", "na"})


def clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return None if text.lower() in _BLANK_STRINGS else text


def clean_ean(value: Any) -> Optional[str]:
    """Return an EAN/GTIN as text.

    EANs are identifiers, not numbers. This function avoids normal numeric
    formatting and handles common spreadsheet artifacts. If an input file has
    already destroyed precision by saving an EAN in scientific notation, exact
    recovery is not guaranteed; CSV/Excel readers therefore load EAN columns as
    strings before this function is called.
    """
    text = clean_str(value)
    if text is None:
        return None
    text = text.strip()
    if re.search(r"^[0-9]+(?:\.0+)?$", text):
        if text.endswith(".0"):
            text = text[:-2]
        return "".join(ch for ch in text if ch.isdigit()) or None
    if re.search(r"^[0-9]+(?:\.[0-9]+)?[eE][+-]?[0-9]+$", text):
        # Scientific notation means a spreadsheet may already have destroyed
        # significant trailing digits. Do not silently manufacture a GTIN.
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or None


class DiscoveryMode(str, Enum):
    STRICT_PRODUCT_URL = "strict_product_url"
    PRODUCT_EVIDENCE = "product_evidence"


class ActionType(str, Enum):
    LLM_SEARCH_PLAN = "llm_search_plan"
    LLM_SEARCH_FEEDBACK = "llm_search_feedback"
    LLM_EXACT_ADJUDICATION = "llm_exact_adjudication"
    ORGANIC_SEARCH = "organic_search"
    AI_MODE_SEARCH = "ai_mode_search"
    SCRAPE_URL = "scrape_url"
    FINISH = "finish"


@dataclass(frozen=True)
class ProductQuery:
    main_text: str
    country_code: str
    row_id: str = "demo-001"
    retailer_name: Optional[str] = None
    ean: Optional[str] = None
    language_code: Optional[str] = None
    region: Optional[str] = None
    input_validation_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.main_text or not self.main_text.strip():
            raise ValueError("main_text is mandatory and cannot be empty")
        if not self.country_code or not self.country_code.strip():
            raise ValueError("country_code is mandatory and cannot be empty")
        object.__setattr__(self, "country_code", self.country_code.strip().upper())
        object.__setattr__(self, "retailer_name", clean_str(self.retailer_name))
        warnings = []
        raw_ean_text = clean_str(self.ean)
        if raw_ean_text and re.search(r"^[0-9]+(?:\.[0-9]+)?[eE][+-]?[0-9]+$", raw_ean_text.strip()):
            warnings.append("EAN_SCIENTIFIC_NOTATION_LOSS_RISK: provide EAN as text; value was not used for exact matching")
        object.__setattr__(self, "ean", clean_ean(self.ean))
        object.__setattr__(self, "input_validation_warnings", tuple(warnings))
        object.__setattr__(self, "language_code", clean_str(self.language_code))
        object.__setattr__(self, "region", clean_str(self.region))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrganicSearchResult:
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
    query: str
    search_id: Optional[str]
    status: str
    results: list[OrganicSearchResult]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIReference:
    title: str = ""
    link: str = ""
    source: str = ""
    snippet: str = ""


@dataclass(frozen=True)
class SerpAIResponse:
    query: str
    status: str
    search_id: Optional[str]
    markdown: str
    text_blocks: list[Any] = field(default_factory=list)
    references: list[AIReference] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class URLCandidate:
    url: str
    title: str = ""
    snippet: str = ""
    domain: str = ""
    source_types: tuple[str, ...] = ()
    query_sources: tuple[str, ...] = ()
    best_position: Optional[int] = None
    organic_count: int = 0
    ai_reference_count: int = 0
    ai_declared_final: bool = False
    lifecycle_status: str = "DISCOVERED"

    def evidence_text(self) -> str:
        return " ".join([self.url, self.title, self.snippet, self.domain])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScrapeResult:
    url: str
    scraped: bool
    success: bool
    reachable: bool
    is_scrapable: bool
    status_code: Optional[int]
    final_url: Optional[str]
    title: str = ""
    h1: str = ""
    page_product_name: str = ""
    structured_eans: tuple[str, ...] = ()
    has_price: bool = False
    price: Optional[float] = None
    currency: str = ""
    availability: str = ""
    brand: str = ""
    manufacturer: str = ""
    description: str = ""
    specs: dict[str, str] = field(default_factory=dict)
    image_urls: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)
    richness_score: float = 0.0
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
    links: tuple[str, ...] = ()
    verification_text: str = field(default="", repr=False)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("verification_text", None)
        return data


@dataclass(frozen=True)
class ProductEvidence:
    source_url: str
    source_type: str
    product_title: Optional[str] = None
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    ean: Optional[str] = None
    sku: Optional[str] = None
    pack_size: Optional[str] = None
    price: Optional[float] = None
    currency: str = ""
    availability: str = ""
    description: str = ""
    specs: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MatchVerification:
    url: str
    identity_status: str
    ean_check: str
    title_check: str
    quantity_check: str
    brand_check: str
    page_type_check: str
    title_match_score: float
    exact_product_check: str = "UNKNOWN"
    variant_check: str = "UNKNOWN"
    variant_conflict_terms: tuple[str, ...] = ()
    identity_driver: str = "UNKNOWN"
    ean_status: str = "UNKNOWN"
    ean_conflict_is_blocking: bool = False
    input_ean_valid: Optional[bool] = None
    input_ean_normalized: Optional[str] = None
    page_gtins_valid: tuple[str, ...] = ()
    page_gtins_ignored: tuple[str, ...] = ()
    requested_quantity: Optional[str] = None
    page_quantity: Optional[str] = None
    requested_ean: Optional[str] = None
    page_eans: tuple[str, ...] = ()
    matched_tokens: tuple[str, ...] = ()
    missing_tokens: tuple[str, ...] = ()
    justifications: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    detector_findings: tuple[dict[str, Any], ...] = ()

    @property
    def has_hard_justification(self) -> bool:
        return self.ean_check == "MATCHED" or (
            self.title_check == "STRONG" and self.quantity_check in {"MATCHED", "NOT_APPLICABLE", "UNKNOWN"}
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMJudgement:
    url: str
    decision: str = "NOT_EVALUATED"
    exact_product_match: bool = False
    confidence: float = 0.0
    primary_identity_driver: str = "UNKNOWN"
    main_text_status: str = "UNKNOWN"
    ean_status: str = "UNKNOWN"
    variant_status: str = "UNKNOWN"
    scrape_usable: bool = False
    image_used: bool = False
    image_url: Optional[str] = None
    image_status: str = "NOT_USED"
    recommended_next_action: str = "UNKNOWN"
    reject_reason: Optional[str] = None
    final_explanation: str = ""
    payload_level: str = "NONE"
    call_index: int = 0
    gateway_retry: bool = False
    raw_response: str = ""
    error: Optional[str] = None

    @property
    def accepted_for_final(self) -> bool:
        return self.decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"} and self.exact_product_match

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMCallRecord:
    row_id: str
    url: str
    call_index: int
    payload_level: str
    image_used: bool
    image_url: Optional[str]
    success: bool
    decision: str = "UNKNOWN"
    error: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMSearchQuery:
    query: str
    source: str = "llm_search_plan"
    scope: str = "country"
    reason: str = ""
    priority: int = 1
    language_code: Optional[str] = None
    language_name: Optional[str] = None
    must_include_ean: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LLMSearchPlan:
    row_id: str
    call_index: int
    stage: str
    expanded_main_text: str = ""
    critical_terms: tuple[str, ...] = ()
    variant_terms_to_preserve: tuple[str, ...] = ()
    negative_terms: tuple[str, ...] = ()
    queries: tuple[LLMSearchQuery, ...] = ()
    reasoning: str = ""
    payload_level: str = "search_plan"
    success: bool = True
    error: Optional[str] = None
    raw_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["queries"] = [q.to_dict() for q in self.queries]
        return data


@dataclass(frozen=True)
class CandidateScorecard:
    candidate: URLCandidate
    organic_score: float
    ai_score: float
    retailer_score: float
    country_score: float
    ean_score: float
    title_score: float
    product_page_score: float
    scrape_score: float
    identity_score: float
    richness_score: float
    weighted_confidence: float
    confidence_cap: float
    final_confidence: float
    validation_status: str
    hard_failures: tuple[str, ...] = ()
    soft_warnings: tuple[str, ...] = ()
    ranking_reasons: tuple[str, ...] = ()
    scrape: Optional[ScrapeResult] = None
    verification: Optional[MatchVerification] = None
    retailer_check: str = "NOT_PROVIDED"
    country_check: str = "NOT_PROVIDED"
    exact_product_check: str = "UNKNOWN"
    variant_check: str = "UNKNOWN"
    identity_driver: str = "UNKNOWN"
    selected_with_warning: bool = False
    primary_reject_reason: str = ""
    llm_judgement: Optional[LLMJudgement] = None
    best_available_url: Optional[str] = None
    verified_exact_url: Optional[str] = None
    url_decision_status: str = "UNRESOLVED"
    is_global_fallback: bool = False
    is_country_specific: bool = False
    needs_review: bool = False
    llm_used: bool = False
    llm_decision: str = "NOT_EVALUATED"
    llm_confidence: float = 0.0
    llm_exact_product_match: bool = False
    llm_reject_reason: str = ""
    llm_justification: str = ""


    @property
    def confidence(self) -> float:
        return self.final_confidence

    @property
    def is_exact_product_match(self) -> bool:
        return self.validation_status == "VERIFIED"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["candidate"] = self.candidate.to_dict()
        data["scrape"] = self.scrape.to_dict() if self.scrape else None
        data["verification"] = self.verification.to_dict() if self.verification else None
        return data


# Backwards-compatible name for old scripts/tests that expected ScoredURLCandidate.
ScoredURLCandidate = CandidateScorecard


@dataclass(frozen=True)
class SearchBudgetSnapshot:
    organic_used: int
    ai_mode_used: int
    scrape_used: int
    max_organic: int
    max_ai_mode: int
    max_scrapes: int

    @property
    def organic_remaining(self) -> int:
        return max(0, self.max_organic - self.organic_used)

    @property
    def ai_mode_remaining(self) -> int:
        return max(0, self.max_ai_mode - self.ai_mode_used)

    @property
    def scrape_remaining(self) -> int:
        return max(0, self.max_scrapes - self.scrape_used)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "organic_remaining": self.organic_remaining,
            "ai_mode_remaining": self.ai_mode_remaining,
            "scrape_remaining": self.scrape_remaining,
        }


@dataclass(frozen=True)
class AgentAction:
    action_type: ActionType
    reason: str
    query: Optional[str] = None
    url: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type.value,
            "reason": self.reason,
            "query": self.query,
            "url": self.url,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AgentActionRecord:
    iteration: int
    action: AgentAction
    success: bool
    output_summary: dict[str, Any]
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "action": self.action.to_dict(),
            "success": self.success,
            "output_summary": dict(self.output_summary),
            "error": self.error,
        }


@dataclass
class ProductSearchState:
    task: ProductQuery
    budget: Any
    iteration: int = 0
    queries: list[str] = field(default_factory=list)
    organic_responses: list[OrganicSearchResponse] = field(default_factory=list)
    ai_responses: list[SerpAIResponse] = field(default_factory=list)
    candidates: list[URLCandidate] = field(default_factory=list)
    scrapes: dict[str, ScrapeResult] = field(default_factory=dict)
    evidence_cards: list[ProductEvidence] = field(default_factory=list)
    verifications: dict[str, MatchVerification] = field(default_factory=dict)
    scorecards: list[CandidateScorecard] = field(default_factory=list)
    actions_taken: list[AgentActionRecord] = field(default_factory=list)
    termination_reason: Optional[str] = None
    final_result: Optional["ProductURLMatch"] = None
    llm_judgements: dict[str, LLMJudgement] = field(default_factory=dict)
    llm_call_records: list[LLMCallRecord] = field(default_factory=list)
    llm_search_plans: list[LLMSearchPlan] = field(default_factory=list)
    planned_search_queries: list[LLMSearchQuery] = field(default_factory=list)
    identity_graph: Any = None
    detector_findings: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def best_scorecard(self) -> Optional[CandidateScorecard]:
        return self.scorecards[0] if self.scorecards else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "budget": self.budget.snapshot().to_dict() if hasattr(self.budget, "snapshot") else None,
            "iteration": self.iteration,
            "queries": list(self.queries),
            "candidates": [c.to_dict() for c in self.candidates],
            "scrapes": {k: v.to_dict() for k, v in self.scrapes.items()},
            "evidence_cards": [e.to_dict() for e in self.evidence_cards],
            "verifications": {k: v.to_dict() for k, v in self.verifications.items()},
            "scorecards": [s.to_dict() for s in self.scorecards],
            "actions_taken": [a.to_dict() for a in self.actions_taken],
            "termination_reason": self.termination_reason,
            "final_result": self.final_result.to_dict() if self.final_result else None,
            "llm_judgements": {k: v.to_dict() for k, v in self.llm_judgements.items()},
            "llm_call_records": [r.to_dict() for r in self.llm_call_records],
            "llm_search_plans": [p.to_dict() for p in self.llm_search_plans],
            "planned_search_queries": [q.to_dict() for q in self.planned_search_queries],
            "identity_graph": self.identity_graph.to_dict() if hasattr(self.identity_graph, "to_dict") else self.identity_graph,
            "detector_findings": dict(self.detector_findings),
        }


@dataclass(frozen=True)
class ProductURLMatch:
    row_id: str
    main_text: str
    country_code: str
    retailer_name: Optional[str]
    ean: Optional[str]
    product_url: Optional[str]
    confidence: float
    validation_status: str
    identity_status: str
    is_exact_product_match: bool
    match_reason: str
    justification: str
    ean_check: str = CHECK_UNKNOWN
    title_check: str = CHECK_UNKNOWN
    quantity_check: str = CHECK_UNKNOWN
    page_type_check: str = CHECK_UNKNOWN
    retailer_check: str = RETAILER_NOT_PROVIDED
    country_check: str = COUNTRY_NOT_PROVIDED
    requested_quantity: Optional[str] = None
    page_quantity: Optional[str] = None
    blocking_reasons: str = ""
    hard_failures: tuple[str, ...] = ()
    soft_warnings: tuple[str, ...] = ()
    termination_reason: Optional[str] = None
    organic_calls_used: int = 0
    ai_mode_calls_used: int = 0
    scrape_calls_used: int = 0
    is_scrapable: bool = False
    scrape_status_code: Optional[int] = None
    scrape_word_count: int = 0
    scrape_markdown_chars: int = 0
    scrape_final_url: Optional[str] = None
    richness_score: float = 0.0
    price: Optional[float] = None
    currency: str = ""
    brand: str = ""
    manufacturer: str = ""
    description: str = ""
    specs_count: int = 0
    image_count: int = 0
    specs: dict[str, str] = field(default_factory=dict)
    image_urls: tuple[str, ...] = ()
    resolution_status: str = "UNRESOLVED"
    availability_inference: str = "UNKNOWN"
    exact_product_check: str = "UNKNOWN"
    variant_check: str = "UNKNOWN"
    variant_conflict_terms: tuple[str, ...] = ()
    identity_driver: str = "UNKNOWN"
    ean_status: str = "UNKNOWN"
    ean_conflict_is_blocking: bool = False
    input_ean_valid: Optional[bool] = None
    input_ean_normalized: Optional[str] = None
    page_gtins_valid: tuple[str, ...] = ()
    page_gtins_ignored: tuple[str, ...] = ()
    selected_with_warning: bool = False
    primary_reject_reason: str = ""
    best_available_url: Optional[str] = None
    verified_exact_url: Optional[str] = None
    url_decision_status: str = "UNRESOLVED"
    is_global_fallback: bool = False
    is_country_specific: bool = False
    needs_review: bool = False
    llm_used: bool = False
    llm_decision: str = "NOT_EVALUATED"
    llm_confidence: float = 0.0
    llm_exact_product_match: bool = False
    llm_reject_reason: str = ""
    llm_justification: str = ""
    llm_calls_used: int = 0
    best_reference_url: Optional[str] = None
    reference_url_status: str = ""
    input_validation_status: str = "OK"
    input_validation_warnings: tuple[str, ...] = ()
    requested_retailer_name: Optional[str] = None
    requested_retailer_attempted: bool = False
    requested_retailer_domains_found: tuple[str, ...] = ()
    requested_retailer_candidates_found: int = 0
    requested_retailer_candidates_scraped: int = 0
    requested_retailer_scrape_success_count: int = 0
    requested_retailer_rich_pages_count: int = 0
    requested_retailer_exact_candidates_count: int = 0
    requested_retailer_scrapability_status: str = "NOT_PROVIDED"
    requested_retailer_escape_reason: str = ""
    selection_scope: str = "UNRESOLVED"
    selected_retailer_name: str = ""
    selected_domain: str = ""
    selected_from_requested_retailer: bool = False
    selected_from_other_country_retailer: bool = False
    selected_from_global_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HarnessTrace:
    state: ProductSearchState
    best_match: ProductURLMatch

    @property
    def scored_candidates(self) -> list[CandidateScorecard]:
        return self.state.scorecards

    @property
    def scrapes(self) -> dict[str, ScrapeResult]:
        return self.state.scrapes

    @property
    def verifications(self) -> dict[str, MatchVerification]:
        return self.state.verifications

    @property
    def candidates(self) -> list[URLCandidate]:
        return self.state.candidates

    def to_dict(self) -> dict[str, Any]:
        return {"best_match": self.best_match.to_dict(), "state": self.state.to_dict()}


# Backwards-compatible alias for previous API name.
PipelineTrace = HarnessTrace
BudgetState = SearchBudgetSnapshot
