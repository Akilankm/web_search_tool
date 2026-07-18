from __future__ import annotations

import json
import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from loguru import logger

from src.product_evidence_harness.belief import (
    MarketStage,
    ProductBeliefArtifactWriter,
    ProductBeliefEngine,
    ProductBeliefState,
)


_PATCHED = False
_ENGINE = ProductBeliefEngine()
_WRITER = ProductBeliefArtifactWriter()
_REGISTRY: dict[str, ProductBeliefState] = {}
_LOCK = threading.RLock()


def _key(product: Any) -> str:
    return "|".join(
        [
            str(getattr(product, "row_id", "")),
            str(getattr(product, "country_code", "")),
            str(getattr(product, "main_text", "")),
        ]
    )


def _get(product: Any, identity_graph: Any = None) -> ProductBeliefState:
    with _LOCK:
        state = _REGISTRY.get(_key(product))
        if state is None:
            state = _ENGINE.initialize(product, identity_graph)
            _REGISTRY[_key(product)] = state
        return state


def _store(product: Any, state: ProductBeliefState) -> None:
    with _LOCK:
        _REGISTRY[_key(product)] = state


def _market_from_url(product: Any, url: str) -> str:
    folded = (url or "").lower()
    retailer_tokens = [
        token
        for token in str(getattr(product, "retailer_name", "") or "")
        .lower()
        .replace("-", " ")
        .split()
        if len(token) >= 2
    ]
    if retailer_tokens and any(token in folded for token in retailer_tokens):
        return MarketStage.REQUESTED_RETAILER.value
    try:
        from src.product_evidence_harness.country_profiles import CountryProfileRegistry

        if CountryProfileRegistry.load().domain_matches_country(
            url, product.country_code
        ):
            return MarketStage.COUNTRY_ALTERNATIVE.value
    except Exception:
        pass
    return MarketStage.GLOBAL_FALLBACK.value


def _write(
    root: str | Path | None, product: Any, state: Any = None
) -> None:
    if not root:
        return
    belief = (
        getattr(state, "product_belief", None) if state is not None else None
    )
    belief = belief or _REGISTRY.get(_key(product))
    if belief is None:
        return
    try:
        _WRITER.write(root, belief)
    except Exception as exc:
        logger.warning(
            "Could not write product belief artifacts | row_id={} | error={}",
            getattr(product, "row_id", ""),
            type(exc).__name__,
        )


def _normalize_action(
    product: Any, belief: ProductBeliefState, action: Any, credit: int
) -> Any:
    from src.product_evidence_harness.adaptive_search import SearchEngine

    stage = _ENGINE.market_stage_for_credit(product, credit)
    belief.current_market_stage = stage.value
    query = _ENGINE.query_for_stage(
        product, belief, stage, diagnostic=credit > 1
    )
    engine = action.engine
    page_token = action.page_token
    image_url = action.image_url
    country_engines = {
        SearchEngine.GOOGLE.value,
        SearchEngine.GOOGLE_SHOPPING.value,
        SearchEngine.GOOGLE_AI_MODE.value,
        SearchEngine.AMAZON.value,
        SearchEngine.EBAY.value,
        SearchEngine.WALMART.value,
        SearchEngine.HOME_DEPOT.value,
    }
    if stage != MarketStage.GLOBAL_FALLBACK and engine not in country_engines:
        engine = SearchEngine.GOOGLE.value
        page_token = ""
        image_url = ""

    handle_engine = engine in {
        SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value,
        SearchEngine.GOOGLE_LENS.value,
    }
    normalized_query = (action.query or query) if handle_engine else query
    purpose = {
        MarketStage.REQUESTED_RETAILER: (
            "requested_retailer_exact_product_resolution"
        ),
        MarketStage.COUNTRY_ALTERNATIVE: (
            "same_country_alternative_retailer_resolution"
        ),
        MarketStage.GLOBAL_FALLBACK: "global_exact_product_fallback",
    }[stage]
    leading = belief.leading_hypothesis
    return replace(
        action,
        engine=engine,
        purpose=purpose,
        query=normalized_query,
        scope=(
            "global"
            if stage == MarketStage.GLOBAL_FALLBACK
            else "country"
        ),
        country_code=product.country_code,
        language_code=product.language_code or action.language_code or "en",
        page_token=page_token,
        image_url=image_url,
        expected_signals=tuple(
            dict.fromkeys(
                (
                    *action.expected_signals,
                    stage.value,
                    "browser_openable_product_url",
                    "information_rich_product_page",
                    "exact_product_identity",
                )
            )
        ),
        reason=(
            "Belief-driven market stage="
            f"{stage.value}; leading_hypothesis="
            f"{leading.canonical_name if leading else product.main_text}; "
            f"status={belief.resolution_status.value}; "
            f"margin={belief.posterior_margin:.3f}. {action.reason}"
        )[:1200],
        planner_source=f"belief_driven:{action.planner_source}",
    )


