from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from product_url_v2.contracts import (
    BudgetUsage,
    CandidateAssessment,
    DeliveryStatus,
    IdentityResolution,
    PipelineStage,
    ProductHypothesis,
    ProductInput,
    ProductRun,
    RunEvent,
)
from product_url_v2.policy import MandatoryURLDeliveryPolicy


_ALLOWED_TRANSITIONS: dict[PipelineStage, set[PipelineStage]] = {
    PipelineStage.INTERPRET_INPUT: {
        PipelineStage.BUILD_HYPOTHESES,
        PipelineStage.FAILED,
    },
    PipelineStage.BUILD_HYPOTHESES: {
        PipelineStage.SEARCH,
        PipelineStage.FAILED,
    },
    PipelineStage.SEARCH: {
        PipelineStage.ADMIT_CANDIDATES,
        PipelineStage.SEARCH,
        PipelineStage.FAILED,
    },
    PipelineStage.ADMIT_CANDIDATES: {
        PipelineStage.SCRAPE,
        PipelineStage.SEARCH,
        PipelineStage.FAILED,
    },
    PipelineStage.SCRAPE: {
        PipelineStage.BROWSER_INVESTIGATION,
        PipelineStage.SEARCH,
        PipelineStage.EVALUATE,
        PipelineStage.FAILED,
    },
    PipelineStage.BROWSER_INVESTIGATION: {
        PipelineStage.BROWSER_INVESTIGATION,
        PipelineStage.SEARCH,
        PipelineStage.EVALUATE,
        PipelineStage.FAILED,
    },
    PipelineStage.EVALUATE: {
        PipelineStage.SEARCH,
        PipelineStage.DELIVER,
        PipelineStage.FAILED,
    },
    PipelineStage.DELIVER: {
        PipelineStage.COMPLETE,
        PipelineStage.FAILED,
    },
    PipelineStage.COMPLETE: set(),
    PipelineStage.FAILED: set(),
}


class ProductRunStateMachine:
    """Pure, auditable state transitions for the v2 pipeline.

    This class contains no network calls, framework hooks, import-time patches,
    or hidden mutation. Every business transition returns a new ProductRun.
    """

    def __init__(self, delivery_policy: MandatoryURLDeliveryPolicy | None = None) -> None:
        self.delivery_policy = delivery_policy or MandatoryURLDeliveryPolicy()

    @staticmethod
    def start(product: ProductInput) -> ProductRun:
        run = ProductRun(product=product)
        return replace(
            run,
            events=(
                RunEvent(
                    sequence=1,
                    stage=PipelineStage.INTERPRET_INPUT,
                    event_type="RUN_STARTED",
                    message="Product URL v2 run initialized.",
                ),
            ),
        )

    def transition(
        self,
        run: ProductRun,
        stage: PipelineStage,
        *,
        event_type: str,
        message: str,
        candidate_id: str | None = None,
        evidence_ids: tuple[str, ...] = (),
    ) -> ProductRun:
        if stage not in _ALLOWED_TRANSITIONS[run.stage]:
            raise ValueError(f"invalid pipeline transition: {run.stage.value} -> {stage.value}")
        event = RunEvent(
            sequence=len(run.events) + 1,
            stage=stage,
            event_type=event_type,
            message=message,
            candidate_id=candidate_id,
            evidence_ids=evidence_ids,
        )
        return replace(run, stage=stage, events=(*run.events, event))

    def set_hypotheses(
        self,
        run: ProductRun,
        hypotheses: Iterable[ProductHypothesis],
        *,
        resolution: IdentityResolution,
    ) -> ProductRun:
        values = tuple(hypotheses)
        ids = [item.hypothesis_id for item in values]
        if len(ids) != len(set(ids)):
            raise ValueError("hypothesis_id values must be unique")
        return replace(run, hypotheses=values, identity_resolution=resolution)

    def add_or_replace_candidate(
        self,
        run: ProductRun,
        candidate: CandidateAssessment,
        *,
        event_type: str,
        message: str,
    ) -> ProductRun:
        candidates = list(run.candidates)
        for index, current in enumerate(candidates):
            if current.candidate_id == candidate.candidate_id:
                candidates[index] = candidate
                break
        else:
            candidates.append(candidate)
        event = RunEvent(
            sequence=len(run.events) + 1,
            stage=run.stage,
            event_type=event_type,
            message=message,
            candidate_id=candidate.candidate_id,
            evidence_ids=candidate.evidence_ids,
        )
        return replace(run, candidates=tuple(candidates), events=(*run.events, event))

    def consume_search_action(self, run: ProductRun, message: str) -> ProductRun:
        usage = replace(run.budget_usage, search_actions=run.budget_usage.search_actions + 1)
        return self._with_budget_event(run, usage, "SEARCH_BUDGET_CONSUMED", message)

    def consume_full_scrape(
        self,
        run: ProductRun,
        message: str,
        *,
        candidate_id: str,
    ) -> ProductRun:
        usage = replace(run.budget_usage, full_scrapes=run.budget_usage.full_scrapes + 1)
        return self._with_budget_event(
            run,
            usage,
            "SCRAPE_BUDGET_CONSUMED",
            message,
            candidate_id=candidate_id,
        )

    def consume_browser_investigation(
        self,
        run: ProductRun,
        message: str,
        *,
        candidate_id: str,
    ) -> ProductRun:
        usage = replace(
            run.budget_usage,
            browser_investigations=run.budget_usage.browser_investigations + 1,
        )
        return self._with_budget_event(
            run,
            usage,
            "BROWSER_BUDGET_CONSUMED",
            message,
            candidate_id=candidate_id,
        )

    def finalize(self, run: ProductRun) -> ProductRun:
        if run.stage not in {PipelineStage.EVALUATE, PipelineStage.DELIVER}:
            raise ValueError("run must be in EVALUATE or DELIVER before finalization")

        working = run
        if working.stage is PipelineStage.EVALUATE:
            working = self.transition(
                working,
                PipelineStage.DELIVER,
                event_type="DELIVERY_SELECTION_STARTED",
                message="Selecting the strongest mandatory product URL.",
            )

        decision = self.delivery_policy.select(working.candidates)
        terminal_stage = (
            PipelineStage.FAILED
            if decision.status is DeliveryStatus.FAILED
            else PipelineStage.COMPLETE
        )
        event = RunEvent(
            sequence=len(working.events) + 1,
            stage=terminal_stage,
            event_type=(
                "MANDATORY_URL_DELIVERY_FAILED"
                if decision.status is DeliveryStatus.FAILED
                else "MANDATORY_URL_DELIVERED"
            ),
            message=" ".join(decision.reasons),
            candidate_id=decision.selected_candidate_id,
        )
        return replace(
            working,
            stage=terminal_stage,
            decision=decision,
            events=(*working.events, event),
        )

    @staticmethod
    def _with_budget_event(
        run: ProductRun,
        usage: BudgetUsage,
        event_type: str,
        message: str,
        *,
        candidate_id: str | None = None,
    ) -> ProductRun:
        usage.validate_against(run.budget_policy)
        event = RunEvent(
            sequence=len(run.events) + 1,
            stage=run.stage,
            event_type=event_type,
            message=message,
            candidate_id=candidate_id,
        )
        return replace(run, budget_usage=usage, events=(*run.events, event))
