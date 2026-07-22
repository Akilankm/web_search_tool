from __future__ import annotations

from src.product_evidence_harness.browser_contracts import (
    BrowserEvidenceBundle,
    BrowserEvidenceStatus,
)
from src.product_evidence_harness.executive_summary import build_executive_summary
from src.product_evidence_harness.feature_schema import (
    FeatureCriticality,
    FeatureDefinition,
    FeatureEvidence,
    FeatureEvidenceStatus,
    FeatureSchema,
    URLFeatureAssessment,
)
from src.product_evidence_harness.strict_acceptance import StrictPrimaryURLSelector


def _schema() -> FeatureSchema:
    return FeatureSchema(
        schema_id="review-correlation",
        required_coverage_threshold=1.0,
        features=(
            FeatureDefinition(
                feature_id="brand",
                feature_name="Brand",
                criticality=FeatureCriticality.CRITICAL,
            ),
            FeatureDefinition(
                feature_id="pack",
                feature_name="Pack",
                criticality=FeatureCriticality.REQUIRED,
            ),
        ),
    )


def _assessment(url: str, *, complete: bool) -> URLFeatureAssessment:
    evidence = (
        FeatureEvidence(
            feature_id="brand",
            feature_name="Brand",
            source_url=url,
            value="Pokemon",
            status=FeatureEvidenceStatus.STRUCTURED_FOUND,
            confidence=0.99,
        ),
        FeatureEvidence(
            feature_id="pack",
            feature_name="Pack",
            source_url=url,
            value="Booster" if complete else None,
            status=(
                FeatureEvidenceStatus.STRUCTURED_FOUND
                if complete
                else FeatureEvidenceStatus.NOT_FOUND
            ),
            confidence=0.99 if complete else 0.0,
        ),
    )
    return URLFeatureAssessment(
        url=url,
        identity_accepted=True,
        identity_status="VERIFIED",
        source_role="PRIMARY_CANDIDATE",
        evidence=evidence,
        coverage=1.0 if complete else 0.5,
        required_coverage=1.0 if complete else 0.5,
        critical_coverage=1.0,
        missing_features=() if complete else ("pack",),
        conflicting_features=(),
    )


def _bundle(url: str) -> BrowserEvidenceBundle:
    return BrowserEvidenceBundle(
        status=BrowserEvidenceStatus.COMPLETED,
        job_id="ROW-REVIEW",
        candidate_id="CAND-001",
        requested_url=url,
        final_url=url,
        browser_openable=True,
        rendered_product_verified=True,
        text_scrapable=True,
        gallery_discovered=True,
        direct_images_downloaded=1,
        screenshots_captured=1,
        multimodal_scrapable=True,
    )


def test_incomplete_feature_page_keeps_measured_review_url() -> None:
    url = "https://www.toytans.ch/de/pokemon-booster/example.html"

    decision = StrictPrimaryURLSelector().select(
        schema=_schema(),
        assessments=[_assessment(url, complete=False)],
        browser_bundles=[_bundle(url)],
        scorecards=[],
    )

    assert decision.accepted is False
    assert decision.primary_url == url
    assert decision.browser_openable is True
    assert decision.text_scrapable is True
    assert decision.rendered_product_verified is True
    assert decision.exact_product_verified is True
    assert decision.full_feature_coverage is False
    assert decision.durable_url is True
    assert decision.selection_reason == "BEST_MEASURED_PRODUCT_URL_REQUIRES_REVIEW"
    assert decision.reasons == ("PRIMARY_URL_MISSING_REQUESTED_FEATURES",)


def test_uninvestigated_candidate_is_not_reported_as_browser_failure() -> None:
    url = "https://example.test/product/booster"

    decision = StrictPrimaryURLSelector().select(
        schema=_schema(),
        assessments=[_assessment(url, complete=False)],
        browser_bundles=[],
        scorecards=[],
    )

    assert decision.accepted is False
    assert decision.primary_url is None
    assert decision.browser_openable is None
    assert decision.text_scrapable is None
    assert decision.rendered_product_verified is None
    assert decision.exact_product_verified is None
    assert decision.full_feature_coverage is None
    assert decision.durable_url is None
    assert decision.reasons == ("NO_CANDIDATE_COMPLETED_BROWSER_INVESTIGATION",)
    assert not any("BROWSER_EVIDENCE_MISSING" in reason for reason in decision.reasons)


def test_ui_summary_shows_only_the_measured_feature_failure() -> None:
    url = "https://www.toytans.ch/de/pokemon-booster/example.html"
    decision = StrictPrimaryURLSelector().select(
        schema=_schema(),
        assessments=[_assessment(url, complete=False)],
        browser_bundles=[_bundle(url)],
        scorecards=[],
    )

    summary = build_executive_summary(
        {
            "job_status": "REVIEW_REQUIRED",
            "coding_ready": False,
            "product": {
                "row_id": "ROW-REVIEW",
                "main_text": "PKM ME04 WACHSENDES CHAOS BOOSTER",
            },
            "primary_url": url,
            "primary_url_acceptance": decision.to_dict(),
            "url_delivery": {
                "delivered": True,
                "strictly_verified": False,
                "url": url,
            },
            "feature_assessments": [
                _assessment(url, complete=False).to_dict()
            ],
            "browser_evidence": [_bundle(url).to_dict()],
            "search": {
                "serpapi_requests_used": 2,
                "serpapi_request_limit": 3,
                "stages": [],
            },
        }
    )

    checks = {
        item["key"]: item["status"]
        for item in summary["pillars"]["usability"]["checks"]
    }
    assert summary["selected_url"] == url
    assert summary["overall_status"] == "URL_DELIVERED_REVIEW_REQUIRED"
    assert checks == {
        "browser_openable": "PASS",
        "text_scrapable": "PASS",
        "rendered_product_verified": "PASS",
        "exact_product_verified": "PASS",
        "full_feature_coverage": "FAIL",
        "durable_url": "PASS",
    }
    assert summary["pillars"]["usability"]["passed_checks"] == 5
    assert summary["pillars"]["usability"]["failed_checks"] == 1


def test_ui_summary_uses_not_assessed_without_browser_measurement() -> None:
    url = "https://example.test/product/booster"
    decision = StrictPrimaryURLSelector().select(
        schema=_schema(),
        assessments=[_assessment(url, complete=False)],
        browser_bundles=[],
        scorecards=[],
    )

    summary = build_executive_summary(
        {
            "job_status": "REVIEW_REQUIRED",
            "coding_ready": False,
            "product": {
                "row_id": "ROW-NOT-ASSESSSED",
                "main_text": "Unknown booster",
            },
            # Mandatory URL delivery may still provide a review URL, but the
            # browser gates must remain unassessed rather than fabricated fails.
            "primary_url": url,
            "primary_url_acceptance": decision.to_dict(),
            "url_delivery": {
                "delivered": True,
                "strictly_verified": False,
                "url": url,
            },
            "feature_assessments": [
                _assessment(url, complete=False).to_dict()
            ],
            "browser_evidence": [],
            "search": {
                "serpapi_requests_used": 3,
                "serpapi_request_limit": 3,
                "stages": [],
            },
        }
    )

    statuses = [
        item["status"]
        for item in summary["pillars"]["usability"]["checks"]
    ]
    assert statuses == ["NOT_ASSESSED"] * 6
    assert summary["pillars"]["usability"]["failed_checks"] == 0
    assert summary["pillars"]["usability"]["assessed_checks"] == 0
