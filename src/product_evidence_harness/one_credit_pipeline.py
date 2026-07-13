from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Optional, Sequence

from loguru import logger

from src.product_evidence_harness.budget import BudgetTracker
from src.product_evidence_harness.candidate_store import CandidateStore
from src.product_evidence_harness.config import HarnessConfig, SerpAPIConfig
from src.product_evidence_harness.contracts import CandidateScorecard, ProductQuery, ProductSearchState, ProductURLMatch, ScrapeResult, URLCandidate
from src.product_evidence_harness.country_profiles import CountryProfileRegistry
from src.product_evidence_harness.feature_evidence import EvidenceSetSelector, FeatureAwareEvidenceExtractor, FeatureReasoner
from src.product_evidence_harness.feature_schema import EvidenceSetDecision, FeatureSchema, URLFeatureAssessment
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.identity_verifier import ProductIdentityVerifier
from src.product_evidence_harness.production_url import ProductionURLGate
from src.product_evidence_harness.query_builder import QueryBuilder
from src.product_evidence_harness.ranker import ProductURLRanker
from src.product_evidence_harness.scraper import CrawlScraper
from src.product_evidence_harness.selector import FinalSelector
from src.product_evidence_harness.serp_clients import GoogleOrganicSearchClient


@dataclass(frozen=True, slots=True)
class OneCreditConfig:
    max_candidates: int = 30
    scrape_top_k: int = 8
    render_or_browser_top_k: int = 3
    max_supplementary_urls: int = 3
    write_outputs: bool = True
    # Empty means inherit HarnessConfig.output_dir, including the container's
    # PRODUCT_HARNESS_OUTPUT_DIR=/data/artifacts setting.
    output_dir: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_candidates", max(1, int(self.max_candidates)))
        object.__setattr__(self, "scrape_top_k", max(1, min(int(self.scrape_top_k), self.max_candidates)))
        object.__setattr__(self, "render_or_browser_top_k", max(1, min(int(self.render_or_browser_top_k), self.scrape_top_k)))
        object.__setattr__(self, "max_supplementary_urls", max(0, int(self.max_supplementary_urls)))


@dataclass(frozen=True, slots=True)
class FeatureAwareHarnessResult:
    state: ProductSearchState
    product_match: ProductURLMatch
    search_query: str
    feature_schema: FeatureSchema | None
    feature_assessments: tuple[URLFeatureAssessment, ...]
    evidence_set: EvidenceSetDecision | None
    artifact_dir: str | None = None

    @property
    def best_match(self) -> ProductURLMatch:
        return self.product_match

    @property
    def scored_candidates(self) -> list[CandidateScorecard]:
        return self.state.scorecards

    @property
    def candidates(self) -> list[URLCandidate]:
        return self.state.candidates

    @property
    def scrapes(self) -> dict[str, ScrapeResult]:
        return self.state.scrapes

    @property
    def product_url(self) -> str | None:
        return self.product_match.product_url

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_match": self.product_match.to_dict(),
            "search_query": self.search_query,
            "feature_schema": self.feature_schema.to_dict() if self.feature_schema else None,
            "feature_assessments": [assessment.to_dict() for assessment in self.feature_assessments],
            "evidence_set": self.evidence_set.to_dict() if self.evidence_set else None,
            "artifact_dir": self.artifact_dir,
        }


