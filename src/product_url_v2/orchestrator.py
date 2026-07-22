from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from product_url_v2.acquisition import PageAcquirer
from product_url_v2.artifacts import ArtifactWriter
from product_url_v2.browser import BrowserClient, select_browser_candidates
from product_url_v2.config import RuntimeConfig, load_feature_set
from product_url_v2.evaluation import apply_browser_evidence, assess_candidate, choose_delivery
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import (
    DeliveryDecision,
    DeliveryStatus,
    PipelineStage,
    ProductInput,
    ResolutionResult,
    RunEvent,
    SearchObservation,
    to_jsonable,
)
from product_url_v2.reasoning import ReasoningPort, ReasoningSettings, StructuredIdentityReasoner
from product_url_v2.search import InformationGainSearchPlanner, SearchClient, SerpAPIClient
from product_url_v2.trace import candidate_judgment, candidate_ranking, interpretation_summary

ProgressCallback = Callable[[RunEvent], None]


@dataclass(slots=True)
class ProductURLOrchestrator:
    config: RuntimeConfig
    search_client: SearchClient | None = None
    acquirer: PageAcquirer | None = None
    browser_client: BrowserClient | None = None
    reasoner: ReasoningPort | None = None

    def resolve(self, product: ProductInput, progress: ProgressCallback | None = None) -> ResolutionResult:
        started = time.perf_counter()
        runtime = self.config.with_runtime_options(product.runtime_options)
        writer = ArtifactWriter(runtime.artifact_root)
        events: list[RunEvent] = []
        interpretation = None
        observations: tuple[SearchObservation, ...] = ()
        candidates = ()

        def emit(stage: PipelineStage, event_type: str, message: str, **details: Any) -> None:
            event = RunEvent(len(events) + 1, stage, event_type, message, details)
            events.append(event)
            if progress:
                progress(event)

        try:
            emit(
                PipelineStage.INTERPRET,
                "START",
                "Interpreting submitted product identity and commercial-form uncertainty.",
                row_id=product.row_id,
                country_code=product.country_code,
                retailer_name=product.retailer_name,
                ean_supplied=bool(product.ean),
                language_code=product.language_code,
                feature_set=product.feature_set,
                reasoning_enabled=runtime.reasoning.enabled,
                reasoning_required=runtime.reasoning.required,
            )
            deterministic = DeterministicProductInterpreter().interpret(product)
            emit(
                PipelineStage.INTERPRET,
                "DETERMINISTIC_INTERPRETATION",
                f"Extracted {len(deterministic.signals)} identity signal(s) and {len(deterministic.hypotheses)} initial hypothesis/hypotheses.",
                **interpretation_summary(deterministic),
            )

            reasoner = self.reasoner or StructuredIdentityReasoner(ReasoningSettings.from_runtime(runtime.reasoning))
            interpretation = reasoner.refine(product, deterministic)
            llm_inference_count = sum(1 for item in interpretation.signals if item.source == "LLM_INFERENCE")
            emit(
                PipelineStage.INTERPRET,
                "INTERPRETATION_READY",
                f"Prepared {len(interpretation.hypotheses)} competing product hypothesis/hypotheses for search.",
                llm_reasoning_enabled=runtime.reasoning.enabled,
                llm_inference_count=llm_inference_count,
                **interpretation_summary(interpretation),
            )

            feature_set = load_feature_set(runtime.feature_set_root, product.feature_set)
            artifact_dir = writer.write_intermediate(
                product.row_id,
                input_payload=to_jsonable(product),
                interpretation=interpretation,
            )
            emit(
                PipelineStage.INTERPRET,
                "COMPLETE",
                "Identity interpretation and hypothesis construction completed.",
                unresolved=list(interpretation.unresolved_discriminators),
                required_coding_fields=list(feature_set.get("required_fields") or []),
            )

            emit(
                PipelineStage.SEARCH,
                "START",
                "Running the bounded hypothesis-driven paid search campaign.",
                credit_limit=runtime.search.credit_limit,
                results_per_search=runtime.search.results_per_search,
            )
            client = self.search_client or SerpAPIClient.from_env(runtime)

            def search_progress(event_type: str, details: Mapping[str, Any]) -> None:
                messages = {
                    "SEARCH_ACTION": f"Executing search credit {details.get('credit_number')}: {details.get('purpose')}.",
                    "SEARCH_OBSERVATION": f"Search credit {details.get('credit_number')} returned {details.get('result_count')} external observation(s).",
                    "SEARCH_CANDIDATES": f"Admitted {details.get('candidate_count')} structurally product-like URL candidate(s).",
                }
                emit(PipelineStage.SEARCH, event_type, messages.get(event_type, "Search evidence updated."), **dict(details))

            campaign = InformationGainSearchPlanner(runtime).run(
                product,
                interpretation,
                client,
                progress=search_progress,
            )
            observations = campaign.observations
            writer.write_intermediate(product.row_id, search=campaign)
            emit(
                PipelineStage.SEARCH,
                "COMPLETE",
                f"Search completed with {len(campaign.candidates)} admitted direct-product candidate(s).",
                search_credit_count=len(campaign.actions),
                observation_count=len(campaign.observations),
                candidate_count=len(campaign.candidates),
            )

            emit(
                PipelineStage.ACQUIRE,
                "START",
                "Acquiring structured and visible page evidence from the bounded candidate set.",
                max_candidates=runtime.acquisition.max_candidates,
                max_per_domain=runtime.acquisition.max_per_domain,
                max_workers=runtime.acquisition.max_workers,
            )
            acquirer = self.acquirer or PageAcquirer(runtime.acquisition, runtime.request_timeout_seconds)

            def acquisition_progress(event_type: str, details: Mapping[str, Any]) -> None:
                if event_type == "ACQUISITION_PLAN":
                    message = f"Selected {details.get('selected_candidate_count')} URL(s) for bounded acquisition."
                else:
                    state = details.get("fetch_status")
                    message = f"Fetched {details.get('final_url') or details.get('requested_url')} with status {state}."
                emit(PipelineStage.ACQUIRE, event_type, message, **dict(details))

            pages = acquirer.acquire_many(campaign.candidates, progress=acquisition_progress)
            emit(
                PipelineStage.ACQUIRE,
                "COMPLETE",
                f"Acquisition completed for {len(pages)} candidate page(s).",
                fetched_count=len(pages),
                fetch_pass_count=sum(1 for item in pages.values() if item.fetch_status.value == "PASS"),
                fetch_fail_count=sum(1 for item in pages.values() if item.fetch_status.value == "FAIL"),
            )

            emit(
                PipelineStage.EVALUATE,
                "START",
                "Evaluating each candidate across identity, source, page, durability and coding gates.",
                candidate_count=len(campaign.candidates),
            )
            assessed = []
            for search_result in campaign.candidates:
                page = pages.get(search_result.url)
                if page is None:
                    emit(
                        PipelineStage.EVALUATE,
                        "CANDIDATE_SKIPPED",
                        "Candidate had no acquired page evidence and could not be assessed.",
                        url=search_result.url,
                    )
                    continue
                candidate = assess_candidate(product, interpretation, search_result, page, feature_set, runtime)
                assessed.append(candidate)
                judgment = candidate_judgment(candidate)
                emit(
                    PipelineStage.EVALUATE,
                    "CANDIDATE_ASSESSED",
                    f"Assessed {candidate.domain}: identity={candidate.identity_match.value}, direct_page={candidate.direct_product_page.value}.",
                    **judgment,
                )
            candidates = tuple(assessed)
            writer.write_intermediate(product.row_id, candidates=candidates)
            emit(
                PipelineStage.EVALUATE,
                "COMPLETE",
                f"Candidate evaluation completed for {len(candidates)} page(s).",
                exact_count=sum(1 for item in candidates if item.identity_match.value == "EXACT"),
                probable_count=sum(1 for item in candidates if item.identity_match.value == "PROBABLE"),
                mismatch_count=sum(1 for item in candidates if item.identity_match.value == "MISMATCH"),
                review_eligible_count=sum(1 for item in candidates if item.review_eligible),
            )

            emit(
                PipelineStage.BROWSER,
                "START",
                "Allocating rendered-browser checks by source authority and evidence diversity.",
                browser_enabled=runtime.browser.enabled,
                browser_required=runtime.browser.required,
                browser_candidate_limit=runtime.browser.max_candidates,
            )
            browser_client = self.browser_client or BrowserClient.from_env(runtime.browser)
            selected = select_browser_candidates(candidates, runtime.browser.max_candidates) if runtime.browser.enabled else ()
            emit(
                PipelineStage.BROWSER,
                "BROWSER_ALLOCATION",
                f"Allocated {len(selected)} candidate(s) for rendered-browser investigation.",
                candidates=[
                    {
                        "candidate_id": item.candidate_id,
                        "url": item.url,
                        "source_role": item.source_role.value,
                        "identity_match": item.identity_match.value,
                        "identity_confidence": item.identity_confidence,
                    }
                    for item in selected
                ],
            )
            by_id = {item.candidate_id: item for item in candidates}
            for item in selected:
                emit(
                    PipelineStage.BROWSER,
                    "BROWSER_STARTED",
                    f"Opening {item.domain} in the rendered browser.",
                    candidate_id=item.candidate_id,
                    url=item.url,
                )
                browser_evidence = browser_client.investigate(item.url, product.row_id, item.candidate_id)
                updated = apply_browser_evidence(item, browser_evidence)
                by_id[item.candidate_id] = updated
                emit(
                    PipelineStage.BROWSER,
                    "BROWSER_COMPLETED",
                    f"Browser investigation for {item.domain} finished with {browser_evidence.access.value}.",
                    candidate_id=item.candidate_id,
                    url=item.url,
                    access=browser_evidence.access.value,
                    final_url=browser_evidence.final_url,
                    title=browser_evidence.title,
                    product_controls=list(browser_evidence.product_controls),
                    screenshot_path=browser_evidence.screenshot_path,
                    error=browser_evidence.error,
                )
            candidates = tuple(by_id[item.candidate_id] for item in candidates)
            writer.write_intermediate(product.row_id, candidates=candidates)
            if runtime.browser.required and not selected:
                raise RuntimeError("browser investigation is required but no candidate was eligible")
            if runtime.browser.required and selected and not any(item.browser_access.value == "PASS" for item in candidates):
                raise RuntimeError("browser investigation is required but no candidate passed")
            emit(
                PipelineStage.BROWSER,
                "COMPLETE",
                f"Rendered-browser investigation assessed {len(selected)} candidate(s); unexecuted checks remain NOT_ASSESSED.",
                assessed_count=len(selected),
                browser_pass_count=sum(1 for item in candidates if item.browser_access.value == "PASS"),
                browser_fail_count=sum(1 for item in candidates if item.browser_access.value == "FAIL"),
                browser_not_assessed_count=sum(1 for item in candidates if item.browser_access.value == "NOT_ASSESSED"),
            )

            emit(
                PipelineStage.DELIVER,
                "START",
                "Applying the canonical mandatory URL-delivery policy.",
                candidate_count=len(candidates),
                review_eligible_count=sum(1 for item in candidates if item.review_eligible),
            )
            provisional = choose_delivery(candidates)
            ranking = candidate_ranking(candidates, provisional.selected_candidate_id)
            emit(
                PipelineStage.DELIVER,
                "CANDIDATE_RANKING",
                "Compared surviving candidates using independent identity, usability and source gates.",
                selected_candidate_id=provisional.selected_candidate_id,
                ranking=ranking,
            )
            decision = provisional
            emit(
                PipelineStage.DELIVER,
                "DECISION_COMPLETE",
                f"Delivery decision: {decision.status.value}.",
                status=decision.status.value,
                selected_url=decision.selected_url,
                selected_candidate_id=decision.selected_candidate_id,
                confidence=decision.confidence,
                coding_ready=decision.coding_ready,
                reasons=list(decision.reasons),
                warnings=list(decision.warnings),
            )
            emit(PipelineStage.DELIVER, "COMPLETE", "Canonical URL-delivery policy completed.")
            emit(PipelineStage.COMPLETE, "COMPLETE", "Product URL resolution completed.")
            result = ResolutionResult(
                runtime_contract=runtime.runtime_contract,
                product=product,
                interpretation=interpretation,
                search_observations=observations,
                candidates=candidates,
                decision=decision,
                events=tuple(events),
                artifact_dir=str(artifact_dir),
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            writer.finalize(result)
            return result
        except Exception as exc:
            emit(
                PipelineStage.FAILED,
                "TECHNICAL_FAILURE",
                f"{type(exc).__name__}: {exc}",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            decision = DeliveryDecision(
                DeliveryStatus.TECHNICAL_FAILURE,
                None,
                None,
                0.0,
                False,
                ("A technical or configuration defect prevented a valid delivery decision.",),
                (f"{type(exc).__name__}: {exc}",),
            )
            artifact_dir = writer.prepare(product.row_id)
            result = ResolutionResult(
                runtime_contract=runtime.runtime_contract,
                product=product,
                interpretation=interpretation,
                search_observations=observations,
                candidates=candidates,
                decision=decision,
                events=tuple(events),
                artifact_dir=str(artifact_dir),
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                technical_error=f"{type(exc).__name__}: {exc}",
            )
            writer.finalize(result)
            return result
