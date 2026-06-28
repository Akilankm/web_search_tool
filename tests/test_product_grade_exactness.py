from product_evidence_harness.contracts import ProductQuery, ScrapeResult
from product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from product_evidence_harness.identity_verifier import ProductIdentityVerifier


def test_compact_identity_graph_preserves_size_color_and_form():
    q = ProductQuery(main_text="1001KARTENA5FLIEDER", country_code="CH", ean="7612450206555")
    g = ProductIdentityGraphBuilder().build(q)
    assert "a5" in g.size_terms
    assert "flieder" in g.color_terms
    assert "card" in g.product_form_families
    assert q.ean == "7612450206555"


def test_wrong_variant_a4_paper_rejected_for_a5_cards():
    q = ProductQuery(main_text="1001KARTENA5FLIEDER", country_code="CH", ean="7612450206555")
    scrape = ScrapeResult(
        url="https://example.test/product",
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url="https://example.test/product",
        title="Artoz 1001 A4 100g flieder Bastelpapier",
        h1="Artoz 1001 A4 100g flieder Bastelpapier",
        page_product_name="Artoz 1001 A4 100g flieder Bastelpapier",
        looks_like_product_page=True,
        verification_text="Artoz 1001 A4 100g flieder Bastelpapier",
    )
    v = ProductIdentityVerifier().verify(q, scrape)
    assert v.identity_status == "MISMATCH"
    assert v.variant_check == "CONFLICT"
    assert any("size_format_detector" in x for x in v.variant_conflict_terms)
    assert any("product_form_detector" in x for x in v.variant_conflict_terms)

from product_evidence_harness.contracts import ProductSearchState, URLCandidate
from product_evidence_harness.budget import BudgetTracker
from product_evidence_harness.query_builder import QueryBuilder


def test_model_identifier_conflict_rejects_sibling_product():
    q = ProductQuery(main_text="LEGOFRIENDS41731HEARTLAKEINTERNATIONALSCHOOL", country_code="CH")
    scrape = ScrapeResult(
        url="https://example.test/product",
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        final_url="https://example.test/product",
        title="LEGO Friends 41730 Heartlake School Accessory",
        h1="LEGO Friends 41730 Heartlake School Accessory",
        page_product_name="LEGO Friends 41730 Heartlake School Accessory",
        looks_like_product_page=True,
        verification_text="LEGO Friends 41730 Heartlake School Accessory",
    )
    v = ProductIdentityVerifier().verify(q, scrape)
    assert v.identity_status == "MISMATCH"
    assert v.variant_check == "CONFLICT"
    assert any("model_identifier_detector" in x for x in v.variant_conflict_terms)


def test_repair_query_uses_requested_identity_not_wrong_variant_page_terms():
    q = ProductQuery(main_text="1001KARTENA5FLIEDER", country_code="CH", ean="7612450206555")
    state = ProductSearchState(task=q, budget=BudgetTracker(max_organic=10, max_ai_mode=0, max_scrapes=10))
    state.identity_graph = ProductIdentityGraphBuilder().build(q)
    state.detector_findings["https://example.test/wrong"] = [
        {"detector": "size_format_detector", "status": "CONFLICT", "severity": "HARD_BLOCKER", "input_value": "a5", "page_value": "a4", "explanation": "wrong size"},
        {"detector": "product_form_detector", "status": "CONFLICT", "severity": "HARD_BLOCKER", "input_value": "karten", "page_value": "bastelpapier", "explanation": "wrong form"},
    ]
    query = QueryBuilder().repair_from_state(state, global_fallback=True).lower()
    assert "a5" in query
    assert "karten" in query
    assert "flieder" in query
    assert "-a4" in query
    assert "-bastelpapier" in query
