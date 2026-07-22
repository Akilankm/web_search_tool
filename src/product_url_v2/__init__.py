"""Clean-slate product URL resolution foundation.

This package is intentionally independent from product_evidence_harness. It has
no import-time monkey patches and does not mutate legacy runtime classes.
"""

from product_url_v2.contracts import (
    BudgetPolicy,
    BudgetUsage,
    CandidateAssessment,
    DeliveryDecision,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    IdentityResolution,
    PipelineStage,
    ProductHypothesis,
    ProductInput,
    ProductRun,
    RunEvent,
    SourceRole,
)
from product_url_v2.metrics import (
    BenchmarkCase,
    BenchmarkMetrics,
    ReleaseDecision,
    ReleaseThresholds,
    RunMetrics,
    canonical_url,
    evaluate_release,
)
from product_url_v2.policy import (
    CandidateAllocationPolicy,
    MandatoryURLDeliveryPolicy,
    SearchObjective,
    build_search_objectives,
    is_structurally_product_like_url,
)
from product_url_v2.state_machine import ProductRunStateMachine

__all__ = [
    "BenchmarkCase",
    "BenchmarkMetrics",
    "BudgetPolicy",
    "BudgetUsage",
    "CandidateAllocationPolicy",
    "CandidateAssessment",
    "DeliveryDecision",
    "DeliveryStatus",
    "GateStatus",
    "IdentityMatch",
    "IdentityResolution",
    "MandatoryURLDeliveryPolicy",
    "PipelineStage",
    "ProductHypothesis",
    "ProductInput",
    "ProductRun",
    "ProductRunStateMachine",
    "ReleaseDecision",
    "ReleaseThresholds",
    "RunEvent",
    "RunMetrics",
    "SearchObjective",
    "SourceRole",
    "build_search_objectives",
    "canonical_url",
    "evaluate_release",
    "is_structurally_product_like_url",
]
