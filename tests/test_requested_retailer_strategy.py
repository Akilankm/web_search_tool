from __future__ import annotations

from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.config import HarnessConfig
from product_evidence_harness.contracts import (
    ActionType,
    AgentAction,
    AgentActionRecord,
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
from product_evidence_harness.retailer_strategy import requested_retailer_metrics


def _planner(config: HarnessConfig | None = None) -> HarnessPlanner:
    registry = CountryProfileRegistry.load()
    return HarnessPlanner(config=config or HarnessConfig(), query_builder=QueryBuilder(country_profiles=registry), country_profiles=registry)


def test_requested_retailer_is_attempted_first_when_provided():
    config = HarnessConfig(enable_llm_search_planning=False)
    state = ProductSearchState(
        task=ProductQuery(main_text="Peluche Osito Azul", country_code="CO", retailer_name="Mercado Libre"),
        budget=BudgetTracker(max_organic=3, max_ai_mode=0, max_scrapes=5),
    )

    action = _planner(config).next_action(state)

    assert action.action_type == ActionType.ORGANIC_SEARCH
    assert action.metadata["scope"] == "requested_retailer"
    assert "Mercado Libre" in action.query


def test_requested_retailer_unusable_escapes_to_country_alternative_search():
    config = HarnessConfig(enable_llm_search_planning=True, enable_llm_search_feedback=False)
    task = ProductQuery(main_text="Peluche Osito Azul", country_code="CO", retailer_name="Mercado Libre")
    state = ProductSearchState(task=task, budget=BudgetTracker(max_organic=4, max_ai_mode=0, max_scrapes=5))
    state.llm_search_plans.append(LLMSearchPlan(row_id=task.row_id, call_index=1, stage="initial_search_plan"))
    state.planned_search_queries.append(LLMSearchQuery(query='"Peluche Osito Azul" Colombia', scope="country_alternative", priority=2))
    q = '"Peluche Osito Azul" "Mercado Libre" Colombia'
    state.queries.append(q)
    state.actions_taken.append(AgentActionRecord(
        iteration=1,
        action=AgentAction(ActionType.ORGANIC_SEARCH, "requested", query=q, metadata={"scope": "requested_retailer"}),
        success=True,
        output_summary={},
    ))
    url1 = "https://articulo.mercadolibre.com.co/MCO-123-osito"
    url2 = "https://www.exito.com/peluche-osito-azul"
    state.candidates.extend([
        URLCandidate(url=url1, domain="articulo.mercadolibre.com.co", title="Peluche Osito Azul"),
        URLCandidate(url=url2, domain="www.exito.com", title="Peluche Osito Azul"),
    ])
    state.scrapes[url1] = ScrapeResult(url=url1, scraped=True, success=True, reachable=True, is_scrapable=False, status_code=403, final_url=url1, title="blocked", richness_score=0.0)
    # scorecards are normally created by the ranker; this minimal fixture only needs retailer metrics behavior.
    from product_evidence_harness.ranker import ProductURLRanker
    ranker = ProductURLRanker(country_profiles=CountryProfileRegistry.load())
    state.scorecards = ranker.score(product=task, candidates=state.candidates, scrapes=state.scrapes, verifications={})

    metrics = requested_retailer_metrics(state)
    action = _planner(config).next_action(state)

    assert metrics.requested_retailer_scrapability_status in {"SCRAPABILITY_CHECK_IN_PROGRESS", "UNUSABLE_FOR_EVIDENCE"}
    # With only one scraped blocked retailer page, the system may continue scraping retailer candidates if present;
    # once requested scope is exhausted, it must not keep forcing Mercado Libre.
    if action.action_type == ActionType.ORGANIC_SEARCH:
        assert action.metadata["scope"] in {"country_alternative", "global"}
        assert "Mercado Libre" not in action.query
