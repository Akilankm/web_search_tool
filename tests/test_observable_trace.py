from pathlib import Path

from product_url_v2.acquisition import PageAcquirer
from product_url_v2.api import Job, JobStore
from product_url_v2.artifacts import ArtifactWriter
from product_url_v2.config import AcquisitionConfig, RuntimeConfig
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import (
    CandidateAssessment,
    GateStatus,
    IdentityMatch,
    PageEvidence,
    PipelineStage,
    ProductInput,
    RunEvent,
    SearchObservation,
    SearchResult,
    SourceRole,
)
from product_url_v2.search import InformationGainSearchPlanner
from product_url_v2.trace import TRACE_CONTRACT, TRACE_NOTICE, candidate_judgment
from product_url_v2.ui_presenter import merge_events, stage_rows


def _candidate(**changes):
    values = {
        "candidate_id": "C-1",
        "url": "https://shop.example.com/product/me04",
        "domain": "shop.example.com",
        "search_rank": 1,
        "search_support": 1.0,
        "source_role": SourceRole.COUNTRY_RETAILER,
        "identity_match": IdentityMatch.PROBABLE,
        "identity_confidence": 0.75,
        "direct_product_page": GateStatus.PASS,
        "direct_page_score": 0.8,
        "durable_url": GateStatus.PASS,
        "country_match": GateStatus.PASS,
        "retailer_match": GateStatus.NOT_ASSESSED,
        "browser_access": GateStatus.NOT_ASSESSED,
        "text_extractable": GateStatus.PASS,
        "coding_evidence_complete": GateStatus.FAIL,
        "source_authority": 75,
        "evidence": {"matched_signals": ["model=ME04"]},
        "conflicts": (),
        "warnings": ("The selected page may not contain every requested coding field.",),
    }
    values.update(changes)
    return CandidateAssessment(**values)


def test_candidate_judgment_separates_strengths_risks_and_blockers() -> None:
    judgment = candidate_judgment(_candidate())
    assert judgment["review_eligible"] is True
    assert any("Direct product-page" in item for item in judgment["strengths"])
    assert any("Rendered browser usability was not assessed" in item for item in judgment["risks"])
    assert not judgment["blockers"]


def test_identity_mismatch_is_an_explicit_blocker() -> None:
    judgment = candidate_judgment(
        _candidate(identity_match=IdentityMatch.MISMATCH, identity_confidence=0.1)
    )
    assert judgment["review_eligible"] is False
    assert any("different product" in item for item in judgment["blockers"])


def test_trace_contract_excludes_hidden_chain_of_thought() -> None:
    assert TRACE_CONTRACT == "observable-decision-trace-v1"
    assert "hidden chain-of-thought" in TRACE_NOTICE


def test_merge_events_is_incremental_and_sequence_stable() -> None:
    existing = [{"sequence": 1, "stage": "INTERPRET", "event_type": "START"}]
    incoming = [
        {"sequence": 2, "stage": "INTERPRET", "event_type": "COMPLETE"},
        {"sequence": 1, "stage": "INTERPRET", "event_type": "START", "message": "updated"},
    ]
    merged = merge_events(existing, incoming)
    assert [item["sequence"] for item in merged] == [1, 2]
    assert merged[0]["message"] == "updated"


def test_stage_rows_show_current_and_completed_work() -> None:
    events = [
        {"sequence": 1, "stage": "INTERPRET", "event_type": "COMPLETE"},
        {"sequence": 2, "stage": "SEARCH", "event_type": "SEARCH_ACTION"},
    ]
    rows = {item["stage"]: item["state"] for item in stage_rows(events, "SEARCH", "RUNNING")}
    assert rows["INTERPRET"] == "COMPLETE"
    assert rows["SEARCH"] == "ACTIVE"
    assert rows["BROWSER"] == "PENDING"


def test_technical_failure_does_not_show_pipeline_complete() -> None:
    rows = {item["stage"]: item["state"] for item in stage_rows([], "FAILED", "TECHNICAL_FAILURE")}
    assert rows["COMPLETE"] == "PENDING"


def test_job_store_returns_incremental_structured_trace() -> None:
    product = ProductInput("ROW-1", "PKM ME04 BOOSTER", "CH")
    store = JobStore()
    store.put(Job("JOB-1", "QUEUED", product, "created", "created"))
    store.mark_running("JOB-1")
    store.record_event(
        "JOB-1",
        RunEvent(1, PipelineStage.INTERPRET, "START", "Interpretation started", {"reasoning_enabled": True}),
    )
    store.record_event(
        "JOB-1",
        RunEvent(2, PipelineStage.SEARCH, "SEARCH_ACTION", "Search credit 1", {"credit_number": 1}),
    )

    view = store.view("JOB-1")
    assert view["event_count"] == 2
    assert view["last_event_sequence"] == 2
    assert view["trace_contract"] == "observable-decision-trace-v1"

    incremental = store.trace("JOB-1", after_sequence=1)
    assert [item["sequence"] for item in incremental["events"]] == [2]
    assert incremental["events"][0]["details"]["credit_number"] == 1


def test_artifact_run_directory_is_shared_group_writable(tmp_path: Path) -> None:
    path = ArtifactWriter(tmp_path).prepare("ROW-1")
    mode = path.stat().st_mode
    assert mode & 0o2000
    assert mode & 0o020


class FakeSearchClient:
    def execute(self, action, product):
        result = SearchResult(
            url=f"https://shop.example.com/product/item-{action.credit_number}",
            title="Product",
            snippet="Exact product",
            source_section="fixture",
            engine=action.engine,
            query=action.query or action.purpose,
            position=action.credit_number,
            product_like=True,
        )
        return SearchObservation(action, "SUCCESS", (result,))


class FakeAcquirer(PageAcquirer):
    def acquire(self, url: str) -> PageEvidence:
        return PageEvidence(
            requested_url=url,
            final_url=url,
            status_code=200,
            content_type="text/html",
            title="Product",
            description="",
            visible_text="Product price in stock",
            jsonld_products=(),
            metadata={},
            links=(),
            images=(),
            fetch_status=GateStatus.PASS,
            elapsed_ms=5,
        )


def test_search_progress_emits_each_paid_action_and_observation() -> None:
    product = ProductInput("ROW-1", "PKM ME04 BOOSTER", "CH")
    interpretation = DeterministicProductInterpreter().interpret(product)
    observed = []
    campaign = InformationGainSearchPlanner(RuntimeConfig()).run(
        product,
        interpretation,
        FakeSearchClient(),
        progress=lambda event_type, details: observed.append((event_type, details)),
    )
    assert len(campaign.actions) == 3
    assert [name for name, _ in observed].count("SEARCH_ACTION") == 3
    assert [name for name, _ in observed].count("SEARCH_OBSERVATION") == 3
    assert observed[-1][0] == "SEARCH_CANDIDATES"


def test_acquisition_progress_reports_plan_and_each_page() -> None:
    candidates = (
        SearchResult("https://shop.example.com/product/1", "One", "", "fixture", "google", "q", 1, True),
        SearchResult("https://other.example.com/product/2", "Two", "", "fixture", "google", "q", 2, True),
    )
    observed = []
    acquirer = FakeAcquirer(AcquisitionConfig(max_workers=1))
    pages = acquirer.acquire_many(candidates, progress=lambda event_type, details: observed.append((event_type, details)))
    assert len(pages) == 2
    assert observed[0][0] == "ACQUISITION_PLAN"
    assert [name for name, _ in observed].count("PAGE_FETCHED") == 2
