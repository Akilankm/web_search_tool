from __future__ import annotations

import json

from src.product_evidence_harness.agentic_browser_contracts import (
    AgenticBrowserElement,
    AgenticBrowserObservation,
)
from src.product_evidence_harness.browser_contracts import (
    BrowserEvidenceRequest,
    EvidenceIntent,
    ProductIdentityPayload,
)
from src.product_evidence_harness.candidate_precision import (
    CandidatePrecisionGate,
    canonicalize_candidate_url,
    classify_candidate_url,
)
from src.product_evidence_harness.candidate_reporting import build_candidate_records
from src.product_evidence_harness.contracts import ProductQuery, URLCandidate
from src.product_evidence_harness.feature_schema import (
    FeatureCriticality,
    FeatureDefinition,
    FeatureSchema,
)
from src.product_evidence_harness.llm.agentic_browser import (
    AgenticBrowserConfig,
    AgenticBrowserInvestigator,
)
from src.product_evidence_harness.three_stage_environment import (
    validate_runtime_environment,
)


def _candidate(url: str, *, position: int = 1, title: str = "Acme Turbo Racer 12345") -> URLCandidate:
    return URLCandidate(
        url=url,
        title=title,
        snippet="Acme Turbo Racer toy product detail page with manufacturer and age information",
        domain="shop.example",
        source_types=("serp_organic_results", "scope_country_primary"),
        query_sources=("acme turbo racer",),
        best_position=position,
        organic_count=1,
    )


def _schema() -> FeatureSchema:
    return FeatureSchema(
        schema_id="toy",
        required_coverage_threshold=1.0,
        features=(
            FeatureDefinition(
                feature_id="brand",
                feature_name="Brand",
                criticality=FeatureCriticality.CRITICAL,
                description="Product brand shown on the detail page",
            ),
            FeatureDefinition(
                feature_id="minimum_age",
                feature_name="Minimum recommended age",
                description="Minimum recommended age or age warning",
            ),
        ),
    )


def _request() -> BrowserEvidenceRequest:
    return BrowserEvidenceRequest(
        job_id="ROW-1",
        candidate_id="CAND-001",
        url="https://shop.example/products/acme-turbo-racer-12345",
        product_identity=ProductIdentityPayload(
            row_id="ROW-1",
            main_text="Acme Turbo Racer 12345",
            country_code="IN",
        ),
        intent=EvidenceIntent(maximum_actions=20),
    )


def _observation(text: str, *, action_count: int = 1) -> AgenticBrowserObservation:
    return AgenticBrowserObservation(
        session_id="SESSION-1",
        candidate_id="CAND-001",
        url="https://shop.example/products/acme-turbo-racer-12345",
        title="Acme Turbo Racer 12345",
        visible_product_name="Acme Turbo Racer 12345",
        visible_text=text,
        interactive_elements=(
            AgenticBrowserElement(
                element_id="E001",
                role="button",
                text="Add to cart",
                tag="button",
            ),
            AgenticBrowserElement(
                element_id="E002",
                role="tab",
                text="Specifications and age details",
                tag="button",
            ),
        ),
        images=(),
        blockers=(),
        warnings=(),
        action_count=action_count,
        maximum_actions=20,
        screenshot_path=None,
        terminal=False,
    )


