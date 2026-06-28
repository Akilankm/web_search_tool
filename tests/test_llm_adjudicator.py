from __future__ import annotations

from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.config import HarnessConfig
from product_evidence_harness.contracts import (
    CandidateScorecard,
    MatchVerification,
    ProductQuery,
    ProductSearchState,
    ScrapeResult,
    URLCandidate,
)
from product_evidence_harness.llm.adjudicator import ExactProductLLMAdjudicator
from product_evidence_harness.llm.service import LLMResponse
from product_evidence_harness.selector import FinalSelector


class FakeLLM:
    def __init__(self, fail_first: bool = False):
        self.calls = []
        self.fail_first = fail_first

    def predict(self, text, *, system_prompt=None, image=None, image_detail="auto", response_format=None, purpose="", **kwargs):
        self.calls.append({"image": image, "purpose": purpose, "text": text})
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("gateway payload rejected")
        return LLMResponse(
            content='{"exact_product_match": true, "decision": "EXACT_MATCH", "confidence": 0.93, "primary_identity_driver": "MAIN_TEXT", "main_text_assessment": {"status":"MATCHED", "reason":"same"}, "ean_assessment": {"status":"MATCHED", "reason":"same"}, "variant_assessment": {"status":"MATCHED", "conflict_terms": [], "reason":"same"}, "scrape_assessment": {"is_product_page": true, "is_scrapable": true, "usable_for_final": true}, "image_assessment": {"used": true, "status":"SUPPORTS_MATCH", "reason":"image supports"}, "reject_reason": null, "final_explanation": "Exact product."}',
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )


def _card(url="https://shop.ch/p/abc"):
    candidate = URLCandidate(url=url, domain="shop.ch", title="ABC Toy", source_types=("organic",))
    scrape = ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        title="ABC Toy",
        h1="ABC Toy",
        page_product_name="ABC Toy",
        structured_eans=("7612450206555",),
        image_urls=("https://shop.ch/images/abc-toy.jpg", "https://shop.ch/logo.png"),
        looks_like_product_page=True,
        word_count=120,
        markdown_chars=800,
    )
    verification = MatchVerification(
        url=url,
        identity_status="VERIFIED",
        ean_check="MATCHED",
        title_check="STRONG",
        quantity_check="NOT_APPLICABLE",
        brand_check="MATCHED",
        page_type_check="PRODUCT_DETAIL",
        title_match_score=1.0,
        exact_product_check="EXACT_MATCH",
        variant_check="MATCHED",
    )
    return CandidateScorecard(
        candidate=candidate,
        organic_score=1,
        ai_score=0,
        retailer_score=0.5,
        country_score=1,
        ean_score=1,
        title_score=1,
        product_page_score=1,
        scrape_score=1,
        identity_score=1,
        richness_score=0.8,
        weighted_confidence=0.9,
        confidence_cap=1,
        final_confidence=0.9,
        validation_status="VERIFIED",
        scrape=scrape,
        verification=verification,
        country_check="MATCHED",
    )


def test_llm_adjudicator_one_image_and_payload_reduction():
    config = HarnessConfig(enable_llm_adjudication=True, llm_max_calls_per_product=4, llm_adjudicate_top_k=1, llm_use_images=True)
    fake = FakeLLM(fail_first=True)
    adjudicator = ExactProductLLMAdjudicator(config=config, service=fake)
    state = ProductSearchState(
        task=ProductQuery(main_text="ABC Toy", country_code="CH", ean="7612450206555"),
        budget=BudgetTracker(max_organic=1, max_ai_mode=0, max_scrapes=1),
        scorecards=[_card()],
    )
    adjudicator.adjudicate_state(state)
    assert len(fake.calls) == 2
    assert fake.calls[0]["image"] == "https://shop.ch/images/abc-toy.jpg"
    assert fake.calls[1]["image"] == "https://shop.ch/images/abc-toy.jpg"
    assert len(state.llm_call_records) == 2
    assert state.scorecards[0].llm_decision == "EXACT_MATCH"
    assert state.scorecards[0].llm_exact_product_match is True


def test_selector_can_require_llm_exact_match():
    card = _card()
    selector = FinalSelector(policy=__import__("product_evidence_harness").HarnessPolicy(require_llm_exact_match_for_final=True))
    task = ProductQuery(main_text="ABC Toy", country_code="CH", ean="7612450206555")
    budget = BudgetTracker(max_organic=1, max_ai_mode=0, max_scrapes=1).snapshot()
    unresolved = selector.select(task=task, scorecards=[card], termination_reason=None, budget_snapshot=budget)
    assert unresolved.product_url == card.candidate.url
    assert unresolved.verified_exact_url is None
    assert unresolved.needs_review is True

    state = ProductSearchState(task=task, budget=BudgetTracker(max_organic=1, max_ai_mode=0, max_scrapes=1), scorecards=[card])
    adjudicator = ExactProductLLMAdjudicator(config=HarnessConfig(enable_llm_adjudication=True), service=FakeLLM())
    adjudicator.adjudicate_state(state)
    resolved = selector.select(task=task, scorecards=state.scorecards, termination_reason=None, budget_snapshot=budget, llm_calls_used=len(state.llm_call_records))
    assert resolved.product_url == card.candidate.url
    assert resolved.llm_decision == "EXACT_MATCH"
