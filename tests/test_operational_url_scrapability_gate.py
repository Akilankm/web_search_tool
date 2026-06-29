from __future__ import annotations

from product_evidence_harness import ProductEvidenceHarness, ProductQuery, ProductSearchState, ProductURLMatch, ScrapeResult


def _match(url: str) -> ProductURLMatch:
    return ProductURLMatch(
        row_id="row-1",
        main_text="demo product",
        country_code="CO",
        retailer_name="Mercado Libre",
        ean=None,
        product_url=url,
        best_available_url=url,
        verified_exact_url=None,
        confidence=0.61,
        validation_status="NEEDS_REVIEW",
        identity_status="WEAK",
        is_exact_product_match=False,
        match_reason="best available",
        justification="candidate selected as best available",
        needs_review=True,
    )


def test_non_scrapable_best_available_is_not_emitted_as_product_url() -> None:
    url = "https://example.com/product/123"
    state = ProductSearchState(
        task=ProductQuery(main_text="demo product", country_code="CO", row_id="row-1"),
        budget=None,
        scrapes={
            url: ScrapeResult(
                url=url,
                scraped=True,
                success=True,
                reachable=True,
                is_scrapable=False,
                status_code=200,
                final_url=url,
                looks_like_product_page=True,
            )
        },
    )

    sanitized = ProductEvidenceHarness._enforce_scrapable_operational_url(_match(url), state)

    assert sanitized.product_url is None
    assert sanitized.best_available_url is None
    assert sanitized.best_reference_url == url
    assert sanitized.needs_review is True
    assert sanitized.url_decision_status == "NO_SCRAPABLE_PRODUCT_URL_FOUND"


def test_scrape_usable_best_available_can_remain_product_url() -> None:
    url = "https://example.com/product/123"
    state = ProductSearchState(
        task=ProductQuery(main_text="demo product", country_code="CO", row_id="row-1"),
        budget=None,
        scrapes={
            url: ScrapeResult(
                url=url,
                scraped=True,
                success=True,
                reachable=True,
                is_scrapable=True,
                status_code=200,
                final_url=url,
                looks_like_product_page=True,
            )
        },
    )

    sanitized = ProductEvidenceHarness._enforce_scrapable_operational_url(_match(url), state)

    assert sanitized.product_url == url
    assert sanitized.best_available_url == url
