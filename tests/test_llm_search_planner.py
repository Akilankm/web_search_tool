from __future__ import annotations

from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.config import HarnessConfig
from product_evidence_harness.contracts import ProductQuery, ProductSearchState
from product_evidence_harness.country_profiles import CountryProfileRegistry
from product_evidence_harness.llm.search_planner import LLMSearchPlanner
from product_evidence_harness.llm.service import LLMResponse
from product_evidence_harness.query_builder import QueryBuilder


class FakePlanningLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def predict(self, text, *, system_prompt=None, response_format=None, purpose="", **kwargs):
        self.calls.append({"text": text, "purpose": purpose})
        return LLMResponse(content=self.content, usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})


def test_llm_search_plan_sanitizes_invented_gtin():
    content = '''{
      "expanded_main_text":"1001 Karten A5 flieder",
      "critical_terms":["1001","Karten","A5","flieder"],
      "variant_terms_to_preserve":["A5","flieder"],
      "negative_terms":[],
      "search_queries":[
        {"query":"7612450206555 1001 Karten A5 flieder", "scope":"country", "reason":"uses input ean", "priority":1, "must_include_ean":true},
        {"query":"0196214141070 wrong invented gtin", "scope":"country", "reason":"bad", "priority":2}
      ],
      "reasoning":"expand compact input"
    }'''
    registry = CountryProfileRegistry.load()
    qb = QueryBuilder(country_profiles=registry)
    planner = LLMSearchPlanner(config=HarnessConfig(enable_llm_search_planning=True), query_builder=qb, country_profiles=registry, service=FakePlanningLLM(content))
    state = ProductSearchState(task=ProductQuery(main_text="1001KARTENA5FLIEDER", country_code="CH", ean="7612450206555"), budget=BudgetTracker())
    plan, record = planner.plan_initial(state)
    assert record.success is True
    assert len(plan.queries) == 1
    assert "7612450206555" in plan.queries[0].query
    assert all("0196214141070" not in q.query for q in plan.queries)
