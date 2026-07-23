from __future__ import annotations

from dataclasses import replace

import pytest

from product_url_v2.models import CandidateAssessment, DeliveryStatus, GateStatus, IdentityMatch, SourceRole, to_jsonable
from product_url_v2.policy import ACCEPTANCE_POLICY_VERSION, choose_delivery, evaluate_acceptance

EAN = "9783311706717"


def candidate(**changes) -> CandidateAssessment:
    values = {
        "candidate_id": "C-1",
        "url": "https://shop.example.ch/product/exact-9783311706717",
        "domain": "shop.example.ch",
        "search_rank": 1,
        "search_support": 1.0,
        "source_role": SourceRole.COUNTRY_RETAILER,
        "identity_match": IdentityMatch.EXACT,
        "identity_confidence": 0.99,
        "direct_product_page": GateStatus.PASS,
        "direct_page_score": 0.95,
        "durable_url": GateStatus.PASS,
        "country_match": GateStatus.PASS,
        "retailer_match": GateStatus.NOT_ASSESSED,
        "browser_access": GateStatus.PASS,
        "text_extractable": GateStatus.PASS,
        "coding_evidence_complete": GateStatus.PASS,
        "source_authority": 75,
        "evidence": {
            "required_identifier": EAN,
            "exact_identifier_verified": True,
            "search_product_like": True,
            "delivery_basis": "rendered_product_evidence",
        },
        "conflicts": (),
        "warnings": (),
    }
    values.update(changes)
    return CandidateAssessment(**values)


@pytest.mark.parametrize(
    ("change", "expected_gate"),
    [
        ({"identity_match": IdentityMatch.UNVERIFIED}, "exact_identity"),
        ({"evidence": {"required_identifier": EAN, "exact_identifier_verified": False, "search_product_like": True}}, "supplied_identifier"),
        ({"direct_product_page": GateStatus.FAIL}, "direct_product_page"),
        ({"durable_url": GateStatus.NOT_ASSESSED}, "durable_url"),
        ({"browser_access": GateStatus.FAIL}, "browser_access"),
        ({"text_extractable": GateStatus.NOT_ASSESSED}, "scrapable_content"),
        ({"conflicts": ("different edition",)}, "no_identity_conflicts"),
    ],
)
def test_every_mandatory_gate_independently_blocks_delivery(change, expected_gate) -> None:
    item = candidate(**change)
    verdict = evaluate_acceptance(item)
    decision = choose_delivery((item,))

    assert verdict.policy_version == ACCEPTANCE_POLICY_VERSION
    assert verdict.eligible is False
    assert any(gate.key == expected_gate and not gate.passed for gate in verdict.gates)
    assert decision.status is DeliveryStatus.FAILED
    assert decision.selected_url is None


def test_secondary_coding_gap_can_only_produce_review_after_mapping_passes() -> None:
    item = candidate(coding_evidence_complete=GateStatus.FAIL)
    verdict = evaluate_acceptance(item)
    decision = choose_delivery((item,))

    assert verdict.eligible is True
    assert verdict.strictly_verified is False
    assert decision.status is DeliveryStatus.REVIEW_REQUIRED
    assert decision.selected_url == item.url


def test_no_identifier_input_does_not_invent_an_identifier_requirement() -> None:
    item = candidate(evidence={"required_identifier": "", "exact_identifier_verified": False, "search_product_like": True})
    verdict = evaluate_acceptance(item)

    assert verdict.identifier_required is False
    assert verdict.identifier_verified is True
    assert verdict.eligible is True


def test_serialized_candidate_and_typed_candidate_have_identical_verdicts() -> None:
    item = candidate(coding_evidence_complete=GateStatus.FAIL, retailer_match=GateStatus.FAIL)

    typed = evaluate_acceptance(item).as_dict()
    serialized = evaluate_acceptance(to_jsonable(item)).as_dict()

    assert typed == serialized


def test_ineligible_manufacturer_never_outranks_eligible_retailer() -> None:
    manufacturer = candidate(
        candidate_id="M",
        url="https://brand.example.ch/product/exact-9783311706717",
        domain="brand.example.ch",
        source_role=SourceRole.LOCAL_MANUFACTURER,
        source_authority=100,
        browser_access=GateStatus.FAIL,
    )
    retailer = candidate(candidate_id="R")

    decision = choose_delivery((manufacturer, retailer))

    assert decision.selected_candidate_id == "R"
    assert decision.selected_url == retailer.url


def test_eligible_manufacturer_outranks_eligible_retailer() -> None:
    retailer = candidate(candidate_id="R")
    manufacturer = replace(
        retailer,
        candidate_id="M",
        url="https://brand.example.ch/product/exact-9783311706717",
        domain="brand.example.ch",
        source_role=SourceRole.LOCAL_MANUFACTURER,
        source_authority=100,
    )

    decision = choose_delivery((retailer, manufacturer))

    assert decision.selected_candidate_id == "M"
