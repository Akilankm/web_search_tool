from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_ASSESSED = "NOT_ASSESSED"


class IdentityMatch(str, Enum):
    EXACT = "EXACT"
    PROBABLE = "PROBABLE"
    UNVERIFIED = "UNVERIFIED"
    MISMATCH = "MISMATCH"


class DeliveryStatus(str, Enum):
    VERIFIED = "VERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"


class SourceRole(str, Enum):
    LOCAL_MANUFACTURER = "LOCAL_MANUFACTURER"
    GLOBAL_MANUFACTURER = "GLOBAL_MANUFACTURER"
    REQUESTED_RETAILER = "REQUESTED_RETAILER"
    COUNTRY_RETAILER = "COUNTRY_RETAILER"
    GLOBAL_RETAILER = "GLOBAL_RETAILER"
    MARKETPLACE = "MARKETPLACE"
    UNKNOWN = "UNKNOWN"


class PipelineStage(str, Enum):
    INTERPRET = "INTERPRET"
    SEARCH = "SEARCH"
    ACQUIRE = "ACQUIRE"
    BROWSER = "BROWSER"
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
    feature_set: str = "toy"
    runtime_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        row_id = self.row_id.strip()
        main_text = " ".join(self.main_text.split())
        country_code = self.country_code.strip().upper()
        retailer = (self.retailer_name or "").strip() or None
        ean = "".join(ch for ch in str(self.ean or "") if ch.isdigit()) or None
        language = (self.language_code or "").strip().lower() or None
        feature_set = self.feature_set.strip() or "toy"
        if not row_id:
            raise ValueError("row_id is required")
        if not main_text:
            raise ValueError("main_text is required")
        if len(country_code) != 2 or not country_code.isalpha():
            raise ValueError("country_code must contain exactly two letters")
        if ean is not None and len(ean) not in {8, 12, 13, 14}:
            raise ValueError("ean must contain 8, 12, 13 or 14 digits")
        if language is not None and (len(language) != 2 or not language.isalpha()):
            raise ValueError("language_code must contain exactly two letters")
        object.__setattr__(self, "row_id", row_id)
        object.__setattr__(self, "main_text", main_text)
        object.__setattr__(self, "country_code", country_code)
        object.__setattr__(self, "retailer_name", retailer)
        object.__setattr__(self, "ean", ean)
        object.__setattr__(self, "language_code", language)
        object.__setattr__(self, "feature_set", feature_set)
        object.__setattr__(self, "runtime_options", dict(self.runtime_options))


@dataclass(frozen=True, slots=True)
class IdentitySignal:
    field: str
    value: str
    confidence: float
    source: str
    evidence: str
    exact: bool = False

    def __post_init__(self) -> None:
        if not self.field.strip() or not self.value.strip():
            raise ValueError("identity signal field and value are required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("identity signal confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ProductHypothesis:
    hypothesis_id: str
    canonical_name: str
    attributes: Mapping[str, str]
    negative_constraints: tuple[str, ...] = ()
    prior_probability: float = 0.0
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.hypothesis_id.strip() or not self.canonical_name.strip():
            raise ValueError("hypothesis id and canonical name are required")
        if not 0.0 <= float(self.prior_probability) <= 1.0:
            raise ValueError("prior_probability must be between 0 and 1")
        object.__setattr__(self, "attributes", dict(self.attributes))


@dataclass(frozen=True, slots=True)
class Interpretation:
    normalized_text: str
    signals: tuple[IdentitySignal, ...]
    hypotheses: tuple[ProductHypothesis, ...]
    unresolved_discriminators: tuple[str, ...]
    negative_constraints: tuple[str, ...]
    language_code: str

    def strongest(self, field_name: str) -> IdentitySignal | None:
        matching = [item for item in self.signals if item.field == field_name]
        return max(matching, key=lambda item: (item.exact, item.confidence), default=None)

    def values(self, field_name: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.value for item in self.signals if item.field == field_name))


@dataclass(frozen=True, slots=True)
class SearchAction:
    credit_number: int
    engine: str
    purpose: str
    scope: str
    query: str = ""
    page_token: str = ""
    rationale: str = ""
    target_uncertainty: str = ""

    @property
    def signature(self) -> str:
        if self.engine == "google_immersive_product":
            return f"{self.engine}|{self.page_token.strip()}"
        return f"{self.engine}|{self.scope}|{' '.join(self.query.casefold().split())}"


