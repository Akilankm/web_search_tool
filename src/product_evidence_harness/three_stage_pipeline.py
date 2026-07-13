from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from loguru import logger

from src.product_evidence_harness.budget import BudgetTracker
from src.product_evidence_harness.contracts import ProductQuery, ProductSearchState, URLCandidate
from src.product_evidence_harness.feature_evidence import EvidenceSetSelector
from src.product_evidence_harness.feature_schema import FeatureSchema
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.one_credit_pipeline import (
    FeatureAwareHarnessResult,
    OneCreditProductEvidenceHarness,
)


@dataclass(frozen=True, slots=True)
class SearchStage:
    name: str
    scope: str
    query: str
    language_code: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "scope": self.scope,
            "query": self.query,
            "language_code": self.language_code,
        }


class ThreeStageProductEvidenceHarness(OneCreditProductEvidenceHarness):
    """Strict three-credit product discovery.

    Stage order is immutable:
      1. requested retailer in the requested country, or primary country search
         when retailer_name is absent;
      2. alternative retailers in the requested country;
      3. unrestricted global fallback.

    Search remains feature-agnostic. The requested feature schema is used only
    after candidate pages have been scraped.
    """

    max_serp_credits: int = 3
    scrape_top_k_per_stage: int = 6

    def __post_init__(self) -> None:
        super().__post_init__()
        self.candidate_store.max_pool_size = max(
            self.candidate_store.max_pool_size,
            min(100, max(30, int(self.config.max_candidate_pool))),
        )

    def run(
        self,
        product: ProductQuery,
        *,
        feature_schema: FeatureSchema | None = None,
        return_trace: bool = False,
    ):
        product = self._with_language(product)
        per_stage = max(1, int(self.scrape_top_k_per_stage))
        budget = BudgetTracker(
            max_organic=self.max_serp_credits,
            max_ai_mode=0,
            max_scrapes=per_stage * self.max_serp_credits,
        )
        state = ProductSearchState(task=product, budget=budget)
        state.identity_graph = ProductIdentityGraphBuilder().build(product)
        stage_trace: list[dict[str, Any]] = []

        for stage_index in range(self.max_serp_credits):
            stage = self._build_stage(product, state, stage_index)
            budget.consume_organic()
            response = self._search_stage(stage, product)
            state.queries.append(stage.query)
            state.organic_responses.append(response)

            before_urls = {candidate.url for candidate in state.candidates}
            merged = self.candidate_store.merge_organic(state.candidates, response)
            state.candidates = self._tag_stage(merged, stage)
            ranked = self._preflight_rank(product, state.candidates)
            state.candidates = ranked[: self.candidate_store.max_pool_size]

            stage_candidates = [
                candidate
                for candidate in state.candidates
                if stage.query in candidate.query_sources
                and candidate.url not in state.scrapes
            ][:per_stage]
            scrape_results = self._scrape_many(stage_candidates, product, budget)
            for candidate, scrape in zip(stage_candidates, scrape_results):
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
            stage_trace.append(
                {
                    **stage.to_dict(),
                    "serp_credit": stage_index + 1,
                    "results_returned": len(response.results),
                    "new_candidate_urls": len({c.url for c in state.candidates} - before_urls),
                    "candidates_scraped": len(stage_candidates),
                }
            )

        state.termination_reason = "THREE_STAGE_SEARCH_COMPLETED"
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
        state.search_stage_trace = stage_trace

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
            "Three-stage workflow completed | row_id={} | serp_calls={} | "
            "candidates={} | scrapes={} | product_url={} | coding_status={}",
            product.row_id,
            budget.organic_used,
            len(state.candidates),
            budget.scrape_used,
            product_match.product_url,
            evidence_set.status if evidence_set else "FEATURE_SCHEMA_NOT_PROVIDED",
        )
        return result if return_trace else product_match

    def _build_stage(
        self,
        product: ProductQuery,
        state: ProductSearchState,
        stage_index: int,
    ) -> SearchStage:
        language = product.language_code or "en"
        if stage_index == 0:
            if product.retailer_name:
                return SearchStage(
                    name="requested_retailer_country",
                    scope="country",
                    query=self.query_builder.requested_retailer_search(product),
                    language_code=language,
                )
            return SearchStage(
                name="country_primary",
                scope="country",
                query=self.query_builder.country_alternative_search(
                    product,
                    language_index=0,
                ),
                language_code=language,
            )

        if stage_index == 1:
            if product.retailer_name:
                query = self.query_builder.country_alternative_search(
                    product,
                    language_index=0,
                )
            elif self.query_builder.country_language_count(product) > 1:
                query = self.query_builder.country_alternative_search(
                    product,
                    language_index=1,
                )
            else:
                query = self.query_builder.repair_from_state(
                    state,
                    global_fallback=False,
                    include_retailer=False,
                )
            if query in state.queries:
                query = self.query_builder.repair_from_state(
                    state,
                    global_fallback=False,
                    include_retailer=False,
                )
            return SearchStage(
                name="country_alternative",
                scope="country",
                query=query,
                language_code=language,
            )

        return SearchStage(
            name="global_fallback",
            scope="global",
            query=self.query_builder.global_fallback(
                product,
                include_retailer=False,
            ),
            language_code=self.config.global_fallback_language_code or "en",
        )

    def _search_stage(self, stage: SearchStage, product: ProductQuery):
        try:
            return self.organic_client.search(
                stage.query,
                product=product,
                scope=stage.scope,
                language_code=stage.language_code,
                country_code=product.country_code if stage.scope == "country" else None,
            )
        except TypeError:
            return self.organic_client.search(stage.query, product=product)

    @staticmethod
    def _tag_stage(
        candidates: list[URLCandidate],
        stage: SearchStage,
    ) -> list[URLCandidate]:
        marker = f"scope_{stage.name}"
        tagged: list[URLCandidate] = []
        for candidate in candidates:
            if stage.query not in candidate.query_sources:
                tagged.append(candidate)
                continue
            tagged.append(
                replace(
                    candidate,
                    source_types=tuple(
                        sorted(set(candidate.source_types) | {marker})
                    ),
                )
            )
        return tagged

    def _write_three_stage_outputs(
        self,
        *,
        product: ProductQuery,
        state: ProductSearchState,
        product_match,
        feature_schema,
        assessments,
        evidence_set,
        stage_trace: list[dict[str, Any]],
    ) -> Path:
        root = Path(self.one_credit.output_dir or self.config.output_dir) / product.row_id
        root.mkdir(parents=True, exist_ok=True)
        result_payload = {
            "product": product.to_dict(),
            "search": {
                "queries": list(state.queries),
                "stages": stage_trace,
                "serpapi_requests_used": state.budget.organic_used,
                "serpapi_request_limit": self.max_serp_credits,
                "policy": "THREE_STAGE_RETAILER_COUNTRY_GLOBAL",
                "feature_schema_used_by_search": False,
            },
            "product_match": product_match.to_dict(),
            "feature_schema": feature_schema.to_dict() if feature_schema else None,
            "feature_assessments": [
                assessment.to_dict() for assessment in assessments
            ],
            "evidence_set": evidence_set.to_dict() if evidence_set else None,
        }
        (root / "result.json").write_text(
            json.dumps(result_payload, indent=2, ensure_ascii=False, default=str)
            + "\n",
            encoding="utf-8",
        )
        self._write_candidates(root / "candidates.csv", state.scorecards)
        self._write_feature_evidence(root / "feature_evidence.csv", assessments)
        (root / "review.md").write_text(
            self._review_three_stage(
                product,
                product_match,
                state,
                evidence_set,
                stage_trace,
            ),
            encoding="utf-8",
        )
        return root

    @staticmethod
    def _review_three_stage(
        product,
        match,
        state,
        evidence_set,
        stage_trace,
    ) -> str:
        lines = [
            f"# Product evidence review — {product.row_id}",
            "",
            "## Three-stage search contract",
            "",
            "| Credit | Stage | Scope | Query | Results | Scraped |",
            "|---:|---|---|---|---:|---:|",
        ]
        for stage in stage_trace:
            lines.append(
                f"| {stage['serp_credit']} | `{stage['name']}` | "
                f"`{stage['scope']}` | `{stage['query']}` | "
                f"{stage['results_returned']} | {stage['candidates_scraped']} |"
            )
        lines.extend(
            [
                "",
                f"- SerpAPI requests used: `{state.budget.organic_used}` / `3`",
                "- Feature list used by search: `No`",
                "- Feature list used after scraping: `Yes`",
                "",
                "## Product URL decision",
                "",
                f"- Product URL before strict browser acceptance: "
                f"`{match.product_url or 'NONE'}`",
                f"- Best review URL: `{match.best_available_url or 'NONE'}`",
                f"- Status: `{match.url_decision_status}`",
                f"- Exact product: `{match.is_exact_product_match}`",
                f"- Confidence: `{match.confidence}`",
                "",
            ]
        )
        if evidence_set:
            lines.extend(
                [
                    "## Feature evidence set",
                    "",
                    f"- Coding status before strict browser acceptance: "
                    f"`{evidence_set.status}`",
                    f"- Required-feature coverage: "
                    f"`{evidence_set.required_coverage:.1%}`",
                    f"- Critical-feature coverage: "
                    f"`{evidence_set.critical_coverage:.1%}`",
                    f"- Missing features: "
                    f"`{', '.join(evidence_set.missing_features) or 'NONE'}`",
                    f"- Conflicting features: "
                    f"`{', '.join(evidence_set.conflicting_features) or 'NONE'}`",
                    "",
                ]
            )
        lines.extend(
            [
                "## Decision principle",
                "",
                "The final orchestrator accepts a primary URL only after dedicated "
                "browser verification confirms that the page opens, is the exact "
                "product, remains scrapable, is durable rather than signed/expiring, "
                "and the same URL contains every requested feature.",
                "",
            ]
        )
        return "\n".join(lines)
