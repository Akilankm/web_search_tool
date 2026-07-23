from product_url_v2.config import RuntimeConfig
from product_url_v2.evaluation import apply_browser_evidence, assess_candidate, choose_delivery
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import BrowserEvidence, DeliveryStatus, GateStatus, PageEvidence, ProductInput, SearchResult


def page(text: str, products=()):
    return PageEvidence(
        "https://shop.example/products/item", "https://shop.example/products/item", 200, "text/html",
        text, text, text, products, {"og:type": "product"}, (), (), GateStatus.PASS,
    )


def test_missing_coding_evidence_retains_exact_usable_review_url() -> None:
    product = ProductInput("P1", "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK", "DE", language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    candidate = assess_candidate(
        product,
        interpretation,
        SearchResult("https://shop.example/products/item", "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK", "", "fixture", "google", "", 1, True),
        page(
            "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK price add to cart",
            ({"@type": "Product", "name": "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK", "brand": {"name": "LEITZ"}},),
        ),
        {"required_fields": ["brand", "product_name", "nonexistent_feature"]},
        RuntimeConfig(),
    )
    candidate = apply_browser_evidence(
        product,
        interpretation,
        candidate,
        BrowserEvidence(
            candidate.url,
            GateStatus.PASS,
            candidate.url,
            "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK",
            "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK price add to cart",
            product_controls=("Add to cart",),
        ),
        RuntimeConfig(),
    )
    decision = choose_delivery([candidate])
    assert decision.status is DeliveryStatus.REVIEW_REQUIRED
    assert decision.selected_url == candidate.url
    assert candidate.mapping_eligible is True
    assert candidate.coding_evidence_complete is GateStatus.FAIL


def test_explicit_ean_conflict_is_not_delivered() -> None:
    product = ProductInput("P2", "LEGO SET 75379", "GB", ean="1234567890123")
    interpretation = DeterministicProductInterpreter().interpret(product)
    candidate = assess_candidate(
        product,
        interpretation,
        SearchResult("https://shop.example/products/item", "Other", "", "fixture", "google", "", 1, True),
        page("Other product price add to cart", ({"@type": "Product", "name": "Other", "gtin13": "9999999999999", "offers": {"price": "10"}},)),
        {"required_fields": ["brand", "product_name"]},
        RuntimeConfig(),
    )
    assert candidate.conflicts
    assert candidate.mapping_eligible is False
    assert choose_delivery([candidate]).status is DeliveryStatus.FAILED
