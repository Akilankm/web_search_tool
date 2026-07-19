from __future__ import annotations

import json
from pathlib import Path

from src.product_evidence_harness.belief import MarketStage, ProductBeliefArtifactWriter, ProductBeliefEngine
from src.product_evidence_harness.contracts import MatchVerification, ProductQuery, ScrapeResult


def _verification(url: str) -> MatchVerification:
    return MatchVerification(
        url=url, identity_status="VERIFIED", ean_check="NOT_PROVIDED", title_check="STRONG",
        quantity_check="MATCHED", brand_check="MATCHED", page_type_check="PRODUCT_DETAIL",
        title_match_score=0.94, exact_product_check="EXACT_MATCH", variant_check="MATCHED",
        identity_driver="MAIN_TEXT_AND_SCRAPED_EVIDENCE", requested_quantity="150 ml",
        page_quantity="150 ml", justifications=("exact title and size",),
    )


def _scrape(url: str) -> ScrapeResult:
    return ScrapeResult(
        url=url, scraped=True, success=True, reachable=True, is_scrapable=True, status_code=200,
        final_url=url, title="Nivea Men Deep Espresso antiperspirant spray 150 ml",
        h1="Nivea Men Deep Espresso 150 ml", page_product_name="Nivea Men Deep Espresso antiperspirant spray 150 ml",
        brand="Nivea", manufacturer="Beiersdorf",
        description="Information-rich exact product page with product format, size, brand, usage and packaging details.",
        specs={"format": "aerosol spray", "size": "150 ml"}, image_urls=("https://example.cz/image.jpg",),
        richness_score=0.88, markdown_excerpt="Nivea Men Deep Espresso antiperspirant aerosol spray 150 ml product information",
        markdown_chars=1800, word_count=220, image_count=1, looks_like_product_page=True,
        is_soft_404=False, verification_text="Nivea Men Deep Espresso antiperspirant aerosol spray 150 ml",
    )


def test_market_path_is_requested_retailer_then_country_then_global() -> None:
    engine = ProductBeliefEngine(enable_llm=False)
    product = ProductQuery(row_id="ROW-1", main_text="NIVEA MEN DEEP ESPRESSO 150ML 6X", country_code="CZ", retailer_name="Alza")
    belief = engine.initialize(product)
    assert engine.market_stage_for_credit(product, 1) == MarketStage.REQUESTED_RETAILER
    assert engine.market_stage_for_credit(product, 2) == MarketStage.COUNTRY_ALTERNATIVE
    assert engine.market_stage_for_credit(product, 3) == MarketStage.GLOBAL_FALLBACK
    assert '"Alza"' in engine.query_for_stage(product, belief, MarketStage.REQUESTED_RETAILER)
    assert "Alza" not in engine.query_for_stage(product, belief, MarketStage.COUNTRY_ALTERNATIVE)


def test_no_retailer_starts_with_country_market() -> None:
    engine = ProductBeliefEngine(enable_llm=False)
    product = ProductQuery(row_id="ROW-2", main_text="LEGO 75379 R2-D2", country_code="CZ")
    belief = engine.initialize(product)
    assert belief.market_path == ("country_alternative", "global_fallback")
    assert engine.market_stage_for_credit(product, 1) == MarketStage.COUNTRY_ALTERNATIVE
    assert engine.market_stage_for_credit(product, 3) == MarketStage.GLOBAL_FALLBACK


def test_scrape_evidence_updates_beliefs_and_ledger() -> None:
    engine = ProductBeliefEngine(enable_llm=False)
    product = ProductQuery(row_id="ROW-3", main_text="NIVEA MEN DEEP ESPRESSO 150ML 6X", country_code="CZ")
    belief = engine.initialize(product)
    before = belief.leading_hypothesis.posterior_probability
    url = "https://shop.example.cz/nivea-men-deep-espresso-150ml"
    engine.update_from_scrape(belief, product, _scrape(url), _verification(url), market_stage="country_alternative")
    assert belief.evidence_ledger
    assert len(belief.snapshots) == 2
    assert belief.leading_hypothesis.posterior_probability >= before
    assert belief.current_market_stage == "country_alternative"
    assert belief.resolution_status.value in {"EXACT", "PROBABLE", "IN_PROGRESS", "AMBIGUOUS"}


def test_belief_artifacts_are_human_and_machine_readable(tmp_path: Path) -> None:
    engine = ProductBeliefEngine(enable_llm=False)
    product = ProductQuery(row_id="ROW-4", main_text="LEGO 75379 R2-D2", country_code="CZ")
    belief = engine.initialize(product)
    ProductBeliefArtifactWriter().write(tmp_path, belief)
    expected = {"product_belief.json", "product_understanding.md", "market_decision_path.md", "belief_updates.md", "evidence_ledger.jsonl"}
    assert expected.issubset({path.name for path in tmp_path.iterdir()})
    payload = json.loads((tmp_path / "product_belief.json").read_text(encoding="utf-8"))
    assert payload["row_id"] == "ROW-4"
    assert payload["hypotheses"]
    assert "hidden chain-of-thought" in (tmp_path / "product_understanding.md").read_text(encoding="utf-8")
