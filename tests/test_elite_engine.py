from __future__ import annotations

import json

from product_evidence_harness import ProductQuery
from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.contracts import (
    CandidateScorecard,
    MatchVerification,
    ProductSearchState,
    ProductURLMatch,
    ScrapeResult,
    URLCandidate,
)
from product_evidence_harness.elite import EnterpriseEvidenceEngine


def _state() -> ProductSearchState:
    url = "https://example.cz/product/lego-41731"
    product = ProductQuery(row_id="row-1", main_text="LEGO Friends 41731 Heartlake International School", country_code="CZ", ean="5702017415177")
    candidate = URLCandidate(
        url=url,
        title="LEGO Friends 41731 Heartlake International School",
        snippet="LEGO Friends school set",
        domain="example.cz",
        source_types=("organic",),
    )
    scrape = ScrapeResult(
        url=url,
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url=url,
        title="LEGO Friends 41731 Heartlake International School",
        h1="LEGO Friends 41731 Heartlake International School",
        page_product_name="LEGO Friends 41731 Heartlake International School",
        structured_eans=("5702017415177",),
        has_price=True,
        price=99.9,
        currency="CZK",
        availability="IN_STOCK_SIGNAL",
        brand="LEGO",
        manufacturer="LEGO",
        description="A detailed LEGO Friends school construction set with characters and accessories.",
        specs={"Set number": "41731", "Age": "8+"},
        image_urls=("https://example.cz/img/41731.jpg",),
        richness_score=0.92,
        word_count=900,
        image_count=1,
        looks_like_product_page=True,
        contains_ean=True,
        text_overlap=0.95,
    )
    verification = MatchVerification(
        url=url,
        identity_status="VERIFIED",
        ean_check="MATCHED",
        title_check="STRONG",
        quantity_check="MATCHED",
        brand_check="MATCHED",
        page_type_check="PRODUCT_PAGE",
        title_match_score=0.95,
        exact_product_check="EXACT_MATCH",
        variant_check="MATCHED",
        identity_driver="EAN_AND_TITLE",
        page_gtins_valid=("5702017415177",),
    )
    scorecard = CandidateScorecard(
        candidate=candidate,
        organic_score=1.0,
        ai_score=0.0,
        retailer_score=0.8,
        country_score=1.0,
        ean_score=1.0,
        title_score=0.95,
        product_page_score=1.0,
        scrape_score=1.0,
        identity_score=1.0,
        richness_score=0.92,
        weighted_confidence=0.95,
        confidence_cap=1.0,
        final_confidence=0.95,
        validation_status="VERIFIED",
        scrape=scrape,
        verification=verification,
        retailer_check="NOT_PROVIDED",
        country_check="MATCHED",
        exact_product_check="EXACT_MATCH",
        variant_check="MATCHED",
    )
    final = ProductURLMatch(
        row_id=product.row_id,
        main_text=product.main_text,
        country_code=product.country_code,
        retailer_name=product.retailer_name,
        ean=product.ean,
        product_url=url,
        verified_exact_url=url,
        best_available_url=url,
        confidence=0.95,
        validation_status="VERIFIED",
        identity_status="VERIFIED",
        is_exact_product_match=True,
        match_reason="verified exact",
        justification="EAN and title matched",
        is_scrapable=True,
        needs_review=False,
        selected_domain="example.cz",
        url_decision_status="EXACT_COUNTRY_MATCH",
    )
    state = ProductSearchState(
        task=product,
        budget=BudgetTracker(max_scrapes=10),
        candidates=[candidate],
        scrapes={url: scrape},
        verifications={url: verification},
        scorecards=[scorecard],
        final_result=final,
    )
    return state


def test_enterprise_assessment_marks_strong_row_as_tier_a() -> None:
    assessment = EnterpriseEvidenceEngine().assess(_state())

    assert assessment.quality_tier == "A"
    assert assessment.coding_readiness.status == "CODING_READY"
    assert assessment.confidence.identity_confidence == 1.0
    assert assessment.product_coding_input["selected_url"] == "https://example.cz/product/lego-41731"
    assert assessment.final_submission_extras()["quality_tier"] == "A"


def test_enterprise_writer_outputs_product_coding_artifacts(tmp_path) -> None:
    assessment = EnterpriseEvidenceEngine().write_artifacts(_state(), tmp_path)

    assert (tmp_path / "enterprise_assessment.json").exists()
    assert (tmp_path / "evidence_graph.json").exists()
    assert (tmp_path / "product_coding_input.json").exists()
    assert (tmp_path / "review_feedback_template.json").exists()
    assert (tmp_path / "quality_assessment.md").exists()

    payload = json.loads((tmp_path / "product_coding_input.json").read_text(encoding="utf-8"))
    assert payload["quality_tier"] == assessment.quality_tier
    assert payload["coding_readiness_status"] == "CODING_READY"
