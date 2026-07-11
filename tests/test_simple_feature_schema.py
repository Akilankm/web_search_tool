from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_evidence_harness import FeatureCriticality, load_feature_schema


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loads_plain_feature_names_and_derives_internal_contract(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "toy_features.json",
        {"features_to_code": ["brand", "manufacturer", "minimum recommended age"]},
    )

    schema = load_feature_schema(path)

    assert schema.schema_id == "toy_features"
    assert schema.required_coverage_threshold == 1.0
    assert [feature.feature_id for feature in schema.features] == [
        "BRAND",
        "MANUFACTURER",
        "MINIMUM_RECOMMENDED_AGE",
    ]
    assert [feature.feature_name for feature in schema.features] == [
        "brand",
        "manufacturer",
        "minimum recommended age",
    ]
    assert all(feature.criticality == FeatureCriticality.REQUIRED for feature in schema.features)
    assert all(feature.value_type == "text" for feature in schema.features)


def test_supports_only_optional_description_for_a_feature(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "toy_features.json",
        {
            "features_to_code": [
                "brand",
                {
                    "name": "material",
                    "description": "Primary material used to manufacture the toy",
                },
            ]
        },
    )

    schema = load_feature_schema(path)

    material = schema.features[1]
    assert material.feature_id == "MATERIAL"
    assert material.description == "Primary material used to manufacture the toy"
    assert material.aliases == ("material",)


def test_rejects_extra_top_level_configuration(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "toy_features.json",
        {
            "features_to_code": ["brand"],
            "required_coverage_threshold": 0.5,
        },
    )

    with pytest.raises(ValueError, match="only the top-level key 'features_to_code'"):
        load_feature_schema(path)


def test_rejects_extra_feature_object_fields(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "toy_features.json",
        {
            "features_to_code": [
                {
                    "name": "battery required",
                    "description": "Whether batteries are required",
                    "criticality": "optional",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="support only 'name' and optional 'description'"):
        load_feature_schema(path)


def test_rejects_duplicates_after_normalization(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "toy_features.json",
        {"features_to_code": ["play duration", "play-duration"]},
    )

    with pytest.raises(ValueError, match="Duplicate feature after normalization"):
        load_feature_schema(path)
