from __future__ import annotations

import json
from pathlib import Path

from src.product_evidence_harness.manufacturer_primary_runtime import _annotate_result
from src.product_evidence_harness.runtime_contract import (
    RUNTIME_CONTRACT_VERSION,
    runtime_capabilities,
)


def _payload() -> dict:
    return {
        "product": {
            "row_id": "ROW-1",
            "main_text": "LEGO Star Wars R2-D2 75379",
            "country_code": "GB",
            "retailer_name": "Amazon UK",
            "ean": "5702017584379",
            "language_code": "en",
        },
        "feature_set": "toy_features",
    }


def test_result_exposes_manufacturer_primary_and_retailer_reference(
    tmp_path: Path,
) -> None:
    manufacturer = "https://www.lego.com/en-gb/product/r2-d2-75379"
    retailer = "https://www.amazon.co.uk/dp/B0ABC12345"
    result = {
        "primary_url": manufacturer,
        "artifact_dir": str(tmp_path),
        "primary_url_acceptance": {
            "accepted": True,
            "source_role": "MANUFACTURER",
            "source_tier": 0,
            "source_tier_name": "LOCAL_MANUFACTURER",
            "manufacturer_url": manufacturer,
            "retailer_url": retailer,
            "selection_reason": "OFFICIAL_MANUFACTURER_PRIMARY_AFTER_STRICT_GATES",
        },
        "product_match": {"product_url": manufacturer},
        "evidence_set": {"primary_url": manufacturer},
        "url_delivery": {
            "required": True,
            "delivered": True,
            "url": manufacturer,
        },
        "search": {"market_decision_path": []},
    }

    annotated = _annotate_result(_payload(), result)

    assert annotated["primary_url"] == manufacturer
    assert annotated["primary_url_role"] == "OFFICIAL_MANUFACTURER"
    assert annotated["manufacturer_url"] == manufacturer
    assert annotated["retailer_url"] == retailer
    assert annotated["source_selection"]["policy"] == (
        "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES"
    )
    assert annotated["url_delivery"]["manufacturer_first_policy"] is True
    assert annotated["search"]["search_stage_order"] == [
        "manufacturer_primary",
        "requested_retailer_country",
        "global_fallback",
    ]

    artifact = json.loads(
        (tmp_path / "source_selection.json").read_text(encoding="utf-8")
    )
    assert artifact["primary_url_role"] == "OFFICIAL_MANUFACTURER"
    assert artifact["retailer_url"] == retailer


def test_result_marks_retailer_fallback_when_no_manufacturer_passes() -> None:
    retailer = "https://www.amazon.co.uk/dp/B0ABC12345"
    result = {
        "primary_url": retailer,
        "primary_url_acceptance": {
            "accepted": True,
            "source_role": "REQUESTED_RETAILER",
            "source_tier": 2,
            "source_tier_name": "REQUESTED_RETAILER_LOCAL",
            "manufacturer_url": None,
            "retailer_url": retailer,
            "selection_reason": (
                "RETAILER_PRIMARY_BECAUSE_NO_QUALIFIED_MANUFACTURER_PAGE"
            ),
        },
        "product_match": {"product_url": retailer},
        "evidence_set": {"primary_url": retailer},
        "url_delivery": {"required": True, "delivered": True, "url": retailer},
        "search": {"market_decision_path": []},
    }

    annotated = _annotate_result(_payload(), result)

    assert annotated["primary_url_role"] == "RETAILER"
    assert annotated["manufacturer_url"] is None
    assert annotated["retailer_url"] == retailer
    assert annotated["source_selection"]["fallback_rule"].startswith(
        "Use the strongest qualified retailer"
    )


def test_runtime_health_advertises_product_evidence_contracts() -> None:
    capabilities = runtime_capabilities()
    assert RUNTIME_CONTRACT_VERSION == "belief-url-resolution-v10-decision-first-ui"
    assert capabilities["manufacturer_first_primary_url"] is True
    assert capabilities["business_judgement_review_artifact"] is True
    assert capabilities["structured_no_url_review_outcome"] is True
    assert capabilities["per_job_runtime_controls"] is True
    assert capabilities["executive_url_decision_summary"] is True
