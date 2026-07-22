from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

from product_url_v2.acquisition import PageAcquirer
from product_url_v2.artifacts import ArtifactWriter
from product_url_v2.browser import BrowserClient, select_browser_candidates
from product_url_v2.config import RuntimeConfig, load_feature_set
from product_url_v2.evaluation import apply_browser_evidence, assess_candidate, choose_delivery
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.reasoning import ReasoningPort, ReasoningSettings, StructuredIdentityReasoner
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
from product_url_v2.search import InformationGainSearchPlanner, SearchClient, SerpAPIClient

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

        def emit(stage: PipelineStage, event_type: str, message: str, **details) -> None:
            event = RunEvent(len(events) + 1, stage, event_type, message, details)
            events.append(event)
            if progress:
                progress(event)

        try:
            emit(PipelineStage.INTERPRET, "START", "Interpreting product identity and commercial-form uncertainty.")
            interpretation = DeterministicProductInterpreter().interpret(product)
            reasoner = self.reasoner or StructuredIdentityReasoner(
                ReasoningSettings(
                    enabled=runtime.reasoning.enabled,
                    required=runtime.reasoning.required,
                    model=runtime.reasoning.model,
                    base_url=runtime.reasoning.base_url,
                    api_key=str(os.getenv("LLM_API_KEY") or ""),
                    timeout_seconds=runtime.reasoning.timeout_seconds,
                    temperature=runtime.reasoning.temperature,
                    max_hypotheses=runtime.reasoning.max_hypotheses,
                )
            )
            interpretation = reasoner.refine(product, interpretation)
            feature_set = load_feature_set(runtime.feature_set_root, product.feature_set)
            artifact_dir = writer.write_intermediate(product.row_id, input_payload=to_jsonable(product), interpretation=interpretation)
            emit(PipelineStage.INTERPRET, "COMPLETE", f"Built {len(interpretation.hypotheses)} product hypothesis/hypotheses.", unresolved=list(interpretation.unresolved_discriminators))

            emit(PipelineStage.SEARCH, "START", "Running bounded hypothesis-driven search campaign.")
            client = self.search_client or SerpAPIClient.from_env(runtime)
            campaign = InformationGainSearchPlanner(runtime).run(product, interpretation, client)
            observations = campaign.observations
            writer.write_intermediate(product.row_id, search=campaign)
            emit(PipelineStage.SEARCH, "COMPLETE", f"Collected {len(campaign.candidates)} structurally product-like URL candidates using {len(campaign.actions)} search credits.")

            emit(PipelineStage.ACQUIRE, "START", "Acquiring structured and visible evidence from bounded candidates.")
            acquirer = self.acquirer or PageAcquirer(runtime.acquisition, runtime.request_timeout_seconds)
            pages = acquirer.acquire_many(campaign.candidates)
            assessed = []
            for search_result in campaign.candidates:
                page = pages.get(search_result.url)
                if page is None:
                    continue
                assessed.append(assess_candidate(product, interpretation, search_result, page, feature_set, runtime))
            candidates = tuple(assessed)
            writer.write_intermediate(product.row_id, candidates=candidates)
            emit(PipelineStage.ACQUIRE, "COMPLETE", f"Evaluated {len(candidates)} acquired product-page candidates.")

            emit(PipelineStage.BROWSER, "START", "Allocating rendered-browser checks by source and evidence diversity.")
            browser_client = self.browser_client or BrowserClient.from_env(runtime.browser)
            selected = select_browser_candidates(candidates, runtime.browser.max_candidates) if runtime.browser.enabled else ()
            by_id = {item.candidate_id: item for item in candidates}
            for item in selected:
                browser_evidence = browser_client.investigate(item.url, product.row_id, item.candidate_id)
                by_id[item.candidate_id] = apply_browser_evidence(item, browser_evidence)
            candidates = tuple(by_id[item.candidate_id] for item in candidates)
            writer.write_intermediate(product.row_id, candidates=candidates)
            if runtime.browser.required and not selected:
                raise RuntimeError("browser investigation is required but no candidate was eligible")
            if runtime.browser.required and selected and not any(item.browser_access.value == "PASS" for item in candidates):
                raise RuntimeError("browser investigation is required but no candidate passed")
            emit(PipelineStage.BROWSER, "COMPLETE", f"Rendered-browser investigation assessed {len(selected)} candidate(s); unexecuted checks remain NOT_ASSESSED.")

            emit(PipelineStage.DELIVER, "START", "Applying canonical mandatory URL-delivery policy.")
            decision = choose_delivery(candidates)
            emit(PipelineStage.DELIVER, "COMPLETE", f"Delivery decision: {decision.status.value}.", selected_url=decision.selected_url)
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
            emit(PipelineStage.FAILED, "TECHNICAL_FAILURE", f"{type(exc).__name__}: {exc}")
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
