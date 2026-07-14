from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from loguru import logger

from src.product_evidence_harness.budget import BudgetTracker
from src.product_evidence_harness.candidate_precision import CandidatePrecisionGate
from src.product_evidence_harness.contracts import ProductQuery, ProductSearchState
from src.product_evidence_harness.feature_evidence import EvidenceSetSelector
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.one_credit_pipeline import FeatureAwareHarnessResult
from src.product_evidence_harness.url_utils import domain_of


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


def _precision_run(
    self,
    product: ProductQuery,
    *,
    feature_schema=None,
    return_trace: bool = False,
):
    product = self._with_language(product)
    maximum_full_scrapes = _bounded_int("PRODUCT_HARNESS_MAX_FULL_SCRAPES", 6, 1, 12)
    maximum_per_domain = _bounded_int("PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN", 2, 1, 4)
    try:
        minimum_score = float(os.getenv("PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE", "0.28"))
    except ValueError:
        minimum_score = 0.28
    gate = CandidatePrecisionGate(
        minimum_score=minimum_score,
        maximum_full_scrapes=maximum_full_scrapes,
        maximum_per_domain=maximum_per_domain,
    )
    budget = BudgetTracker(max_organic=3, max_ai_mode=0, max_scrapes=maximum_full_scrapes)
    state = ProductSearchState(task=product, budget=budget)
    state.identity_graph = ProductIdentityGraphBuilder().build(product)
    state.candidate_admissions = {}
    stage_trace: list[dict[str, Any]] = []

    for stage_index in range(3):
        stage = self._build_stage(product, state, stage_index)
        budget.consume_organic()
        response = self._search_stage(stage, product)
        state.queries.append(stage.query)
        state.organic_responses.append(response)
        before_urls = {candidate.url for candidate in state.candidates}
        state.candidates = self._tag_stage(
            self.candidate_store.merge_organic(state.candidates, response),
            stage,
        )
        state.candidates = self._preflight_rank(product, state.candidates)[
            : self.candidate_store.max_pool_size
        ]

        pool = [
            candidate
            for candidate in state.candidates
            if stage.query in candidate.query_sources and candidate.url not in state.scrapes
        ]
        if stage_index == 2:
            pool = [candidate for candidate in state.candidates if candidate.url not in state.scrapes]

        existing_domains = Counter(domain_of(url) for url in state.scrapes)
        pool = [
            candidate
            for candidate in pool
            if existing_domains.get(candidate.domain or domain_of(candidate.url), 0)
            < maximum_per_domain
        ]
        remaining = budget.snapshot().scrape_remaining
        stages_left = 3 - stage_index
        allowance = (
            0
            if remaining <= 0
            else min(remaining, max(1, (remaining + stages_left - 1) // stages_left))
        )
        scrape_candidates, decisions = gate.select_for_scrape(
            product=product,
            candidates=pool,
            already_scraped=state.scrapes,
            maximum_new=allowance,
        )
        for candidate in state.candidates:
            decision = decisions.get(candidate.url) or gate.evaluate(product, candidate)
            state.candidate_admissions[candidate.url] = decision.to_dict()

        scrape_results = self._scrape_many(scrape_candidates, product, budget)
        for candidate, scrape in zip(scrape_candidates, scrape_results):
            state.scrapes[candidate.url] = scrape
            state.verifications[candidate.url] = self.verifier.verify(
                product,
                scrape,
                identity_graph=state.identity_graph,
            )
        state.scorecards = self.ranker.score(
            product=product,
            candidates=state.candidates,
            scrapes=state.scrapes,
            verifications=state.verifications,
        )
        stage_decisions = [
            state.candidate_admissions[candidate.url]
            for candidate in pool
            if candidate.url in state.candidate_admissions
        ]
        stage_trace.append(
            {
                **stage.to_dict(),
                "serp_credit": stage_index + 1,
                "results_returned": len(response.results),
                "canonical_candidates_seen": len(pool),
                "new_candidate_urls": len(
                    {candidate.url for candidate in state.candidates} - before_urls
                ),
                "candidates_qualified": sum(
                    1 for item in stage_decisions if item.get("admitted_for_scrape")
                ),
                "candidates_rejected_url_type": sum(
                    1
                    for item in stage_decisions
                    if "REJECTED_URL_TYPE" in str(item.get("admission_reason"))
                ),
                "candidates_rejected_low_identity": sum(
                    1
                    for item in stage_decisions
                    if any(
                        marker in str(item.get("admission_reason"))
                        for marker in ("LOW_IDENTITY", "LOW_PREFLIGHT", "WEAK_PRODUCT_PAGE")
                    )
                ),
                "candidates_scraped": len(scrape_candidates),
                "scrape_budget_remaining": budget.snapshot().scrape_remaining,
            }
        )

    state.termination_reason = "THREE_STAGE_PRECISION_SEARCH_COMPLETED"
    state.search_stage_trace = stage_trace
    product_match = self.selector.select(
        task=product,
        scorecards=state.scorecards,
        termination_reason=state.termination_reason,
        budget_snapshot=budget.snapshot(),
        state=state,
    )
    from src.product_evidence_harness.pipeline import ProductEvidenceHarness as LegacyHarness

    product_match = LegacyHarness._enforce_production_grade_product_url(
        product_match,
        state,
        production_gate=self.production_gate,
    )
    state.final_result = product_match

    assessments = ()
    evidence_set = None
    if feature_schema is not None:
        assessments = self._assess_features(product, feature_schema, state)
        evidence_set = EvidenceSetSelector(
            max_supplementary_urls=self.one_credit.max_supplementary_urls
        ).select(
            schema=feature_schema,
            assessments=assessments,
            preferred_primary_url=product_match.product_url
            or product_match.best_available_url,
        )

    artifact_dir = None
    if self.one_credit.write_outputs and self.config.write_outputs:
        artifact_dir = str(
            self._write_three_stage_outputs(
                product=product,
                state=state,
                product_match=product_match,
                feature_schema=feature_schema,
                assessments=assessments,
                evidence_set=evidence_set,
                stage_trace=stage_trace,
            )
        )
    result = FeatureAwareHarnessResult(
        state=state,
        product_match=product_match,
        search_query=" || ".join(state.queries),
        feature_schema=feature_schema,
        feature_assessments=assessments,
        evidence_set=evidence_set,
        artifact_dir=artifact_dir,
    )
    logger.info(
        "Precision workflow completed | row_id={} | serp={} | candidates={} | full_scrapes={}/{}",
        product.row_id,
        budget.organic_used,
        len(state.candidates),
        budget.scrape_used,
        maximum_full_scrapes,
    )
    return result if return_trace else product_match


def _flatten_serp(state: ProductSearchState) -> list[dict[str, Any]]:
    stage_by_query = {
        item.get("query"): item
        for item in getattr(state, "search_stage_trace", [])
        if item.get("query")
    }
    rows: list[dict[str, Any]] = []
    for response in state.organic_responses:
        stage = stage_by_query.get(response.query, {})
        for result in response.results:
            from src.product_evidence_harness.candidate_precision import canonicalize_candidate_url

            rows.append(
                {
                    "serp_credit": stage.get("serp_credit"),
                    "stage": stage.get("name"),
                    "scope": stage.get("scope"),
                    "query": response.query,
                    "position": result.position,
                    "original_url": result.url,
                    "url": canonicalize_candidate_url(result.url),
                    "title": result.title,
                    "snippet": result.snippet,
                    "search_status": result.search_status,
                }
            )
    return rows


def _apply_writer_patch(cls) -> None:
    original = cls._write_three_stage_outputs

    def writer(self, **kwargs):
        root = original(self, **kwargs)
        state = kwargs["state"]
        payload = {
            "candidate_admissions": list(
                getattr(state, "candidate_admissions", {}).values()
            ),
            "candidates": [candidate.to_dict() for candidate in state.candidates],
            "scrapes": {url: item.to_dict() for url, item in state.scrapes.items()},
            "verifications": {
                url: item.to_dict() for url, item in state.verifications.items()
            },
            "scorecards": [card.to_dict() for card in state.scorecards],
            "serp_results": _flatten_serp(state),
        }
        Path(root, "candidate_state.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return root

    cls._write_three_stage_outputs = writer


def apply_precision_search_patches() -> None:
    from src.product_evidence_harness.three_stage_pipeline import (
        ThreeStageProductEvidenceHarness,
    )

    if getattr(ThreeStageProductEvidenceHarness, "_precision_runtime_applied", False):
        return
    ThreeStageProductEvidenceHarness.run = _precision_run
    _apply_writer_patch(ThreeStageProductEvidenceHarness)
    ThreeStageProductEvidenceHarness._precision_runtime_applied = True