class _NeverCallService:
    def __init__(self) -> None:
        self.calls = 0

    def predict(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("LLM should not be called when all features are resolved")


class _DummyBrowser:
    pass


def test_canonical_url_strips_tracking_but_preserves_product_identity() -> None:
    value = canonicalize_candidate_url(
        "https://www.shop.example/products/12345/?utm_source=serp&fbclid=x&sku=ABC-1#details"
    )

    assert value.startswith("https://shop.example/products/12345")
    assert "sku=ABC-1" in value
    assert "utm_" not in value
    assert "fbclid" not in value
    assert "#" not in value


def test_url_classifier_rejects_weak_types_and_accepts_numeric_product_path() -> None:
    assert classify_candidate_url("https://shop.example/") == "HOMEPAGE"
    assert classify_candidate_url("https://shop.example/search?q=turbo") == "SEARCH_RESULTS"
    assert classify_candidate_url("https://facebook.com/acme/posts/1") == "SOCIAL_OR_COMMUNITY"
    assert classify_candidate_url("https://shop.example/manual.pdf") == "DOCUMENT_OR_MEDIA"
    assert classify_candidate_url("https://shop.example/products/12345") == "PRODUCT_DETAIL_LIKELY"


def test_precision_gate_rejects_category_and_low_identity_before_scrape() -> None:
    product = ProductQuery(
        row_id="ROW-1",
        main_text="Acme Turbo Racer 12345",
        country_code="IN",
    )
    gate = CandidatePrecisionGate(minimum_score=0.28)

    category = gate.evaluate(
        product,
        _candidate(
            "https://shop.example/category/toys",
            title="Toy catalogue",
        ),
    )
    irrelevant = gate.evaluate(
        product,
        _candidate(
            "https://shop.example/products/unrelated-doll-99999",
            title="Unrelated fashion doll",
        ),
    )
    product_page = gate.evaluate(
        product,
        _candidate("https://shop.example/products/acme-turbo-racer-12345"),
    )

    assert category.admitted_for_scrape is False
    assert "REJECTED_URL_TYPE" in category.admission_reason
    assert irrelevant.admitted_for_scrape is False
    assert "LOW_IDENTITY" in irrelevant.admission_reason or "LOW_PREFLIGHT" in irrelevant.admission_reason
    assert product_page.admitted_for_scrape is True


def test_scrape_selection_enforces_total_and_cumulative_domain_caps() -> None:
    product = ProductQuery(
        row_id="ROW-1",
        main_text="Acme Turbo Racer 12345",
        country_code="IN",
    )
    gate = CandidatePrecisionGate(
        minimum_score=0.20,
        maximum_full_scrapes=6,
        maximum_per_domain=2,
    )
    candidates = [
        _candidate(f"https://shop.example/products/acme-turbo-racer-1234{index}", position=index)
        for index in range(1, 5)
    ] + [
        URLCandidate(
            **{
                **_candidate(
                    "https://other.example/product/acme-turbo-racer-12345",
                    position=5,
                ).to_dict(),
                "domain": "other.example",
            }
        )
    ]

    selected, decisions = gate.select_for_scrape(
        product=product,
        candidates=candidates,
        already_scraped=["https://shop.example/products/acme-turbo-racer-12340"],
        maximum_new=6,
    )

    assert len(selected) <= 6
    assert sum(candidate.domain == "shop.example" for candidate in selected) == 1
    assert any(candidate.domain == "other.example" for candidate in selected)
    assert any(
        decision.admission_reason == "QUALIFIED_NOT_SCRAPED_DOMAIN_DIVERSITY_CAP"
        for decision in decisions.values()
    )


def test_agentic_config_clamps_legacy_context_values(monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE", "10")
    monkeypatch.setenv("PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE", "20")
    monkeypatch.setenv("PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS", "12000")
    monkeypatch.setenv("PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS", "60")
    monkeypatch.setenv("PRODUCT_HARNESS_AGENTIC_MAX_IMAGES", "30")

    config = AgenticBrowserConfig.from_env()

    assert config.max_turns_per_candidate == 4
    assert config.max_actions_per_candidate == 6
    assert config.max_observation_chars == 5000
    assert config.max_elements_in_prompt == 18
    assert config.max_images_in_prompt == 10


def test_prompt_uses_relevant_delta_and_ranks_specification_control_first() -> None:
    investigator = AgenticBrowserInvestigator(
        browser=_DummyBrowser(),  # type: ignore[arg-type]
        service=_NeverCallService(),  # type: ignore[arg-type]
        config=AgenticBrowserConfig(
            max_turns_per_candidate=4,
            max_actions_per_candidate=6,
            max_observation_chars=2000,
            max_elements_in_prompt=2,
            max_images_in_prompt=2,
        ),
    )
    first = json.loads(
        investigator._prompt(
            _request(),
            _schema(),
            _observation(
                "Acme Turbo Racer product page. Brand Acme is visible. General shipping information."
            ),
            [],
        )
    )
    second = json.loads(
        investigator._prompt(
            _request(),
            _schema(),
            _observation(
                "Acme Turbo Racer product page. Brand Acme is visible. General shipping information. Minimum recommended age is 6 years.",
                action_count=2,
            ),
            [],
        )
    )

    first_control = first["new_relevant_observation"]["interactive_elements"][0]
    second_text = second["new_relevant_observation"]["visible_text"]
    assert first["context_policy"]["mode"] == "incremental_delta_relevance_filtered"
    assert first_control["element_id"] == "E002"
    assert "6 years" in second_text
    assert "shipping information" not in second_text


def test_plan_finishes_without_llm_when_features_already_resolved() -> None:
    service = _NeverCallService()
    investigator = AgenticBrowserInvestigator(
        browser=_DummyBrowser(),  # type: ignore[arg-type]
        service=service,  # type: ignore[arg-type]
        config=AgenticBrowserConfig(max_turns_per_candidate=4),
    )
    plan = investigator._plan(
        _request(),
        _schema(),
        _observation("All product evidence is already resolved."),
        [
            {
                "candidate_assessment": {
                    "resolved_feature_ids": ["brand", "minimum_age"]
                }
            }
        ],
    )

    assert plan["action"] == "finish"
    assert plan["termination_reason"] == "ALL_REQUESTED_FEATURES_RESOLVED"
    assert service.calls == 0


def test_candidate_ledger_is_one_row_per_canonical_url() -> None:
    canonical = "https://shop.example/products/acme-turbo-racer-12345"
    candidate_state = {
        "candidates": [
            {
                "url": canonical + "?utm_source=one",
                "title": "Acme Turbo Racer",
                "snippet": "Exact product",
                "domain": "shop.example",
                "source_types": ["scope_country_primary"],
                "organic_count": 1,
                "best_position": 1,
            },
            {
                "url": canonical + "?utm_source=two",
                "title": "Acme Turbo Racer",
                "snippet": "Exact product duplicate",
                "domain": "shop.example",
                "source_types": ["scope_global_fallback"],
                "organic_count": 1,
                "best_position": 4,
            },
        ],
        "candidate_admissions": [
            {
                "canonical_url": canonical,
                "url_type": "PRODUCT_DETAIL_LIKELY",
                "preflight_score": 0.91,
                "identity_overlap": 1.0,
                "admitted_for_scrape": True,
                "admission_reason": "QUALIFIED_FOR_FULL_SCRAPE",
            }
        ],
        "scrapes": {
            canonical: {
                "success": True,
                "reachable": True,
                "is_scrapable": True,
                "word_count": 120,
                "markdown_chars": 2000,
                "looks_like_product_page": True,
                "looks_like_homepage": False,
                "is_soft_404": False,
                "richness_score": 0.8,
                "page_product_name": "Acme Turbo Racer",
                "has_price": True,
                "final_url": canonical,
            }
        },
        "verifications": {
            canonical: {
                "identity_status": "VERIFIED",
                "page_type_check": "PRODUCT_DETAIL",
                "ean_check": "MATCHED",
                "title_check": "STRONG",
                "variant_check": "MATCHED",
            }
        },
        "scorecards": [
            {
                "candidate": {"url": canonical},
                "validation_status": "VERIFIED",
                "final_confidence": 0.94,
                "hard_failures": [],
                "soft_warnings": [],
            }
        ],
    }
    result = {
        "primary_url": canonical,
        "evidence_set": {"selected_urls": [canonical]},
        "candidate_investigations": [],
        "browser_evidence": [],
        "feature_assessments": [
            {
                "url": canonical,
                "identity_status": "VERIFIED",
                "coverage": 1.0,
                "missing_features": [],
                "conflicting_features": [],
                "evidence": [
                    {
                        "feature_id": "brand",
                        "feature_name": "Brand",
                        "value": "Acme",
                        "status": "STRUCTURED_FOUND",
                        "confidence": 0.99,
                    }
                ],
            }
        ],
    }

    records = build_candidate_records(result, candidate_state)

    assert len(records) == 1
    assert records[0]["canonical_url"] == canonical
    assert records[0]["final_status"] == "STRICT_SELECTED"
    assert records[0]["feature_brand_value"] == "Acme"
    assert records[0]["scrape_accepted"] is True


def test_environment_reports_effective_hard_context_caps_for_legacy_values() -> None:
    values = {
        "SERPAPI_API_KEY": "serpapi_key_with_more_than_twenty_chars",
        "PRODUCT_HARNESS_WORKFLOW": "three_stage_feature_aware",
        "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES": "3",
        "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES": "0",
        "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER": "true",
        "PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER": "true",
        "PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE": "true",
        "PRODUCT_HARNESS_COUNTRY_FIRST": "true",
        "PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK": "true",
        "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY": "true",
        "PRODUCT_HARNESS_REJECT_EXPIRING_URLS": "true",
        "PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES": "90",
        "PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE": "10",
        "PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE": "20",
        "PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS": "12000",
        "PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS": "60",
        "PRODUCT_HARNESS_AGENTIC_MAX_IMAGES": "30",
        "PRODUCT_HARNESS_MAX_FULL_SCRAPES": "6",
        "PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN": "2",
        "PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE": "0.28",
        "LLM_API_KEY": "x",
        "LLM_API_VERSION": "internal-v1",
        "LLM_ENDPOINT": "enterprise-gateway/openai",
        "LLM_DEPLOYMENT": "vision-production",
    }

    report = validate_runtime_environment(
        None,
        strict_file_permissions=False,
        environ=values,
    )

    assert report.max_agentic_candidates == 3
    assert report.max_agentic_turns_per_candidate == 4
    assert report.max_agentic_actions_per_candidate == 6
    assert "llm_agentic_browser_context_budget_validated" in report.checks_passed
