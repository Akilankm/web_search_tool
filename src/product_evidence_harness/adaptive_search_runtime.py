from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from loguru import logger

from src.product_evidence_harness.adaptive_search import (
    DEFAULT_ALLOWED_ENGINES,
    BudgetAwareSearchPlanner,
    SearchAction,
    SearchHandle,
    SearchObservation,
    SerpAPIMultiEngineClient,
)
from src.product_evidence_harness.budget import BudgetTracker
from src.product_evidence_harness.candidate_precision import CandidatePrecisionGate
from src.product_evidence_harness.contracts import (
    OrganicSearchResponse,
    ProductQuery,
    ProductSearchState,
)
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


def _bounded_float(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


def _enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _adaptive_run(
    self,
    product: ProductQuery,
    *,
    feature_schema=None,
    return_trace: bool = False,
):
    product = self._with_language(product)
    max_credits = _bounded_int("PRODUCT_HARNESS_MAX_SERPAPI_CREDITS", 3, 1, 3)
    maximum_full_scrapes = _bounded_int(
        "PRODUCT_HARNESS_MAX_FULL_SCRAPES", 6, 1, 12
    )
    maximum_per_domain = _bounded_int(
        "PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN", 2, 1, 4
    )
    minimum_score = _bounded_float(
        "PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE", 0.28, 0.05, 0.95
    )
    early_stop = _enabled("PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL", True)
    gate = CandidatePrecisionGate(
        minimum_score=minimum_score,
        maximum_full_scrapes=maximum_full_scrapes,
        maximum_per_domain=maximum_per_domain,
    )
    budget = BudgetTracker(
        max_organic=max_credits,
        max_ai_mode=0,
        max_scrapes=maximum_full_scrapes,
    )
    state = ProductSearchState(task=product, budget=budget)
    state.identity_graph = ProductIdentityGraphBuilder().build(product)
    state.candidate_admissions = {}
    state.search_observations = []
    state.search_handles = []
    state.search_actions = []
    state.search_raw_payloads = []

    router = getattr(self, "adaptive_search_router", None) or SerpAPIMultiEngineClient(
        self.serp_config
    )
    planner = getattr(self, "adaptive_search_planner", None) or BudgetAwareSearchPlanner(
        require_llm=_enabled("PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING", True),
        max_context_candidates=_bounded_int(
            "PRODUCT_HARNESS_SEARCH_PLANNER_MAX_CANDIDATES", 8, 3, 20
        ),
    )

    observations: list[SearchObservation] = []
    handles: list[SearchHandle] = []
    used_signatures: set[str] = set()
    action_trace: list[dict[str, Any]] = []
    provisional_match = None
    working_url_found = False
    stop_reason = "SERPAPI_CREDIT_BUDGET_EXHAUSTED"

    for credit_index in range(max_credits):
        credit_number = credit_index + 1
        rejection_summary = _rejection_summary(
            getattr(state, "candidate_admissions", {})
        )
        action = planner.choose_action(
            product=product,
            credit_number=credit_number,
            credits_remaining=max_credits - credit_index,
            observations=observations,
            handles=handles,
            candidates=state.candidates,
            rejection_summary=rejection_summary,
            used_signatures=used_signatures,
        )
        if action.signature() in used_signatures:
            action = planner.deterministic_fallback(
                product=product,
                credit_number=credit_number,
                observations=observations,
                handles=handles,
                used_signatures=used_signatures,
                available_engines=planner._available_engines(product, handles),
                fallback_reason="duplicate planner action",
            )
        used_signatures.add(action.signature())
        budget.consume_organic()

        try:
            observation = router.execute(action, product)
        except Exception as exc:
            observation = SearchObservation(
                action=action,
                status="Error",
                search_id=None,
                results=[],
                error=f"{type(exc).__name__}: {exc}",
            )
        observations.append(observation)
        handles = _merge_handles(handles, observation.handles)
        state.search_observations = [item.compact_dict() for item in observations]
        state.search_handles = [item.to_dict() for item in handles]
        state.search_actions = [item.action.to_dict() for item in observations]
        state.search_raw_payloads.append(observation.raw_payload)

        response = observation.to_response()
        state.queries.append(response.query)
        state.organic_responses.append(response)
        before_urls = {candidate.url for candidate in state.candidates}
        state.candidates = self.candidate_store.merge_organic(
            state.candidates,
            response,
        )
        state.candidates = _tag_engine(
            state.candidates,
            response=response,
            action=action,
            credit_number=credit_number,
        )
        state.candidates = self._preflight_rank(product, state.candidates)[
            : self.candidate_store.max_pool_size
        ]

        pool = [
            candidate
            for candidate in state.candidates
            if candidate.url not in state.scrapes
        ]
        existing_domains = Counter(domain_of(url) for url in state.scrapes)
        pool = [
            candidate
            for candidate in pool
            if existing_domains.get(
                candidate.domain or domain_of(candidate.url), 0
            )
            < maximum_per_domain
        ]
        remaining_scrapes = budget.snapshot().scrape_remaining
        remaining_credits = max_credits - credit_index
        allowance = (
            0
            if remaining_scrapes <= 0
            else min(
                remaining_scrapes,
                max(1, (remaining_scrapes + remaining_credits - 1) // remaining_credits),
            )
        )
        scrape_candidates, decisions = gate.select_for_scrape(
            product=product,
            candidates=pool,
            already_scraped=state.scrapes,
            maximum_new=allowance,
        )
        for candidate in state.candidates:
            decision = decisions.get(candidate.url) or gate.evaluate(
                product, candidate
            )
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
        provisional_match = _select_provisional(self, product, state, budget)
        working_url_found = _working_url_found(self, provisional_match)

        decisions_for_credit = [
            state.candidate_admissions[candidate.url]
            for candidate in state.candidates
            if response.query in candidate.query_sources
            and candidate.url in state.candidate_admissions
        ]
        trace_row = {
            "serp_credit": credit_number,
            "name": f"adaptive_credit_{credit_number}",
            "engine": action.engine,
            "purpose": action.purpose,
            "planner_source": action.planner_source,
            "scope": action.scope,
            "query": action.query,
            "page_token_used": bool(action.page_token),
            "image_used": bool(action.image_url),
            "language_code": action.language_code or product.language_code,
            "country_code": action.country_code or product.country_code,
            "reason": action.reason,
            "expected_signals": list(action.expected_signals),
            "status": observation.status,
            "search_id": observation.search_id,
            "raw_results_seen": observation.raw_result_count,
            "results_returned": len(observation.results),
            "handles_discovered": len(observation.handles),
            "new_candidate_urls": len(
                {candidate.url for candidate in state.candidates} - before_urls
            ),
            "canonical_candidates_seen": len(state.candidates),
            "candidates_qualified": sum(
                1
                for item in decisions_for_credit
                if item.get("admitted_for_scrape")
            ),
            "candidates_scraped": len(scrape_candidates),
            "scrape_budget_remaining": budget.snapshot().scrape_remaining,
            "working_url_found": working_url_found,
            "current_best_url": (
                provisional_match.product_url
                if provisional_match is not None
                else None
            ),
            "current_best_confidence": (
                provisional_match.confidence
                if provisional_match is not None
                else 0.0
            ),
            "error": observation.error,
        }
        action_trace.append(trace_row)

        logger.info(
            "Adaptive search credit {}/{} | engine={} | urls={} | handles={} | "
            "scraped={} | working_url={}",
            credit_number,
            max_credits,
            action.engine,
            len(observation.results),
            len(observation.handles),
            len(scrape_candidates),
            provisional_match.product_url if provisional_match else None,
        )
        if early_stop and working_url_found:
            stop_reason = "WORKING_EXACT_PRODUCT_URL_FOUND"
            trace_row["early_stop"] = True
            break

    state.termination_reason = (
        "ADAPTIVE_SEARCH_WORKING_URL_FOUND"
        if working_url_found
        else "ADAPTIVE_SEARCH_CREDIT_BUDGET_EXHAUSTED"
    )
    state.search_stage_trace = action_trace
    state.serpapi_credits_used = budget.organic_used
    state.search_stop_reason = stop_reason
    state.search_planner_calls = int(getattr(planner, "calls", 0))
    state.search_planner_fallbacks = int(getattr(planner, "fallbacks", 0))

    product_match = _select_provisional(self, product, state, budget)
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
                stage_trace=action_trace,
            )
        )
        _write_adaptive_artifacts(
            Path(artifact_dir),
            product=product,
            state=state,
            product_match=product_match,
            evidence_set=evidence_set,
            observations=observations,
            trace=action_trace,
            max_credits=max_credits,
            working_url_found=working_url_found,
            stop_reason=stop_reason,
            planner=planner,
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
        "Adaptive search completed | row_id={} | credits={}/{} | engines={} | "
        "candidates={} | scrapes={} | product_url={}",
        product.row_id,
        budget.organic_used,
        max_credits,
        ",".join(row["engine"] for row in action_trace),
        len(state.candidates),
        budget.scrape_used,
        product_match.product_url,
    )
    return result if return_trace else product_match