@dataclass(frozen=True, slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    source_section: str
    engine: str
    query: str
    position: int | None = None
    product_like: bool = False
    page_token: str = ""

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("search result URL must be absolute HTTP(S)")


@dataclass(frozen=True, slots=True)
class SearchObservation:
    action: SearchAction
    status: str
    results: tuple[SearchResult, ...]
    search_id: str | None = None
    answer_summary: str = ""
    error: str = ""


@dataclass(frozen=True, slots=True)
class PageEvidence:
    requested_url: str
    final_url: str
    status_code: int | None
    content_type: str
    title: str
    description: str
    visible_text: str
    jsonld_products: tuple[Mapping[str, Any], ...]
    metadata: Mapping[str, str]
    links: tuple[str, ...]
    images: tuple[str, ...]
    fetch_status: GateStatus
    fetch_error: str = ""
    elapsed_ms: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "jsonld_products", tuple(dict(item) for item in self.jsonld_products))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class BrowserEvidence:
    url: str
    access: GateStatus
    final_url: str = ""
    title: str = ""
    visible_text: str = ""
    screenshot_path: str = ""
    product_controls: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    candidate_id: str
    url: str
    domain: str
    search_rank: int | None
    search_support: float
    source_role: SourceRole
    identity_match: IdentityMatch
    identity_confidence: float
    direct_product_page: GateStatus
    direct_page_score: float
    durable_url: GateStatus
    country_match: GateStatus
    retailer_match: GateStatus
    browser_access: GateStatus
    text_extractable: GateStatus
    coding_evidence_complete: GateStatus
    source_authority: int
    evidence: Mapping[str, Any] = field(default_factory=dict)
    conflicts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("candidate URL must be absolute HTTP(S)")
        inferred = (parsed.hostname or "").lower().removeprefix("www.")
        if self.domain.strip().lower().removeprefix("www.") != inferred:
            raise ValueError("candidate domain must match URL hostname")
        if not 0 <= self.source_authority <= 100:
            raise ValueError("source_authority must be between 0 and 100")
        if not 0.0 <= self.identity_confidence <= 1.0:
            raise ValueError("identity_confidence must be between 0 and 1")
        if not 0.0 <= self.direct_page_score <= 1.0:
            raise ValueError("direct_page_score must be between 0 and 1")
        object.__setattr__(self, "evidence", dict(self.evidence))

    @property
    def browser_assessed(self) -> bool:
        return self.browser_access is not GateStatus.NOT_ASSESSED

    @property
    def hard_url_blockers(self) -> tuple[str, ...]:
        values = self.evidence.get("hard_url_blockers") or ()
        if isinstance(values, str):
            values = (values,)
        return tuple(str(item) for item in values if str(item).strip())

    @property
    def exact_identifier_required(self) -> bool:
        return bool(self.evidence.get("required_identifier"))

    @property
    def exact_identifier_verified(self) -> bool:
        if not self.exact_identifier_required:
            return True
        return bool(self.evidence.get("exact_identifier_verified"))

    @property
    def mapping_eligible(self) -> bool:
        """True only when this URL is the exact, openable and scrapable product page."""
        return bool(
            self.identity_match is IdentityMatch.EXACT
            and self.exact_identifier_verified
            and self.direct_product_page is GateStatus.PASS
            and self.durable_url is GateStatus.PASS
            and self.browser_access is GateStatus.PASS
            and self.text_extractable is GateStatus.PASS
            and not self.conflicts
            and not self.hard_url_blockers
        )

    @property
    def strictly_verified(self) -> bool:
        return bool(self.mapping_eligible and self.coding_evidence_complete is GateStatus.PASS)

    @property
    def review_eligible(self) -> bool:
        """A review URL must still be an exact, accessible and scrapable mapping.

        REVIEW_REQUIRED is reserved for secondary uncertainty such as coding-field,
        country or requested-retailer completeness. It is never a fallback for an
        inaccessible, unverified or conflicting product page.
        """
        return self.mapping_eligible

    def with_updates(self, **changes: Any) -> "CandidateAssessment":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class DeliveryDecision:
    status: DeliveryStatus
    selected_url: str | None
    selected_candidate_id: str | None
    confidence: float
    coding_ready: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status in {DeliveryStatus.VERIFIED, DeliveryStatus.REVIEW_REQUIRED}:
            if not self.selected_url or not self.selected_candidate_id:
                raise ValueError("delivered decisions require a URL and candidate id")
        elif self.selected_url or self.selected_candidate_id:
            raise ValueError("failed decisions cannot contain a selected URL")


@dataclass(frozen=True, slots=True)
class RunEvent:
    sequence: int
    stage: PipelineStage
    event_type: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    runtime_contract: str
    product: ProductInput
    interpretation: Interpretation | None
    search_observations: tuple[SearchObservation, ...]
    candidates: tuple[CandidateAssessment, ...]
    decision: DeliveryDecision
    events: tuple[RunEvent, ...]
    artifact_dir: str
    elapsed_ms: int
    technical_error: str = ""


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value


def unique_candidates(items: Iterable[CandidateAssessment]) -> tuple[CandidateAssessment, ...]:
    seen: set[str] = set()
    output: list[CandidateAssessment] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        output.append(item)
    return tuple(output)