def _three_stage_run(
    self,
    product,
    *,
    feature_schema=None,
    return_trace: bool = False,
):
    from src.product_evidence_harness.budget import BudgetTracker
    from src.product_evidence_harness.contracts import ProductSearchState
    from src.product_evidence_harness.feature_evidence import EvidenceSetSelector
    from src.product_evidence_harness.identity.graph import (
        ProductIdentityGraphBuilder,
    )
    from src.product_evidence_harness.one_credit_pipeline import (
        FeatureAwareHarnessResult,
    )
    from src.product_evidence_harness.pipeline import (
        ProductEvidenceHarness as LegacyHarness,
    )

    product = self._with_language(product)
    per_stage = max(1, min(4, int(self.scrape_top_k_per_stage)))
    try:
        scrape_cap = int(
            os.getenv("PRODUCT_HARNESS_MAX_FULL_SCRAPES", "6")
        )
    except ValueError:
        scrape_cap = 6
    budget = BudgetTracker(
        max_organic=self.max_serp_credits,
        max_ai_mode=0,
        max_scrapes=max(1, min(12, scrape_cap)),
    )
    state = ProductSearchState(task=product, budget=budget)
    state.identity_graph = ProductIdentityGraphBuilder().build(product)
    belief = _get(product, state.identity_graph)
    state.product_belief = belief
    trace: list[dict[str, Any]] = []
    product_match = None
    working = False

    for stage_index in range(self.max_serp_credits):
        stage = self._build_stage(product, state, stage_index)
        if stage.scope == "global":
            belief.current_market_stage = MarketStage.GLOBAL_FALLBACK.value
        elif stage.name == "requested_retailer_country":
            belief.current_market_stage = MarketStage.REQUESTED_RETAILER.value
        else:
            belief.current_market_stage = (
                MarketStage.COUNTRY_ALTERNATIVE.value
            )

        budget.consume_organic()
        response = self._search_stage(stage, product)
        state.queries.append(stage.query)
        state.organic_responses.append(response)
        before = {candidate.url for candidate in state.candidates}
        state.candidates = self._tag_stage(
            self.candidate_store.merge_organic(
                state.candidates, response
            ),
            stage,
        )
        state.candidates = self._preflight_rank(
            product, state.candidates
        )[: self.candidate_store.max_pool_size]

        remaining = budget.snapshot().scrape_remaining
        stages_remaining = max(1, self.max_serp_credits - stage_index)
        allowance = (
            min(
                per_stage,
                remaining,
                max(
                    1,
                    (remaining + stages_remaining - 1)
                    // stages_remaining,
                ),
            )
            if remaining
            else 0
        )
        stage_candidates = [
            candidate
            for candidate in state.candidates
            if stage.query in candidate.query_sources
            and candidate.url not in state.scrapes
        ][:allowance]
        scrapes = self._scrape_many(stage_candidates, product, budget)
        for candidate, scrape in zip(stage_candidates, scrapes):
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
        product_match = self.selector.select(
            task=product,
            scorecards=state.scorecards,
            termination_reason=(
                f"BELIEF_MARKET_STAGE_{stage.name.upper()}"
            ),
            budget_snapshot=budget.snapshot(),
            state=state,
        )
        product_match = (
            LegacyHarness._enforce_production_grade_product_url(
                product_match,
                state,
                production_gate=self.production_gate,
            )
        )
        belief = _REGISTRY.get(_key(product), belief)
        state.product_belief = belief
        working = bool(
            product_match.product_url
            and product_match.is_exact_product_match
            and product_match.is_scrapable
            and product_match.validation_status == "VERIFIED"
        )
        leading = belief.leading_hypothesis
        trace.append(
            {
                **stage.to_dict(),
                "serp_credit": stage_index + 1,
                "market_stage": belief.current_market_stage,
                "results_returned": len(response.results),
                "new_candidate_urls": len(
                    {
                        candidate.url
                        for candidate in state.candidates
                    }
                    - before
                ),
                "candidates_scraped": len(stage_candidates),
                "belief_status": belief.resolution_status.value,
                "leading_hypothesis": (
                    leading.canonical_name if leading else None
                ),
                "leading_probability": (
                    leading.posterior_probability if leading else 0.0
                ),
                "posterior_margin": belief.posterior_margin,
                "working_browser_url_found": working,
            }
        )
        if working:
            break

    state.termination_reason = (
        "BELIEF_DRIVEN_URL_FOUND"
        if working
        else "BELIEF_DRIVEN_MARKET_PATH_EXHAUSTED"
    )
    if product_match is None:
        product_match = self.selector.select(
            task=product,
            scorecards=state.scorecards,
            termination_reason=state.termination_reason,
            budget_snapshot=budget.snapshot(),
            state=state,
        )
        product_match = (
            LegacyHarness._enforce_production_grade_product_url(
                product_match,
                state,
                production_gate=self.production_gate,
            )
        )
    else:
        product_match = replace(
            product_match,
            termination_reason=state.termination_reason,
        )
    state.final_result = product_match
    state.search_stage_trace = trace

    assessments = ()
    evidence_set = None
    if feature_schema is not None:
        assessments = self._assess_features(
            product, feature_schema, state
        )
        evidence_set = EvidenceSetSelector(
            max_supplementary_urls=(
                self.one_credit.max_supplementary_urls
            )
        ).select(
            schema=feature_schema,
            assessments=assessments,
            preferred_primary_url=(
                product_match.product_url
                or product_match.best_available_url
            ),
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
                stage_trace=trace,
            )
        )
        _write(artifact_dir, product, state)

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
        "Belief-driven market workflow completed | row_id={} | "
        "serp_calls={} | scrapes={} | belief={} | url={}",
        product.row_id,
        budget.organic_used,
        budget.scrape_used,
        belief.resolution_status.value,
        product_match.product_url,
    )
    return result if return_trace else product_match


