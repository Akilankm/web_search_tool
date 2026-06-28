from __future__ import annotations

from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.config import HarnessConfig
from product_evidence_harness.contracts import (
    ActionType,
    LLMJudgement,
    LLMSearchPlan,
    LLMSearchQuery,
    ProductQuery,
    ProductSearchState,
    ScrapeResult,
    URLCandidate,
)
from product_evidence_harness.country_profiles import CountryProfileRegistry
from product_evidence_harness.planner import HarnessPlanner
from product_evidence_harness.query_builder import QueryBuilder


def _planner(config: HarnessConfig | None = None) -> HarnessPlanner:
    registry = CountryProfileRegistry.load()
    return HarnessPlanner(config=config or HarnessConfig(), query_builder=QueryBuilder(country_profiles=registry), country_profiles=registry)


def test_loop_scrapes_after_first_search_before_draining_queries():
    config = HarnessConfig(enable_llm_search_planning=True, enable_llm_adjudication=True)
    state = ProductSearchState(task=ProductQuery(main_text="LEGO 41731", country_code="CH"), budget=BudgetTracker(max_organic=5, max_ai_mode=0, max_scrapes=5))
    state.llm_search_plans.append(LLMSearchPlan(row_id="demo-001", call_index=1, stage="initial_search_plan"))
    state.llm_call_records.append(_fake_call_record())
    state.planned_search_queries.extend([
        LLMSearchQuery(query='"LEGO 41731" Switzerland', scope="country", priority=1),
        LLMSearchQuery(query='"LEGO 41731" shop', scope="country", priority=2),
    ])
    state.queries.append('"LEGO 41731" Switzerland')
    state.candidates.append(URLCandidate(url="https://shop.ch/p/lego-41731", domain="shop.ch", title="LEGO 41731"))

    action = _planner(config).next_action(state)

    assert action.action_type == ActionType.SCRAPE_URL
    assert action.url == "https://shop.ch/p/lego-41731"


def test_rejected_llm_judgement_triggers_feedback_before_more_initial_searches():
    config = HarnessConfig(enable_llm_search_planning=True, enable_llm_search_feedback=True, enable_llm_adjudication=True, llm_max_calls_per_product=4)
    state = ProductSearchState(task=ProductQuery(main_text="LEGO 41731", country_code="CH"), budget=BudgetTracker(max_organic=5, max_ai_mode=0, max_scrapes=5))
    state.llm_search_plans.append(LLMSearchPlan(row_id="demo-001", call_index=1, stage="initial_search_plan"))
    state.llm_call_records.append(_fake_call_record(call_index=1, decision="SEARCH_PLAN"))
    state.llm_call_records.append(_fake_call_record(call_index=2, decision="WRONG_PRODUCT"))
    state.planned_search_queries.append(LLMSearchQuery(query='"LEGO 41731" shop', scope="country", priority=2))
    url = "https://shop.ch/p/lego-41730"
    state.candidates.append(URLCandidate(url=url, domain="shop.ch", title="LEGO 41730"))
    state.scrapes[url] = ScrapeResult(url=url, scraped=True, success=True, reachable=True, is_scrapable=True, status_code=200, final_url=url, title="LEGO 41730", looks_like_product_page=True, richness_score=0.7)
    state.llm_judgements[url] = LLMJudgement(url=url, decision="WRONG_PRODUCT", exact_product_match=False)

    action = _planner(config).next_action(state)

    assert action.action_type == ActionType.LLM_SEARCH_FEEDBACK


def _fake_call_record(call_index: int = 1, decision: str = "SEARCH_PLAN"):
    from product_evidence_harness.contracts import LLMCallRecord
    return LLMCallRecord(row_id="demo-001", url="", call_index=call_index, payload_level="test", image_used=False, image_url=None, success=True, decision=decision)
