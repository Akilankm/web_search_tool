from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ClaimStatus(str, Enum):
    EXPLICIT = "EXPLICIT"
    NORMALIZED = "NORMALIZED"
    DETERMINISTICALLY_DERIVED = "DETERMINISTICALLY_DERIVED"
    INFERRED_FROM_TEXT = "INFERRED_FROM_TEXT"
    INFERRED_FROM_COUNTRY = "INFERRED_FROM_COUNTRY"
    MODEL_MEMORY_PRIOR = "MODEL_MEMORY_PRIOR"
    WEB_SUPPORTED = "WEB_SUPPORTED"
    WEB_VERIFIED = "WEB_VERIFIED"
    CONFLICTING = "CONFLICTING"
    DISPROVEN = "DISPROVEN"
    UNKNOWN = "UNKNOWN"


class EvidencePolarity(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class ResolutionStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    IN_PROGRESS = "IN_PROGRESS"
    EXACT = "EXACT"
    PROBABLE = "PROBABLE"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTING = "CONFLICTING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class MarketStage(str, Enum):
    REQUESTED_RETAILER = "requested_retailer"
    COUNTRY_ALTERNATIVE = "country_alternative"
    GLOBAL_FALLBACK = "global_fallback"


@dataclass(frozen=True)
class ProductClaim:
    claim_id: str
    field: str
    value: Any
    status: ClaimStatus
    confidence: float
    source_tokens: tuple[str, ...] = ()
    reasoning_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class ProductHypothesis:
    hypothesis_id: str
    canonical_name: str
    category: str = "unknown"
    product_role: str = "consumer_product"
    attributes: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    negative_constraints: list[str] = field(default_factory=list)
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradicting_evidence_ids: list[str] = field(default_factory=list)
    prior_score: float = 0.0
    score: float = 0.0
    posterior_probability: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProductUncertainty:
    field: str
    candidate_values: tuple[str, ...]
    entropy: float
    decision_impact: float
    priority: float
    affected_hypothesis_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AtomicEvidence:
    evidence_id: str
    source_url: str
    field: str
    value: Any
    polarity: EvidencePolarity
    affected_hypothesis_ids: tuple[str, ...]
    directness: str
    source_reliability: float
    extraction_confidence: float
    market_stage: str = ""
    excerpt: str = ""
    hard_conflict: bool = False

    @property
    def weight(self) -> float:
        sign = -1.0 if self.polarity == EvidencePolarity.CONTRADICTS else 1.0
        if self.polarity == EvidencePolarity.NEUTRAL:
            return 0.0
        multiplier = 1.8 if self.hard_conflict else 1.0
        return sign * self.source_reliability * self.extraction_confidence * multiplier

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["polarity"] = self.polarity.value
        data["weight"] = round(self.weight, 4)
        return data


@dataclass(frozen=True)
class BeliefSnapshot:
    sequence: int
    trigger: str
    probabilities: dict[str, float]
    leading_hypothesis_id: str | None
    resolution_status: ResolutionStatus
    posterior_margin: float
    evidence_count: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["resolution_status"] = self.resolution_status.value
        return data


@dataclass
class ProductBeliefState:
    row_id: str
    raw_main_text: str
    country_code: str
    requested_retailer: str | None
    interpretation_source: str
    claims: list[ProductClaim] = field(default_factory=list)
    hypotheses: list[ProductHypothesis] = field(default_factory=list)
    uncertainties: list[ProductUncertainty] = field(default_factory=list)
    evidence_ledger: list[AtomicEvidence] = field(default_factory=list)
    snapshots: list[BeliefSnapshot] = field(default_factory=list)
    negative_constraints: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    market_path: tuple[str, ...] = (
        MarketStage.REQUESTED_RETAILER.value,
        MarketStage.COUNTRY_ALTERNATIVE.value,
        MarketStage.GLOBAL_FALLBACK.value,
    )
    current_market_stage: str = ""
    parse_coverage: float = 0.0
    identity_completeness: float = 0.0
    ambiguity_entropy: float = 1.0
    assumption_burden: float = 1.0
    search_readiness: float = 0.0
    resolution_status: ResolutionStatus = ResolutionStatus.INITIALIZED
    selected_hypothesis_id: str | None = None
    llm_summary: str = ""
    llm_usage: dict[str, int] = field(default_factory=dict)

    @property
    def leading_hypothesis(self) -> ProductHypothesis | None:
        if not self.hypotheses:
            return None
        return max(self.hypotheses, key=lambda item: item.posterior_probability)

    @property
    def posterior_margin(self) -> float:
        probabilities = sorted((item.posterior_probability for item in self.hypotheses), reverse=True)
        if not probabilities:
            return 0.0
        if len(probabilities) == 1:
            return probabilities[0]
        return max(0.0, probabilities[0] - probabilities[1])

    def recalculate_entropy(self) -> float:
        probabilities = [item.posterior_probability for item in self.hypotheses if item.posterior_probability > 0]
        if len(probabilities) <= 1:
            self.ambiguity_entropy = 0.0
            return self.ambiguity_entropy
        raw = -sum(value * math.log(value) for value in probabilities)
        self.ambiguity_entropy = round(raw / math.log(len(probabilities)), 4)
        return self.ambiguity_entropy

    def add_snapshot(self, trigger: str) -> None:
        leading = self.leading_hypothesis
        self.snapshots.append(
            BeliefSnapshot(
                sequence=len(self.snapshots) + 1,
                trigger=trigger,
                probabilities={item.hypothesis_id: round(item.posterior_probability, 6) for item in self.hypotheses},
                leading_hypothesis_id=leading.hypothesis_id if leading else None,
                resolution_status=self.resolution_status,
                posterior_margin=round(self.posterior_margin, 6),
                evidence_count=len(self.evidence_ledger),
            )
        )

    def to_dict(self) -> dict[str, Any]:
        leading = self.leading_hypothesis
        return {
            "row_id": self.row_id,
            "raw_main_text": self.raw_main_text,
            "country_code": self.country_code,
            "requested_retailer": self.requested_retailer,
            "interpretation_source": self.interpretation_source,
            "claims": [item.to_dict() for item in self.claims],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "uncertainties": [item.to_dict() for item in self.uncertainties],
            "evidence_ledger": [item.to_dict() for item in self.evidence_ledger],
            "snapshots": [item.to_dict() for item in self.snapshots],
            "negative_constraints": list(self.negative_constraints),
            "unknowns": list(self.unknowns),
            "market_path": list(self.market_path),
            "current_market_stage": self.current_market_stage,
            "metrics": {
                "parse_coverage": self.parse_coverage,
                "identity_completeness": self.identity_completeness,
                "ambiguity_entropy": self.ambiguity_entropy,
                "assumption_burden": self.assumption_burden,
                "search_readiness": self.search_readiness,
                "posterior_margin": round(self.posterior_margin, 4),
            },
            "resolution_status": self.resolution_status.value,
            "selected_hypothesis_id": self.selected_hypothesis_id,
            "leading_hypothesis": leading.to_dict() if leading else None,
            "llm_summary": self.llm_summary,
            "llm_usage": dict(self.llm_usage),
        }