def _enrich(
    payload: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    product = dict(payload.get("product") or payload)
    key = "|".join(
        [
            str(
                product.get("row_id")
                or (result.get("product") or {}).get("row_id")
                or ""
            ),
            str(
                product.get("country_code")
                or (result.get("product") or {}).get("country_code")
                or ""
            ),
            str(
                product.get("main_text")
                or (result.get("product") or {}).get("main_text")
                or ""
            ),
        ]
    )
    belief = _REGISTRY.get(key)
    if belief is None:
        return result
    leading = belief.leading_hypothesis
    result["product_identification"] = {
        "leading_hypothesis": (
            leading.to_dict() if leading else None
        ),
        "resolution_status": belief.resolution_status.value,
        "posterior_margin": belief.posterior_margin,
        "metrics": belief.to_dict()["metrics"],
        "critical_uncertainties": [
            item.to_dict() for item in belief.uncertainties[:5]
        ],
        "evidence_items": len(belief.evidence_ledger),
        "interpretation_source": belief.interpretation_source,
    }
    result.setdefault("search", {})["market_decision_path"] = list(
        belief.market_path
    )
    result["belief_artifacts"] = {
        "product_understanding": "product_understanding.md",
        "product_belief": "product_belief.json",
        "evidence_ledger": "evidence_ledger.jsonl",
        "belief_updates": "belief_updates.md",
        "market_decision_path": "market_decision_path.md",
    }
    artifact_dir = result.get("artifact_dir")
    if artifact_dir:
        _WRITER.write(artifact_dir, belief)
        try:
            (Path(artifact_dir) / "orchestrated_result.json").write_text(
                json.dumps(
                    result,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass
    return result


def apply_belief_driven_resolution_patch() -> None:
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.adaptive_search import (
        BudgetAwareSearchPlanner,
    )
    from src.product_evidence_harness.agent_service.orchestrator import (
        ProductEvidenceOrchestrator,
    )
    from src.product_evidence_harness.agent_service.strict_orchestrator import (
        StrictProductEvidenceOrchestrator,
    )
    from src.product_evidence_harness.artifacts import ArtifactWriter
    from src.product_evidence_harness.constants import (
        IDENTITY_MISMATCH,
        IDENTITY_PROBABLE,
        IDENTITY_UNVERIFIED,
        IDENTITY_VERIFIED,
        IDENTITY_WEAK,
    )
    from src.product_evidence_harness.contracts import ProductSearchState
    from src.product_evidence_harness.identity_verifier import (
        ProductIdentityVerifier,
    )
    from src.product_evidence_harness.one_credit_pipeline import (
        OneCreditProductEvidenceHarness,
    )
    from src.product_evidence_harness.pipeline import ProductEvidenceHarness
    from src.product_evidence_harness.ranker import ProductURLRanker
    from src.product_evidence_harness.selector import FinalSelector
    from src.product_evidence_harness.source_authority import (
        SourceAuthorityPolicy,
    )
    from src.product_evidence_harness.three_stage_pipeline import (
        SearchStage,
        ThreeStageProductEvidenceHarness,
    )
    import src.product_evidence_harness.adaptive_search_runtime as adaptive_runtime

    SourceAuthorityPolicy.hierarchy = lambda self, product: (
        (
            "REQUESTED_RETAILER",
            "COUNTRY_ALTERNATIVE",
            "GLOBAL_FALLBACK",
        )
        if product.retailer_name
        else ("COUNTRY_ALTERNATIVE", "GLOBAL_FALLBACK")
    )

    original_sort = ProductURLRanker._sort_key

    def market_sort_key(self, card):
        base = original_sort(self, card)
        requested = 1 if card.retailer_check == "MATCHED" else 0
        in_country = (
            1
            if card.country_check in {"MATCHED", "NOT_PROVIDED"}
            else 0
        )
        global_fallback = (
            1 if card.country_check == "ALTERNATIVE" else 0
        )
        # Preserve identity/scrapability as the first two gates, then apply
        # market precedence before authority/richness tie-breakers.
        return (
            base[0],
            base[1],
            requested,
            in_country,
            global_fallback,
            *base[2:],
        )

    ProductURLRanker._sort_key = market_sort_key

    def market_key(card):
        scrape = card.scrape
        identity_rank = {
            IDENTITY_VERIFIED: 5,
            IDENTITY_PROBABLE: 4,
            IDENTITY_WEAK: 3,
            IDENTITY_UNVERIFIED: 2,
            IDENTITY_MISMATCH: 0,
        }.get(
            card.verification.identity_status
            if card.verification
            else IDENTITY_UNVERIFIED,
            1,
        )
        return (
            identity_rank,
            1 if not card.hard_failures else 0,
            1
            if card.llm_decision
            in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"}
            else 0,
            1 if scrape and scrape.is_scrapable else 0,
            1 if scrape and scrape.looks_like_product_page else 0,
            1 if scrape and scrape.reachable else 0,
            1 if card.retailer_check == "MATCHED" else 0,
            1
            if card.country_check in {"MATCHED", "NOT_PROVIDED"}
            else 0,
            1 if card.country_check == "ALTERNATIVE" else 0,
            card.richness_score,
            card.final_confidence,
        )

    def select_exact(self, cards):
        return next(
            (
                card
                for card in sorted(
                    cards, key=market_key, reverse=True
                )
                if card.validation_status == "VERIFIED"
                and self._is_final_usable(card)
            ),
            None,
        )

    def select_best(
        self, cards, *, allow_hard_rejected: bool = False
    ):
        candidates = (
            list(cards)
            if allow_hard_rejected
            else [card for card in cards if not card.hard_failures]
        )
        return (
            sorted(candidates, key=market_key, reverse=True)[0]
            if candidates
            else None
        )

    FinalSelector._select_exact_card = select_exact
    FinalSelector._select_best_available_card = select_best
    adaptive_runtime._working_url_found = lambda self, match: bool(
        match
        and match.product_url
        and match.is_exact_product_match
        and float(match.confidence or 0.0)
        >= float(
            self.config.with_effective_policy().policy.min_verified_confidence
        )
    )

    original_verify = ProductIdentityVerifier.verify

    def verify(self, product, scrape, *args, **kwargs):
        verification = original_verify(
            self, product, scrape, *args, **kwargs
        )
        belief = _get(product, kwargs.get("identity_graph"))
        _ENGINE.update_from_scrape(
            belief,
            product,
            scrape,
            verification,
            market_stage=_market_from_url(
                product, scrape.final_url or scrape.url
            ),
        )
        _store(product, belief)
        return verification

    ProductIdentityVerifier.verify = verify

    original_choose = BudgetAwareSearchPlanner.choose_action
    original_fallback = BudgetAwareSearchPlanner.deterministic_fallback

    def choose(self, *args, **kwargs):
        product = kwargs["product"]
        credit = int(kwargs.get("credit_number") or 1)
        action = original_choose(self, *args, **kwargs)
        if str(action.planner_source).startswith("belief_driven:"):
            return action
        return _normalize_action(
            product, _get(product), action, credit
        )

    def fallback(self, *args, **kwargs):
        product = kwargs["product"]
        credit = int(kwargs.get("credit_number") or 1)
        return _normalize_action(
            product,
            _get(product),
            original_fallback(self, *args, **kwargs),
            credit,
        )

    BudgetAwareSearchPlanner.choose_action = choose
    BudgetAwareSearchPlanner.deterministic_fallback = fallback

    original_build_stage = ThreeStageProductEvidenceHarness._build_stage

    def build_stage(self, product, state, stage_index):
        original = original_build_stage(
            self, product, state, stage_index
        )
        belief = _get(
            product, getattr(state, "identity_graph", None)
        )
        market = _ENGINE.market_stage_for_credit(
            product, stage_index + 1
        )
        belief.current_market_stage = market.value
        return SearchStage(
            name={
                MarketStage.REQUESTED_RETAILER: (
                    "requested_retailer_country"
                ),
                MarketStage.COUNTRY_ALTERNATIVE: (
                    "country_alternative"
                ),
                MarketStage.GLOBAL_FALLBACK: "global_fallback",
            }[market],
            scope=(
                "global"
                if market == MarketStage.GLOBAL_FALLBACK
                else "country"
            ),
            query=_ENGINE.query_for_stage(
                product,
                belief,
                market,
                diagnostic=stage_index > 0,
            ),
            language_code=(
                self.config.global_fallback_language_code or "en"
                if market == MarketStage.GLOBAL_FALLBACK
                else (
                    product.language_code
                    or original.language_code
                    or "en"
                )
            ),
        )

    ThreeStageProductEvidenceHarness._build_stage = build_stage
    ThreeStageProductEvidenceHarness.run = _three_stage_run

    original_one = OneCreditProductEvidenceHarness.run

    def one(self, product, *args, **kwargs):
        _get(product)
        result = original_one(self, product, *args, **kwargs)
        state = getattr(result, "state", None)
        if state is not None:
            state.product_belief = _REGISTRY.get(_key(product))
        _write(getattr(result, "artifact_dir", None), product, state)
        return result

    OneCreditProductEvidenceHarness.run = one

    original_legacy = ProductEvidenceHarness.run

    def legacy(self, product, *args, **kwargs):
        _get(product)
        result = original_legacy(self, product, *args, **kwargs)
        if getattr(result, "state", None) is not None:
            result.state.product_belief = _REGISTRY.get(
                _key(product)
            )
        return result

    ProductEvidenceHarness.run = legacy

    original_state_dict = ProductSearchState.to_dict

    def state_dict(self):
        data = original_state_dict(self)
        belief = getattr(
            self, "product_belief", None
        ) or _REGISTRY.get(_key(self.task))
        data["product_belief"] = (
            belief.to_dict() if belief else None
        )
        return data

    ProductSearchState.to_dict = state_dict

    original_write_state = ArtifactWriter.write_state

    def write_state(self, state):
        state.product_belief = getattr(
            state, "product_belief", None
        ) or _REGISTRY.get(_key(state.task))
        root = original_write_state(self, state)
        _write(root, state.task, state)
        return root

    ArtifactWriter.write_state = write_state

    original_orchestrator = ProductEvidenceOrchestrator.run
    original_strict = StrictProductEvidenceOrchestrator.run

    def orchestrator_run(self, payload, *args, **kwargs):
        return _enrich(
            payload,
            original_orchestrator(self, payload, *args, **kwargs),
        )

    def strict_run(self, payload, *args, **kwargs):
        return _enrich(
            payload,
            original_strict(self, payload, *args, **kwargs),
        )

    ProductEvidenceOrchestrator.run = orchestrator_run
    StrictProductEvidenceOrchestrator.run = strict_run
