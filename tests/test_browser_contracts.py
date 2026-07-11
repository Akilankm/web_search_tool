from src.product_evidence_harness.browser_contracts import BrowserEvidenceRequest, EvidenceIntent, ProductIdentityPayload


def test_browser_request_round_trip() -> None:
    request = BrowserEvidenceRequest(
        job_id="job-1",
        candidate_id="cand-1",
        url="https://example.com/product/1",
        product_identity=ProductIdentityPayload(
            row_id="row-1",
            main_text="Example Product",
            country_code="CH",
        ),
        intent=EvidenceIntent(maximum_images=5, requested_evidence_categories=("product_gallery",)),
    )
    assert BrowserEvidenceRequest.from_mapping(request.to_dict()) == request


def test_browser_request_rejects_non_http_url() -> None:
    try:
        BrowserEvidenceRequest(
            job_id="job-1",
            candidate_id="cand-1",
            url="file:///etc/passwd",
            product_identity=ProductIdentityPayload(row_id="r", main_text="x", country_code="US"),
        )
    except ValueError as exc:
        assert "absolute HTTP" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