def _select_provisional(self, product, state, budget):
    match = self.selector.select(
        task=product,
        scorecards=state.scorecards,
        termination_reason=getattr(
            state, "termination_reason", "ADAPTIVE_SEARCH_IN_PROGRESS"
        ),
        budget_snapshot=budget.snapshot(),
        state=state,
    )
    from src.product_evidence_harness.pipeline import (
        ProductEvidenceHarness as LegacyHarness,
    )

    return LegacyHarness._enforce_production_grade_product_url(
        match,
        state,
        production_gate=self.production_gate,
    )


def _working_url_found(self, match) -> bool:
    if match is None or not match.product_url or not match.is_exact_product_match:
        return False
    return float(match.confidence or 0.0) >= float(
        self.config.with_effective_policy().policy.min_verified_confidence
    )


def _merge_handles(
    current: Sequence[SearchHandle],
    additions: Sequence[SearchHandle],
) -> list[SearchHandle]:
    output = list(current)
    seen = {(item.kind, item.value) for item in output}
    for item in additions:
        key = (item.kind, item.value)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _tag_engine(candidates, *, response: OrganicSearchResponse, action: SearchAction, credit_number: int):
    from dataclasses import replace

    marker_engine = f"engine_{action.engine}"
    marker_credit = f"credit_{credit_number}"
    output = []
    for candidate in candidates:
        if response.query not in candidate.query_sources:
            output.append(candidate)
            continue
        output.append(
            replace(
                candidate,
                source_types=tuple(
                    sorted(
                        set(candidate.source_types)
                        | {marker_engine, marker_credit, f"scope_{action.scope}"}
                    )
                ),
            )
        )
    return output


