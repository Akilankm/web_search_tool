from __future__ import annotations

import os
from dataclasses import replace
from typing import Any, Callable

from src.product_evidence_harness.agent_service.orchestrator import ProductEvidenceOrchestrator
from src.product_evidence_harness.browser_client import BrowserServiceError
from src.product_evidence_harness.browser_contracts import (
    BrowserEvidenceRequest,
    EvidenceIntent,
    ProductIdentityPayload,
)
from src.product_evidence_harness.config import HarnessConfig, SerpAPIConfig
from src.product_evidence_harness.contracts import ProductQuery
from src.product_evidence_harness.feature_evidence import EvidenceSetSelector
from src.product_evidence_harness.feature_schema import URLFeatureAssessment
from src.product_evidence_harness.llm.feature_reasoner import LLMFeatureReasoner
from src.product_evidence_harness.one_credit_pipeline import FeatureAwareHarnessResult, OneCreditConfig
from src.product_evidence_harness.schema_io import load_feature_schema
from src.product_evidence_harness.strict_acceptance import StrictPrimaryURLSelector
from src.product_evidence_harness.three_stage_pipeline import ThreeStageProductEvidenceHarness


def _enabled(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class StrictProductEvidenceOrchestrator(ProductEvidenceOrchestrator):
    """Three-stage discovery plus strict browser and feature acceptance."""

    def run(
        self,
        payload: dict[str, Any],
        *,
        progress: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        emit = progress or (lambda *_args: None)
        product_payload = dict(payload.get("product") or payload)
        feature_set = str(
            payload.get("feature_set") or product_payload.pop("feature_set", "")
        ).strip()
        if not feature_set:
            raise ValueError(
                "feature_set is required; the private feature file is resolved inside the agent container"
            )

        emit("VALIDATING_INPUT", "Loading product input and private feature set")
        product = ProductQuery(**product_payload)
        feature_path = self.feature_registry.resolve(feature_set)
        schema = load_feature_schema(feature_path)

        emit(
            "SEARCHING",
            "Running requested-retailer, same-country, and global fallback searches",
        )
        llm_reasoner = None
        if _enabled("PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING", False):
            llm_reasoner = LLMFeatureReasoner.from_env(
                max_calls=int(os.getenv("PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT", "2"))
            )

        stage_scrape_top_k = max(
            1,
            min(
                10,
                int(os.getenv("PRODUCT_HARNESS_SCRAPE_TOP_K_PER_STAGE", "6")),
            ),
        )
        harness = ThreeStageProductEvidenceHarness(
            serp_config=SerpAPIConfig.from_env(
                country_code=product.country_code,
                language_code=product.language_code or "en",
            ),
            config=HarnessConfig.from_env(),
            one_credit=OneCreditConfig(
                max_candidates=max(
                    30,
                    int(os.getenv("PRODUCT_HARNESS_MAX_CANDIDATE_POOL", "90")),
                ),
                scrape_top_k=stage_scrape_top_k,
                render_or_browser_top_k=max(
                    3,
                    int(os.getenv("PRODUCT_HARNESS_BROWSER_CANDIDATE_LIMIT", "9")),
                ),
                max_supplementary_urls=3,
            ),
            feature_reasoner=llm_reasoner,
        )
        harness.scrape_top_k_per_stage = stage_scrape_top_k
        base = harness.run(product, feature_schema=schema, return_trace=True)
        if not isinstance(base, FeatureAwareHarnessResult):
            raise RuntimeError("Expected feature-aware trace result")

        browser_bundles = []
        browser_assessments: list[URLFeatureAssessment] = []
        if self.browser_client is not None:
            emit(
                "REQUESTING_BROWSER_EVIDENCE",
                "Browser-verifying candidates from every fallback stage",
            )
            for index, url in enumerate(self._browser_urls(base), start=1):
                request = BrowserEvidenceRequest(
                    job_id=product.row_id,
                    candidate_id=f"CAND-{index:03d}",
                    url=url,
                    product_identity=ProductIdentityPayload(
                        row_id=product.row_id,
                        main_text=product.main_text,
                        country_code=product.country_code,
                        retailer_name=product.retailer_name,
                        ean=product.ean,
                        language_code=product.language_code,
                    ),
                    intent=EvidenceIntent(
                        verify_rendered_product=True,
                        expand_product_sections=True,
                        collect_gallery=True,
                        download_images=True,
                        capture_screenshot_fallbacks=True,
                        maximum_images=10,
                        maximum_screenshots=8,
                        maximum_actions=30,
                        requested_evidence_categories=(
                            "product_gallery",
                            "package_front_back",
                            "specification_sections",
                            "safety_and_warning_sections",
                            "dimension_diagrams",
                        ),
                    ),
                )
                try:
                    bundle = self.browser_client.acquire(request)
                except BrowserServiceError:
                    continue
                browser_bundles.append(bundle)
                assessment = self._assessment_from_browser(product, schema, bundle, llm_reasoner)
                if assessment is not None:
                    browser_assessments.append(assessment)

        emit(
            "VALIDATING_PRIMARY_URL",
            "Enforcing browser, identity, feature, scraping, and durability gates",
        )
        assessments = self._merge_assessments(base.feature_assessments, browser_assessments)
        diagnostic_evidence_set = EvidenceSetSelector(max_supplementary_urls=3).select(
            schema=schema,
            assessments=assessments,
            preferred_primary_url=base.product_match.product_url
            or base.product_match.best_available_url,
        )
        strict_acceptance = StrictPrimaryURLSelector(
            reject_expiring_urls=_enabled("PRODUCT_HARNESS_REJECT_EXPIRING_URLS", True),
            require_all_features_on_primary=_enabled(
                "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY",
                True,
            ),
        ).select(
            schema=schema,
            assessments=assessments,
            browser_bundles=browser_bundles,
            scorecards=base.state.scorecards,
        )

        if strict_acceptance.accepted:
            evidence_set = replace(
                diagnostic_evidence_set,
                primary_url=strict_acceptance.primary_url,
                supplementary_urls=(),
                selected_urls=(strict_acceptance.primary_url,),
                coding_ready=True,
                status="CODING_READY_STRICT_PRIMARY_URL",
                total_coverage=1.0,
                required_coverage=1.0,
                critical_coverage=1.0,
                missing_features=(),
                conflicting_features=(),
                reasons=(
                    "The primary URL is browser-openable and text-scrapable.",
                    "The rendered page is the exact requested product.",
                    "The same primary URL contains every requested feature.",
                    "The URL contains no signed, session-bound, or expiry parameter.",
                ),
            )
            product_match = replace(
                base.product_match,
                product_url=strict_acceptance.primary_url,
                validation_status="VERIFIED",
                identity_status="VERIFIED",
                is_exact_product_match=True,
                match_reason="STRICT_PRIMARY_URL_ACCEPTED",
                justification=(
                    "Accepted after browser verification, exact-product identity validation, "
                    "full requested-feature coverage, scrapability, and URL durability checks."
                ),
                resolution_status="RESOLVED",
                url_decision_status="STRICT_PRIMARY_URL_ACCEPTED",
                is_global_fallback=(strict_acceptance.scope == "global_fallback"),
                is_country_specific=(strict_acceptance.scope != "global_fallback"),
                needs_review=False,
                is_scrapable=True,
                scrape_final_url=strict_acceptance.primary_url,
                selection_scope=strict_acceptance.scope.upper(),
            )
        else:
            review_urls = tuple(
                dict.fromkeys(url for url in diagnostic_evidence_set.selected_urls if url)
            )
            evidence_set = replace(
                diagnostic_evidence_set,
                primary_url=None,
                supplementary_urls=review_urls,
                selected_urls=review_urls,
                coding_ready=False,
                status="REVIEW_REQUIRED_STRICT_PRIMARY_URL",
                reasons=strict_acceptance.reasons,
            )
            product_match = replace(
                base.product_match,
                product_url=None,
                is_exact_product_match=False,
                match_reason="STRICT_PRIMARY_URL_REJECTED",
                justification=(
                    "No URL passed every required final gate: browser-openable, accessible, "
                    "exact product, text-scrapable, complete requested feature coverage, and "
                    "non-expiring URL."
                ),
                resolution_status="REVIEW_REQUIRED",
                url_decision_status="STRICT_PRIMARY_URL_REJECTED",
                needs_review=True,
                primary_reject_reason="|".join(strict_acceptance.reasons[:20]),
            )

        coding_ready = strict_acceptance.accepted
        status = "COMPLETED" if coding_ready else "REVIEW_REQUIRED"
        stage_trace = list(getattr(base.state, "search_stage_trace", []))

        emit("WRITING_OUTPUTS", "Writing the final strict evidence dossier")
        result = {
            "job_status": status,
            "product": product.to_dict(),
            "feature_set": feature_set,
            "feature_schema_path": str(feature_path),
            "search": {
                "queries": list(base.state.queries),
                "stages": stage_trace,
                "serpapi_requests_used": base.state.budget.organic_used,
                "serpapi_request_limit": 3,
                "policy": "REQUESTED_RETAILER_COUNTRY_GLOBAL",
                "feature_schema_used_by_search": False,
            },
            "product_match": product_match.to_dict(),
            "primary_url": strict_acceptance.primary_url,
            "supplementary_urls": list(evidence_set.supplementary_urls),
            "primary_url_acceptance": strict_acceptance.to_dict(),
            "evidence_set": evidence_set.to_dict(),
            "feature_assessments": [assessment.to_dict() for assessment in assessments],
            "browser_evidence": [bundle.to_dict() for bundle in browser_bundles],
            "multimodal_ready": any(bundle.multimodal_scrapable for bundle in browser_bundles),
            "coding_ready": coding_ready,
            "artifact_dir": str(self.config.artifact_root / product.row_id),
        }
        output_dir = self.config.artifact_root / product.row_id
        output_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_json(
            output_dir / "primary_url_acceptance.json",
            strict_acceptance.to_dict(),
        )
        self._atomic_json(output_dir / "orchestrated_result.json", result)
        return result

    def _browser_urls(self, base: FeatureAwareHarnessResult) -> tuple[str, ...]:
        limit = max(3, int(self.config.browser_candidate_limit))
        cards = list(base.state.scorecards)
        selected: list[str] = []
        stage_order = (
            "requested_retailer_country",
            "country_primary",
            "country_alternative",
            "global_fallback",
        )

        for stage in stage_order:
            marker = f"scope_{stage}"
            card = next(
                (
                    item
                    for item in cards
                    if marker in item.candidate.source_types and not item.hard_failures
                ),
                None,
            )
            if card is not None:
                selected.append(card.candidate.url)

        selected.extend(
            [
                base.product_match.product_url,
                base.product_match.best_available_url,
            ]
        )
        selected.extend(card.candidate.url for card in cards if not card.hard_failures)
        selected.extend(card.candidate.url for card in cards)
        return tuple(dict.fromkeys(url for url in selected if url))[:limit]