@dataclass
class OneCreditProductEvidenceHarness:
    """One paid search, feature-agnostic discovery, feature-aware scraping."""

    serp_config: SerpAPIConfig
    config: HarnessConfig = field(default_factory=HarnessConfig)
    one_credit: OneCreditConfig = field(default_factory=OneCreditConfig)
    organic_client: Optional[GoogleOrganicSearchClient] = None
    scraper: Optional[CrawlScraper] = None
    candidate_store: Optional[CandidateStore] = None
    query_builder: Optional[QueryBuilder] = None
    verifier: Optional[ProductIdentityVerifier] = None
    ranker: Optional[ProductURLRanker] = None
    selector: Optional[FinalSelector] = None
    production_gate: Optional[ProductionURLGate] = None
    feature_extractor: Optional[FeatureAwareEvidenceExtractor] = None
    feature_reasoner: Optional[FeatureReasoner] = None
    country_profiles: Optional[CountryProfileRegistry] = None

    def __post_init__(self) -> None:
        self.serp_config = replace(self.serp_config, max_retries=1)
        self.country_profiles = self.country_profiles or CountryProfileRegistry.load(self.config.country_profile_path)
        self.organic_client = self.organic_client or GoogleOrganicSearchClient(self.serp_config)
        self.scraper = self.scraper or CrawlScraper(
            headless=self.config.crawl_headless,
            verbose=self.config.crawl_verbose,
            page_timeout_ms=self.config.crawl_page_timeout_ms,
            min_word_count=self.config.crawl_min_word_count,
            scrape_concurrency=self.config.scrape_concurrency,
            static_fetch_first=self.config.static_fetch_first,
            browser_fallback_only=self.config.browser_fallback_only,
            static_timeout_seconds=self.config.static_timeout_seconds,
        )
        self.candidate_store = self.candidate_store or CandidateStore(max_pool_size=self.one_credit.max_candidates)
        self.query_builder = self.query_builder or QueryBuilder(country_profiles=self.country_profiles)
        effective_policy = self.config.with_effective_policy().policy
        self.verifier = self.verifier or ProductIdentityVerifier(policy=effective_policy)
        self.ranker = self.ranker or ProductURLRanker(weights=self.config.score_weights, policy=effective_policy, country_profiles=self.country_profiles)
        self.selector = self.selector or FinalSelector(policy=effective_policy)
        self.production_gate = self.production_gate or ProductionURLGate()
        self.feature_extractor = self.feature_extractor or FeatureAwareEvidenceExtractor()

    def run(self, product: ProductQuery, *, feature_schema: FeatureSchema | None = None, return_trace: bool = False) -> ProductURLMatch | FeatureAwareHarnessResult:
        product = self._with_language(product)
        budget = BudgetTracker(max_organic=1, max_ai_mode=0, max_scrapes=self.one_credit.scrape_top_k)
        state = ProductSearchState(task=product, budget=budget)
        state.identity_graph = ProductIdentityGraphBuilder().build(product)

        query = self.query_builder.primary(product)
        budget.consume_organic()
        response = self._search_once(query, product)
        state.queries.append(query)
        state.organic_responses.append(response)
        state.candidates = self.candidate_store.merge_organic([], response)
        state.candidates = self._preflight_rank(product, state.candidates)[: self.one_credit.max_candidates]

        scrape_candidates = state.candidates[: self.one_credit.scrape_top_k]
        scrape_results = self._scrape_many(scrape_candidates, product, budget)
        for candidate, scrape in zip(scrape_candidates, scrape_results):
            state.scrapes[candidate.url] = scrape
            state.verifications[candidate.url] = self.verifier.verify(product, scrape, identity_graph=state.identity_graph)

        state.scorecards = self.ranker.score(product=product, candidates=state.candidates, scrapes=state.scrapes, verifications=state.verifications)
        state.termination_reason = "ONE_CREDIT_SEARCH_COMPLETED"
        product_match = self.selector.select(task=product, scorecards=state.scorecards, termination_reason=state.termination_reason, budget_snapshot=budget.snapshot(), state=state)

        from src.product_evidence_harness.pipeline import ProductEvidenceHarness as LegacyHarness
        product_match = LegacyHarness._enforce_production_grade_product_url(product_match, state, production_gate=self.production_gate)
        state.final_result = product_match

        assessments: tuple[URLFeatureAssessment, ...] = ()
        evidence_set: EvidenceSetDecision | None = None
        if feature_schema is not None:
            assessments = self._assess_features(product, feature_schema, state)
            evidence_set = EvidenceSetSelector(max_supplementary_urls=self.one_credit.max_supplementary_urls).select(
                schema=feature_schema,
                assessments=assessments,
                preferred_primary_url=product_match.product_url or product_match.best_available_url,
            )

        artifact_dir = None
        if self.one_credit.write_outputs and self.config.write_outputs:
            artifact_dir = str(self._write_outputs(product, state, product_match, query, feature_schema, assessments, evidence_set))

        result = FeatureAwareHarnessResult(
            state=state,
            product_match=product_match,
            search_query=query,
            feature_schema=feature_schema,
            feature_assessments=assessments,
            evidence_set=evidence_set,
            artifact_dir=artifact_dir,
        )
        logger.info(
            "One-credit workflow completed | row_id={} | serp_calls={} | candidates={} | scrapes={} | product_url={} | coding_status={}",
            product.row_id,
            budget.organic_used,
            len(state.candidates),
            budget.scrape_used,
            product_match.product_url,
            evidence_set.status if evidence_set else "FEATURE_SCHEMA_NOT_PROVIDED",
        )
        return result if return_trace else product_match

    def _with_language(self, product: ProductQuery) -> ProductQuery:
        if product.language_code:
            return product
        profile = self.country_profiles.get(product.country_code)
        return replace(product, language_code=profile.default_language)

    def _search_once(self, query: str, product: ProductQuery):
        try:
            return self.organic_client.search(query, product=product, scope="country", language_code=product.language_code, country_code=product.country_code)
        except TypeError:
            return self.organic_client.search(query, product=product)

    def _scrape_many(self, candidates: Sequence[URLCandidate], product: ProductQuery, budget: BudgetTracker) -> list[ScrapeResult]:
        urls = [candidate.url for candidate in candidates]
        for _ in urls:
            budget.consume_scrape()
        if hasattr(self.scraper, "scrape_many"):
            try:
                return list(self.scraper.scrape_many(urls, product=product, max_workers=self.config.scrape_concurrency))
            except TypeError:
                pass
        return [self.scraper.scrape(url, product=product) for url in urls]

    def _preflight_rank(self, product: ProductQuery, candidates: Sequence[URLCandidate]) -> list[URLCandidate]:
        identity_tokens = self._tokens(product.main_text)
        ean = product.ean or ""
        retailer = (product.retailer_name or "").lower()

        def score(candidate: URLCandidate) -> tuple[float, float, int]:
            evidence = " ".join([candidate.url, candidate.title, candidate.snippet, candidate.domain]).lower()
            overlap = sum(1 for token in identity_tokens if token in evidence) / max(1, len(identity_tokens))
            ean_bonus = 1.0 if ean and ean in re.sub(r"\D", "", evidence) else 0.0
            retailer_bonus = 1.0 if retailer and retailer.replace(" ", "") in evidence.replace(" ", "") else 0.0
            module_support = min(1.0, len(candidate.source_types) / 3)
            position = candidate.best_position or 999
            weighted = 0.45 * overlap + 0.30 * ean_bonus + 0.15 * retailer_bonus + 0.10 * module_support
            return weighted, module_support, -position

        return sorted(candidates, key=score, reverse=True)

    @staticmethod
    def _tokens(value: str) -> tuple[str, ...]:
        stop = {"the", "and", "with", "for", "from", "pack", "product", "toy"}
        return tuple(dict.fromkeys(token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2 and token not in stop))

    def _assess_features(self, product: ProductQuery, schema: FeatureSchema, state: ProductSearchState) -> tuple[URLFeatureAssessment, ...]:
        assessments = []
        for card in state.scorecards:
            if card.scrape is None:
                continue
            assessments.append(
                self.feature_extractor.extract(
                    product=product,
                    schema=schema,
                    scrape=card.scrape,
                    verification=card.verification,
                    reasoner=self.feature_reasoner,
                )
            )
        return tuple(assessments)

    def _write_outputs(self, product: ProductQuery, state: ProductSearchState, match: ProductURLMatch, query: str, schema: FeatureSchema | None, assessments: Sequence[URLFeatureAssessment], evidence_set: EvidenceSetDecision | None) -> Path:
        root = Path(self.one_credit.output_dir or self.config.output_dir) / product.row_id
        root.mkdir(parents=True, exist_ok=True)
        result_payload = {
            "product": product.to_dict(),
            "search": {
                "query": query,
                "serpapi_requests_used": 1,
                "policy": "ONE_CREDIT_HARD_LIMIT",
                "feature_schema_used_by_search": False,
            },
            "product_match": match.to_dict(),
            "feature_schema": schema.to_dict() if schema else None,
            "feature_assessments": [assessment.to_dict() for assessment in assessments],
            "evidence_set": evidence_set.to_dict() if evidence_set else None,
        }
        (root / "result.json").write_text(json.dumps(result_payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        self._write_candidates(root / "candidates.csv", state.scorecards)
        self._write_feature_evidence(root / "feature_evidence.csv", assessments)
        (root / "review.md").write_text(self._review_markdown(product, match, query, state, evidence_set), encoding="utf-8")
        return root

    @staticmethod
    def _write_candidates(path: Path, cards: Sequence[CandidateScorecard]) -> None:
        fields = ["url", "source_types", "best_position", "confidence", "validation_status", "identity_status", "ean_check", "title_check", "page_type", "scrapable", "richness", "decision_reasons"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for card in cards:
                writer.writerow({
                    "url": card.candidate.url,
                    "source_types": "|".join(card.candidate.source_types),
                    "best_position": card.candidate.best_position or "",
                    "confidence": card.final_confidence,
                    "validation_status": card.validation_status,
                    "identity_status": card.verification.identity_status if card.verification else "NOT_SCRAPED",
                    "ean_check": card.verification.ean_check if card.verification else "UNKNOWN",
                    "title_check": card.verification.title_check if card.verification else "UNKNOWN",
                    "page_type": card.verification.page_type_check if card.verification else "UNKNOWN",
                    "scrapable": bool(card.scrape and card.scrape.is_scrapable),
                    "richness": card.scrape.richness_score if card.scrape else 0.0,
                    "decision_reasons": "|".join([*card.hard_failures, *card.soft_warnings, *card.ranking_reasons]),
                })

    @staticmethod
    def _write_feature_evidence(path: Path, assessments: Sequence[URLFeatureAssessment]) -> None:
        fields = ["url", "source_role", "identity_status", "feature_id", "feature_name", "value", "status", "confidence", "evidence_location", "evidence_text", "extraction_method"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for assessment in assessments:
                for item in assessment.evidence:
                    writer.writerow({
                        "url": assessment.url,
                        "source_role": assessment.source_role,
                        "identity_status": assessment.identity_status,
                        "feature_id": item.feature_id,
                        "feature_name": item.feature_name,
                        "value": item.value,
                        "status": item.status.value,
                        "confidence": item.confidence,
                        "evidence_location": item.evidence_location,
                        "evidence_text": item.evidence_text,
                        "extraction_method": item.extraction_method,
                    })

    @staticmethod
    def _review_markdown(product: ProductQuery, match: ProductURLMatch, query: str, state: ProductSearchState, evidence_set: EvidenceSetDecision | None) -> str:
        lines = [
            f"# Product evidence review — {product.row_id}",
            "",
            "## One-credit search contract",
            "",
            "| Item | Value |",
            "|---|---|",
            "| SerpAPI requests | `1` |",
            f"| Query | `{query}` |",
            f"| Candidate URLs | `{len(state.candidates)}` |",
            f"| Scraped candidates | `{len(state.scrapes)}` |",
            "| Feature list used by SerpAPI | `No` |",
            "| Feature list used after scraping | `Yes` |",
            "",
            "## Product URL decision",
            "",
            f"- Product URL: `{match.product_url or 'NONE'}`",
            f"- Best review URL: `{match.best_available_url or 'NONE'}`",
            f"- Status: `{match.url_decision_status}`",
            f"- Exact product: `{match.is_exact_product_match}`",
            f"- Confidence: `{match.confidence}`",
            "",
        ]
        if evidence_set:
            lines.extend([
                "## Feature evidence set",
                "",
                f"- Coding status: `{evidence_set.status}`",
                f"- Primary identity URL: `{evidence_set.primary_url or 'NONE'}`",
                f"- Supplementary URLs: `{', '.join(evidence_set.supplementary_urls) or 'NONE'}`",
                f"- Required-feature coverage: `{evidence_set.required_coverage:.1%}`",
                f"- Critical-feature coverage: `{evidence_set.critical_coverage:.1%}`",
                f"- Missing features: `{', '.join(evidence_set.missing_features) or 'NONE'}`",
                f"- Conflicting features: `{', '.join(evidence_set.conflicting_features) or 'NONE'}`",
                "",
            ])
        lines.extend([
            "## Decision principle",
            "",
            "Search is identity-driven and feature-agnostic. Scraping and evidence selection are feature-aware. A URL is never accepted for coding unless it first passes product-identity validation.",
            "",
        ])
        return "\n".join(lines)


ProductEvidenceHarness = OneCreditProductEvidenceHarness
HarnessProductURLFinderPipeline = OneCreditProductEvidenceHarness
HybridProductURLFinderPipeline = OneCreditProductEvidenceHarness