def _rejection_summary(
    decisions: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in decisions.values():
        reason = str(item.get("admission_reason") or "UNKNOWN")
        counts[reason] += 1
    return dict(counts.most_common(12))


def _flatten_adaptive_serp(state, trace) -> list[dict[str, Any]]:
    trace_by_credit = {int(item["serp_credit"]): item for item in trace}
    rows: list[dict[str, Any]] = []
    for credit, response in enumerate(state.organic_responses, start=1):
        action = trace_by_credit.get(credit, {})
        for result in response.results:
            rows.append(
                {
                    "serp_credit": credit,
                    "stage": action.get("name"),
                    "engine": action.get("engine"),
                    "purpose": action.get("purpose"),
                    "planner_source": action.get("planner_source"),
                    "scope": action.get("scope"),
                    "query": response.query,
                    "position": result.position,
                    "url": result.url,
                    "title": result.title,
                    "snippet": result.snippet,
                    "source_section": result.source,
                    "search_status": result.search_status,
                }
            )
    return rows


def _write_adaptive_artifacts(
    root: Path,
    *,
    product,
    state,
    product_match,
    evidence_set,
    observations,
    trace,
    max_credits,
    working_url_found,
    stop_reason,
    planner,
) -> None:
    result_path = root / "result.json"
    result_payload = {}
    if result_path.is_file():
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    result_payload["search"] = {
        "policy": "ADAPTIVE_THREE_CREDIT_MULTI_ENGINE",
        "maximum_serpapi_credits": max_credits,
        "serpapi_requests_used": state.budget.organic_used,
        "serpapi_request_limit": max_credits,
        "three_stage_contract_enforced": True,
        "adaptive_search_contract_enforced": True,
        "feature_schema_used_by_search": False,
        "allowed_engines": list(DEFAULT_ALLOWED_ENGINES),
        "engine_sequence": [item["engine"] for item in trace],
        "planner_calls": int(getattr(planner, "calls", 0)),
        "planner_fallbacks": int(getattr(planner, "fallbacks", 0)),
        "working_url_found_during_search": working_url_found,
        "stop_reason": stop_reason,
        "queries": list(state.queries),
        "stages": trace,
        "actions": [item.action.to_dict() for item in observations],
        "observations": [item.compact_dict() for item in observations],
        "handles": [item.to_dict() for item in _merge_handles([], [
            handle for observation in observations for handle in observation.handles
        ])],
        "serp_results": _flatten_adaptive_serp(state, trace),
    }
    result_payload.setdefault("product", product.to_dict())
    result_payload.setdefault("product_match", product_match.to_dict())
    result_path.write_text(
        json.dumps(result_payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    (root / "adaptive_search_trace.json").write_text(
        json.dumps(
            {
                "product": product.to_dict(),
                "search": result_payload["search"],
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    for index, observation in enumerate(observations, start=1):
        if not observation.raw_payload:
            continue
        safe_engine = observation.action.engine.replace("/", "_")
        (root / f"serp_credit_{index:02d}_{safe_engine}_raw.json").write_text(
            json.dumps(
                observation.raw_payload,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            + "\n",
            encoding="utf-8",
        )
    (root / "review.md").write_text(
        _adaptive_review(
            product=product,
            product_match=product_match,
            evidence_set=evidence_set,
            trace=trace,
            credits_used=state.budget.organic_used,
            max_credits=max_credits,
            working_url_found=working_url_found,
            stop_reason=stop_reason,
        ),
        encoding="utf-8",
    )


def _adaptive_review(
    *,
    product,
    product_match,
    evidence_set,
    trace,
    credits_used,
    max_credits,
    working_url_found,
    stop_reason,
) -> str:
    lines = [
        f"# Product evidence review — {product.row_id}",
        "",
        "## Adaptive SerpAPI credit decisions",
        "",
        "| Credit | Engine | Purpose | Planner | Results | Handles | Scraped | Working URL |",
        "|---:|---|---|---|---:|---:|---:|---|",
    ]
    for item in trace:
        lines.append(
            f"| {item['serp_credit']} | `{item['engine']}` | `{item['purpose']}` | "
            f"`{item['planner_source']}` | {item['results_returned']} | "
            f"{item['handles_discovered']} | {item['candidates_scraped']} | "
            f"`{item['working_url_found']}` |"
        )
    lines.extend(
        [
            "",
            f"- Credits used: `{credits_used}` / `{max_credits}`",
            f"- Stop reason: `{stop_reason}`",
            f"- Working exact-product URL found during search: `{working_url_found}`",
            f"- Final product URL before strict browser acceptance: "
            f"`{product_match.product_url or 'NONE'}`",
            f"- Best review URL: `{product_match.best_available_url or 'NONE'}`",
            f"- URL decision status: `{product_match.url_decision_status}`",
            f"- Confidence: `{product_match.confidence}`",
            "",
        ]
    )
    if evidence_set is not None:
        lines.extend(
            [
                "## Feature evidence",
                "",
                f"- Status: `{evidence_set.status}`",
                f"- Required coverage: `{evidence_set.required_coverage:.1%}`",
                f"- Critical coverage: `{evidence_set.critical_coverage:.1%}`",
                f"- Missing: `{', '.join(evidence_set.missing_features) or 'NONE'}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Decision principle",
            "",
            "Each SerpAPI credit is selected from the evidence obtained so far. "
            "The LLM chooses the next engine and query; deterministic code enforces "
            "the three-credit ceiling, prevents duplicate actions, validates every "
            "direct URL, and never accepts an unverified intermediary link.",
            "",
        ]
    )
    return "\n".join(lines)


def apply_adaptive_search_runtime_patch() -> None:
    from src.product_evidence_harness.three_stage_pipeline import (
        ThreeStageProductEvidenceHarness,
    )

    if getattr(ThreeStageProductEvidenceHarness, "_adaptive_search_runtime_applied", False):
        return
    ThreeStageProductEvidenceHarness.run = _adaptive_run
    ThreeStageProductEvidenceHarness._adaptive_search_runtime_applied = True
