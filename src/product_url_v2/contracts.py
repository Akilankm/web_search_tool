from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable
from urllib.parse import urlparse


class GateStatus(str, Enum):
    """Observed state of one independently measured gate."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_ASSESSED = "NOT_ASSESSED"


class IdentityMatch(str, Enum):
    """Candidate-level product identity judgment."""

    EXACT = "EXACT"
    PROBABLE = "PROBABLE"
    UNVERIFIED = "UNVERIFIED"
    MISMATCH = "MISMATCH"


class IdentityResolution(str, Enum):
    """Run-level product identity resolution."""

    EXACT = "EXACT"
    PROBABLE = "PROBABLE"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DeliveryStatus(str, Enum):
    """Terminal URL-delivery result."""

    VERIFIED = "VERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"


class SourceRole(str, Enum):
    LOCAL_MANUFACTURER = "LOCAL_MANUFACTURER"
    GLOBAL_MANUFACTURER = "GLOBAL_MANUFACTURER"
    REQUESTED_RETAILER = "REQUESTED_RETAILER"
    COUNTRY_RETAILER = "COUNTRY_RETAILER"
    GLOBAL_RETAILER = "GLOBAL_RETAILER"
    MARKETPLACE = "MARKETPLACE"
    UNKNOWN = "UNKNOWN"


class PipelineStage(str, Enum):
    INTERPRET_INPUT = "INTERPRET_INPUT"
    BUILD_HYPOTHESES = "BUILD_HYPOTHESES"
    SEARCH = "SEARCH"
    ADMIT_CANDIDATES = "ADMIT_CANDIDATES"
    SCRAPE = "SCRAPE"
    BROWSER_INVESTIGATION = "BROWSER_INVESTIGATION"
    EVALUATE = "EVALUATE"
    DELIVER = "DELIVER"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ProductInput:
    row_id: str
    main_text: str
    country_code: str
    retailer_name: str | None = None
    ean: str | None = None
    language_code: str | None = None

    def __post_init__(self) -> None:
        row_id = self.row_id.strip()
        main_text = " ".join(self.main_text.split())
        country_code = self.country_code.strip().upper()
        retailer_name = (self.retailer_name or "").strip() or None
        ean = (self.ean or "").strip() or None
        language_code = (self.language_code or "").strip().lower() or None

        if not row_id:
            raise ValueError("row_id is required")
        if not main_text:
            raise ValueError("main_text is required")
        if len(country_code) != 2 or not country_code.isalpha():
            raise ValueError("country_code must contain exactly two letters")
        if language_code is not None and (
            len(language_code) != 2 or not language_code.isalpha()
        ):
            raise ValueError("language_code must contain exactly two letters")

        object.__setattr__(self, "row_id", row_id)
        object.__setattr__(self, "main_text", main_text)
        object.__setattr__(self, "country_code", country_code)
        object.__setattr__(self, "retailer_name", retailer_name)
        object.__setattr__(self, "ean", ean)
        object.__setattr__(self, "language_code", language_code)


@dataclass(frozen=True, slots=True)
class ProductHypothesis:
    hypothesis_id: str
    canonical_name: str
    attributes: tuple[tuple[str, str], ...] = ()
    negative_constraints: tuple[str, ...] = ()
    posterior_probability: float = 0.0
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip():
            raise ValueError("hypothesis_id is required")
        if not self.canonical_name.strip():
            raise ValueError("canonical_name is required")
        if not 0.0 <= float(self.posterior_probability) <= 1.0:
            raise ValueError("posterior_probability must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    """One candidate evaluated across independent business axes.

    A NOT_ASSESSED gate is never converted to FAIL. Coding evidence cannot erase
    a usable product URL, and browser automation accessibility is not treated as
    proof that a human cannot open the page.
    """

    candidate_id: str
    url: str
    domain: str
    source_role: SourceRole = SourceRole.UNKNOWN
    hypothesis_id: str | None = None
    search_rank: int | None = None
    search_support: float = 0.0
    identity_match: IdentityMatch = IdentityMatch.UNVERIFIED
    identity_confidence: float = 0.0
    browser_access: GateStatus = GateStatus.NOT_ASSESSED
    text_extractable: GateStatus = GateStatus.NOT_ASSESSED
    direct_product_page: GateStatus = GateStatus.NOT_ASSESSED
    durable_url: GateStatus = GateStatus.NOT_ASSESSED
    country_match: GateStatus = GateStatus.NOT_ASSESSED
    retailer_match: GateStatus = GateStatus.NOT_ASSESSED
    coding_evidence_complete: GateStatus = GateStatus.NOT_ASSESSED
    source_authority: int = 0
    evidence_ids: tuple[str, ...] = ()
    hard_conflicts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        candidate_id = self.candidate_id.strip()
        url = self.url.strip()
        parsed = urlparse(url)
        domain = self.domain.strip().lower().removeprefix("www.")
        if not candidate_id:
            raise ValueError("candidate_id is required")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"candidate URL must be absolute HTTP(S): {url!r}")
        inferred_domain = (parsed.hostname or "").lower().removeprefix("www.")
        if not domain:
            domain = inferred_domain
        if domain != inferred_domain:
            raise ValueError("candidate domain must match the URL hostname")
        if self.search_rank is not None and self.search_rank < 1:
            raise ValueError("search_rank must be at least 1")
        if not 0.0 <= float(self.search_support) <= 1.0:
            raise ValueError("search_support must be between 0 and 1")
        if not 0.0 <= float(self.identity_confidence) <= 1.0:
            raise ValueError("identity_confidence must be between 0 and 1")
        if not 0 <= int(self.source_authority) <= 100:
            raise ValueError("source_authority must be between 0 and 100")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "domain", domain)

    @property
    def browser_assessed(self) -> bool:
        return self.browser_access is not GateStatus.NOT_ASSESSED

    @property
    def has_identity_conflict(self) -> bool:
        return self.identity_match is IdentityMatch.MISMATCH or bool(self.hard_conflicts)

    @property
    def strictly_verified(self) -> bool:
        return bool(
            self.identity_match is IdentityMatch.EXACT
            and self.identity_confidence >= 0.80
            and self.browser_access is GateStatus.PASS
            and self.text_extractable is GateStatus.PASS
            and self.direct_product_page is GateStatus.PASS
            and self.durable_url is GateStatus.PASS
            and self.coding_evidence_complete is GateStatus.PASS
            and not self.hard_conflicts
        )

    @property
    def review_eligible(self) -> bool:
        """Whether the real direct URL can be delivered for human review.

        Browser automation or text extraction failure does not automatically
        remove a URL that a human coding team may still use. Explicit wrong-page,
        wrong-product, transient-URL, or identity-conflict evidence does.
        """

        return bool(
            self.direct_product_page is not GateStatus.FAIL
            and self.durable_url is not GateStatus.FAIL
            and self.identity_match is not IdentityMatch.MISMATCH
            and not self.hard_conflicts
        )

    def with_updates(self, **changes: object) -> "CandidateAssessment":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class DeliveryDecision:
    status: DeliveryStatus
    selected_candidate_id: str | None
    selected_url: str | None
    strictly_verified: bool
    coding_ready: bool
    reasons: tuple[str, ...]
    considered_candidate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status is DeliveryStatus.FAILED:
            if self.selected_url is not None or self.selected_candidate_id is not None:
                raise ValueError("FAILED delivery cannot contain a selected URL")
            if self.strictly_verified or self.coding_ready:
                raise ValueError("FAILED delivery cannot be verified or coding-ready")
            return
        if not self.selected_url or not self.selected_candidate_id:
            raise ValueError(
                "VERIFIED and REVIEW_REQUIRED decisions must contain a product URL"
            )
        if self.status is DeliveryStatus.VERIFIED and not self.strictly_verified:
            raise ValueError("VERIFIED delivery must be strictly verified")
        if self.strictly_verified and not self.coding_ready:
            raise ValueError("strict verification requires coding readiness")


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    max_search_actions: int = 3
    max_full_scrapes: int = 6
    max_browser_investigations: int = 3
    max_per_domain: int = 2

    def __post_init__(self) -> None:
        if not 1 <= self.max_search_actions <= 10:
            raise ValueError("max_search_actions must be between 1 and 10")
        if not 1 <= self.max_full_scrapes <= 50:
            raise ValueError("max_full_scrapes must be between 1 and 50")
        if not 1 <= self.max_browser_investigations <= 20:
            raise ValueError("max_browser_investigations must be between 1 and 20")
        if not 1 <= self.max_per_domain <= self.max_full_scrapes:
            raise ValueError("max_per_domain must be within the scrape budget")


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    search_actions: int = 0
    full_scrapes: int = 0
    browser_investigations: int = 0

    def validate_against(self, policy: BudgetPolicy) -> None:
        if not 0 <= self.search_actions <= policy.max_search_actions:
            raise ValueError("search action budget exceeded")
        if not 0 <= self.full_scrapes <= policy.max_full_scrapes:
            raise ValueError("full scrape budget exceeded")
        if not 0 <= self.browser_investigations <= policy.max_browser_investigations:
            raise ValueError("browser investigation budget exceeded")


@dataclass(frozen=True, slots=True)
class RunEvent:
    sequence: int
    stage: PipelineStage
    event_type: str
    message: str
    candidate_id: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductRun:
    product: ProductInput
    stage: PipelineStage = PipelineStage.INTERPRET_INPUT
    identity_resolution: IdentityResolution = IdentityResolution.INSUFFICIENT_EVIDENCE
    hypotheses: tuple[ProductHypothesis, ...] = ()
    candidates: tuple[CandidateAssessment, ...] = ()
    budget_policy: BudgetPolicy = field(default_factory=BudgetPolicy)
    budget_usage: BudgetUsage = field(default_factory=BudgetUsage)
    decision: DeliveryDecision | None = None
    events: tuple[RunEvent, ...] = ()

    def candidate(self, candidate_id: str) -> CandidateAssessment:
        for item in self.candidates:
            if item.candidate_id == candidate_id:
                return item
        raise KeyError(candidate_id)

    def with_candidates(self, candidates: Iterable[CandidateAssessment]) -> "ProductRun":
        values = tuple(candidates)
        ids = [item.candidate_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_id values must be unique")
        return replace(self, candidates=values)
