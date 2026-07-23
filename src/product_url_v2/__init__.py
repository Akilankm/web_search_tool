"""Notebook-first exact product-to-URL resolver."""

from product_url_v2.config import RuntimeConfig, load_config, load_feature_set
from product_url_v2.interpretation import DeterministicProductInterpreter, build_search_context, normalize_product_text
from product_url_v2.models import (
    BrowserEvidence,
    CandidateAssessment,
    DeliveryDecision,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    Interpretation,
    PageEvidence,
    ProductHypothesis,
    ProductInput,
    ResolutionResult,
    SourceRole,
    to_jsonable,
)
from product_url_v2.orchestrator import ProductURLOrchestrator
from product_url_v2.policy import (
    ACCEPTANCE_POLICY_VERSION,
    AcceptanceGate,
    AcceptanceVerdict,
    choose_delivery,
    evaluate_acceptance,
)

__version__ = "2.0.0"

__all__ = [
    "ACCEPTANCE_POLICY_VERSION",
    "AcceptanceGate",
    "AcceptanceVerdict",
    "BrowserEvidence",
    "CandidateAssessment",
    "DeliveryDecision",
    "DeliveryStatus",
    "DeterministicProductInterpreter",
    "GateStatus",
    "IdentityMatch",
    "Interpretation",
    "PageEvidence",
    "ProductHypothesis",
    "ProductInput",
    "ProductURLOrchestrator",
    "ResolutionResult",
    "RuntimeConfig",
    "SourceRole",
    "build_search_context",
    "choose_delivery",
    "evaluate_acceptance",
    "load_config",
    "load_feature_set",
    "normalize_product_text",
    "to_jsonable",
]
