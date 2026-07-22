"""Canonical product URL resolver. No legacy imports, monkey patches or import-time mutation."""

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

__version__ = "1.0.2"

__all__ = [
    "BrowserEvidence", "CandidateAssessment", "DeliveryDecision", "DeliveryStatus",
    "DeterministicProductInterpreter", "GateStatus", "IdentityMatch", "Interpretation",
    "PageEvidence", "ProductHypothesis", "ProductInput", "ProductURLOrchestrator",
    "ResolutionResult", "RuntimeConfig", "SourceRole", "build_search_context",
    "load_config", "load_feature_set", "normalize_product_text", "to_jsonable",
]
