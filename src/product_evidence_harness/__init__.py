from src.product_evidence_harness.config import HarnessBudgetConfig, HarnessConfig, HarnessPolicy, SerpAPIConfig
from src.product_evidence_harness.contracts import (
    AgentAction,
    AgentActionRecord,
    CandidateScorecard,
    DiscoveryMode,
    HarnessTrace,
    MatchVerification,
    OrganicSearchResponse,
    OrganicSearchResult,
    PipelineTrace,
    ProductEvidence,
    ProductQuery,
    ProductSearchState,
    ProductURLMatch,
    LLMSearchPlan,
    LLMSearchQuery,
    ScrapeResult,
    ScoredURLCandidate,
    SerpAIResponse,
    URLCandidate,
)
from src.product_evidence_harness.country_profiles import CountryProfile, CountryProfileRegistry, LanguageProfile
from src.product_evidence_harness.detectors import DetectorFinding, VariantConflictDetector
from src.product_evidence_harness.elite import CodingReadiness, ConfidenceBreakdown, EnterpriseEvidenceAssessment, EnterpriseEvidenceEngine
from src.product_evidence_harness.environment import (
    EnvironmentValidationError,
    EnvironmentValidationReport,
    validate_runtime_environment,
)
from src.product_evidence_harness.feature_evidence import EvidenceSetSelector, FeatureAwareEvidenceExtractor, FeatureReasoner
from src.product_evidence_harness.feature_schema import (
    EvidenceSetDecision,
    FeatureCriticality,
    FeatureDefinition,
    FeatureEvidence,
    FeatureEvidenceStatus,
    FeatureSchema,
    URLFeatureAssessment,
)
from src.product_evidence_harness.feedback import ReviewFeedbackRecord, ReviewFeedbackStore, RetailerDomainMemory
from src.product_evidence_harness.identity import ProductIdentityGraph, ProductIdentityGraphBuilder
from src.product_evidence_harness.identity_verifier import ProductIdentityVerifier
from src.product_evidence_harness.io import CSVProductIO
from src.product_evidence_harness.legacy_compat import (
    HarnessProductURLFinderPipeline,
    HybridProductURLFinderPipeline,
    ProductEvidenceHarness,
)
from src.product_evidence_harness.llm import ExactProductLLMAdjudicator, LLMConfig, LLMService
from src.product_evidence_harness.llm.feature_reasoner import LLMFeatureReasoner
from src.product_evidence_harness.llm.vision_reasoner import MultimodalFeatureReasoner, VisionReasonerConfig
from src.product_evidence_harness.logging_utils import RichPrinter, configure_logging
from src.product_evidence_harness.one_credit_pipeline import (
    FeatureAwareHarnessResult,
    OneCreditConfig,
    OneCreditProductEvidenceHarness,
)
from src.product_evidence_harness.production_url import ProductionURLAssessment, ProductionURLGate
from src.product_evidence_harness.ranker import ProductURLRanker
from src.product_evidence_harness.scraper import CrawlScraper
from src.product_evidence_harness.schema_io import load_feature_schema
from src.product_evidence_harness.tournament_pipeline import TournamentAwareProductEvidenceHarness
from src.product_evidence_harness.compat_patches import apply_compatibility_patches
from src.product_evidence_harness.browser_contracts import (
    AcquisitionMethod,
    BrowserActionRecord,
    BrowserEvidenceBundle,
    BrowserEvidenceRequest,
    BrowserEvidenceStatus,
    EvidenceIntent,
    ProductIdentityPayload,
    VisualAsset,
)
from src.product_evidence_harness.browser_client import BrowserEvidenceClient, BrowserServiceConfig, BrowserServiceError
from src.product_evidence_harness.agent_service.orchestrator import AgentRuntimeConfig, FeatureSetRegistry, ProductEvidenceOrchestrator

apply_compatibility_patches()

FeatureAwareProductEvidenceHarness = OneCreditProductEvidenceHarness
LegacyTournamentProductEvidenceHarness = TournamentAwareProductEvidenceHarness

__all__ = [
    "SerpAPIConfig", "HarnessConfig", "HarnessPolicy", "HarnessBudgetConfig", "OneCreditConfig",
    "DiscoveryMode", "ProductQuery", "ProductURLMatch", "HarnessTrace", "PipelineTrace",
    "URLCandidate", "LLMSearchPlan", "LLMSearchQuery", "CandidateScorecard", "ScoredURLCandidate",
    "ScrapeResult", "ProductEvidence", "MatchVerification", "OrganicSearchResponse",
    "OrganicSearchResult", "SerpAIResponse", "ProductSearchState", "AgentAction", "AgentActionRecord",
    "ProductEvidenceHarness", "FeatureAwareProductEvidenceHarness", "OneCreditProductEvidenceHarness",
    "FeatureAwareHarnessResult", "HarnessProductURLFinderPipeline", "HybridProductURLFinderPipeline",
    "LegacyTournamentProductEvidenceHarness", "FeatureDefinition", "FeatureSchema", "FeatureCriticality",
    "FeatureEvidenceStatus", "FeatureEvidence", "URLFeatureAssessment", "EvidenceSetDecision",
    "FeatureAwareEvidenceExtractor", "EvidenceSetSelector", "FeatureReasoner", "load_feature_schema",
    "CrawlScraper", "ProductIdentityVerifier", "ProductIdentityGraph", "ProductIdentityGraphBuilder",
    "DetectorFinding", "VariantConflictDetector", "ProductURLRanker", "RichPrinter", "configure_logging", "CSVProductIO",
    "CountryProfile", "CountryProfileRegistry", "LanguageProfile", "ExactProductLLMAdjudicator", "LLMConfig", "LLMService",
    "LLMFeatureReasoner", "MultimodalFeatureReasoner", "VisionReasonerConfig",
    "EnvironmentValidationError", "EnvironmentValidationReport", "validate_runtime_environment",
    "EnterpriseEvidenceEngine", "EnterpriseEvidenceAssessment", "ConfidenceBreakdown", "CodingReadiness",
    "ReviewFeedbackRecord", "ReviewFeedbackStore", "RetailerDomainMemory", "ProductionURLGate", "ProductionURLAssessment",
    "AcquisitionMethod", "BrowserActionRecord", "BrowserEvidenceBundle", "BrowserEvidenceRequest",
    "BrowserEvidenceStatus", "EvidenceIntent", "ProductIdentityPayload", "VisualAsset",
    "BrowserEvidenceClient", "BrowserServiceConfig", "BrowserServiceError",
    "AgentRuntimeConfig", "FeatureSetRegistry", "ProductEvidenceOrchestrator",
]
