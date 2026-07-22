from __future__ import annotations

import pytest

from product_url_v2 import (
    CandidateAssessment,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    PipelineStage,
    ProductInput,
    ProductRunStateMachine,
    SourceRole,
)


def _review_candidate() -> CandidateAssessment:
    return CandidateAssessment(
        candidate_id="C1",
        url="https://retailer.example/product/exact-item",
        domain="retailer.example",
        source_role=SourceRole.COUNTRY_RETAILER,
        search_rank=1,
        search_support=0.9,
        identity_match=IdentityMatch.EXACT,
        identity_confidence=0.94,
        browser_access=GateStatus.PASS,
        text_extractable=GateStatus.PASS,
        direct_product_page=GateStatus.PASS,
        durable_url=GateStatus.PASS,
        coding_evidence_complete=GateStatus.FAIL,
        source_authority=75,
    )


def _advance_to_evaluate(machine: ProductRunStateMachine):
    run = machine.start(
        ProductInput(
            row_id="ROW-1",
            main_text="Exact product",
            country_code="DE",
        )
    )
    run = machine.transition(
        run,
        PipelineStage.BUILD_HYPOTHESES,
        event_type="INPUT_INTERPRETED",
        message="Input interpretation complete.",
    )
    run = machine.transition(
        run,
        PipelineStage.SEARCH,
        event_type="SEARCH_STARTED",
        message="Search started.",
    )
    run = machine.consume_search_action(run, "Search credit 1 consumed.")
    run = machine.transition(
        run,
        PipelineStage.ADMIT_CANDIDATES,
        event_type="CANDIDATES_DISCOVERED",
        message="Candidate admission started.",
    )
    run = machine.transition(
        run,
        PipelineStage.SCRAPE,
        event_type="SCRAPE_STARTED",
        message="Scraping started.",
    )
    candidate = _review_candidate()
    run = machine.consume_full_scrape(
        run,
        "Candidate scraped.",
        candidate_id=candidate.candidate_id,
    )
    run = machine.add_or_replace_candidate(
        run,
        candidate,
        event_type="CANDIDATE_EVALUATED",
        message="Candidate evidence recorded.",
    )
    run = machine.transition(
        run,
        PipelineStage.BROWSER_INVESTIGATION,
        event_type="BROWSER_STARTED",
        message="Browser investigation started.",
    )
    run = machine.consume_browser_investigation(
        run,
        "Candidate investigated.",
        candidate_id=candidate.candidate_id,
    )
    return machine.transition(
        run,
        PipelineStage.EVALUATE,
        event_type="EVALUATION_STARTED",
        message="Final evaluation started.",
    )


def test_review_required_terminal_result_always_contains_url() -> None:
    machine = ProductRunStateMachine()
    run = machine.finalize(_advance_to_evaluate(machine))

    assert run.stage is PipelineStage.COMPLETE
    assert run.decision is not None
    assert run.decision.status is DeliveryStatus.REVIEW_REQUIRED
    assert run.decision.selected_url == "https://retailer.example/product/exact-item"
    assert run.decision.coding_ready is False
    assert run.events[-1].event_type == "MANDATORY_URL_DELIVERED"


def test_invalid_transition_is_rejected() -> None:
    machine = ProductRunStateMachine()
    run = machine.start(
        ProductInput(row_id="ROW-2", main_text="Product", country_code="GB")
    )

    with pytest.raises(ValueError, match="invalid pipeline transition"):
        machine.transition(
            run,
            PipelineStage.COMPLETE,
            event_type="INVALID",
            message="Cannot skip the pipeline.",
        )


def test_budget_overrun_is_rejected_at_transition_boundary() -> None:
    machine = ProductRunStateMachine()
    run = machine.start(
        ProductInput(row_id="ROW-3", main_text="Product", country_code="GB")
    )
    run = machine.transition(
        run,
        PipelineStage.BUILD_HYPOTHESES,
        event_type="INPUT_INTERPRETED",
        message="Input interpreted.",
    )
    run = machine.transition(
        run,
        PipelineStage.SEARCH,
        event_type="SEARCH_STARTED",
        message="Search started.",
    )
    run = machine.consume_search_action(run, "Credit 1")
    run = machine.consume_search_action(run, "Credit 2")
    run = machine.consume_search_action(run, "Credit 3")

    with pytest.raises(ValueError, match="search action budget exceeded"):
        machine.consume_search_action(run, "Credit 4")
