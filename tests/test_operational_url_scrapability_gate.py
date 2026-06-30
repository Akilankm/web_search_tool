from __future__ import annotations

from product_evidence_harness import ProductEvidenceHarness, ProductQuery, ProductSearchState, ProductURLMatch, ScrapeResult
from product_evidence_harness.contracts import URLCandidate


def _match(url: str | None) -> ProductURLMatch:
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


def test_non_scrapable_best_available_is_emitted_with_review_status() -> None:
    url = "https://retailer.test/product/123"
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

    sanitized = ProductEvidenceHarness._enforce_nonempty_product_url(_match(url), state)

    assert sanitized.product_url == url
    assert sanitized.best_available_url == url
    assert sanitized.best_reference_url == url
    assert sanitized.needs_review is True
    assert sanitized.is_scrapable is False
    assert sanitized.url_decision_status == "BEST_AVAILABLE_PRODUCT_URL_NOT_SCRAPABLE_NEEDS_REVIEW"


def test_scrape_usable_best_available_can_remain_product_url() -> None:
    url = "https://retailer.test/product/123"
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

    sanitized = ProductEvidenceHarness._enforce_nonempty_product_url(_match(url), state)

    assert sanitized.product_url == url
    assert sanitized.best_available_url == url
    assert sanitized.is_scrapable is True


def test_blank_match_uses_best_discovered_candidate_url() -> None:
    url = "https://fallback.test/product/456"
    state = ProductSearchState(
        task=ProductQuery(main_text="demo product", country_code="CO", row_id="row-1"),
        budget=None,
        candidates=[URLCandidate(url=url, title="fallback product", domain="fallback.test")],
    )

    sanitized = ProductEvidenceHarness._enforce_nonempty_product_url(_match(None), state)

    assert sanitized.product_url == url
    assert sanitized.best_available_url == url
    assert sanitized.needs_review is True
    assert sanitized.url_decision_status == "DISCOVERED_CANDIDATE_URL_UNSCRAPED_NEEDS_REVIEW"
