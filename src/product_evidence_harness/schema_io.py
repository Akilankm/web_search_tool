from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.product_evidence_harness.feature_schema import FeatureCriticality, FeatureDefinition, FeatureSchema


_ALLOWED_SIMPLE_FEATURE_KEYS = {"name", "description"}


def _feature_id(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name)
    ascii_text = "".join(ch for ch in folded if not unicodedata.combining(ch))
    identifier = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").upper()
    if not identifier:
        raise ValueError(f"Cannot derive a feature ID from feature name: {name!r}")
    return identifier


def _simple_feature_records(items: Sequence[Any]) -> list[dict[str, Any]]:
    if not items:
        raise ValueError("features_to_code must contain at least one feature")

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        description = ""
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, Mapping):
            unknown = set(item) - _ALLOWED_SIMPLE_FEATURE_KEYS
            if unknown:
                raise ValueError(
                    "Feature objects support only 'name' and optional 'description'; "
                    f"unsupported key(s) at index {index}: {', '.join(sorted(unknown))}"
                )
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
        else:
            raise ValueError(
                "Each features_to_code entry must be a feature-name string or "
                "an object containing 'name' and optional 'description'"
            )

        if not name:
            raise ValueError(f"Feature name is empty at index {index}")
        feature_id = _feature_id(name)
        if feature_id in seen_ids:
            raise ValueError(f"Duplicate feature after normalization: {name!r} -> {feature_id}")
        seen_ids.add(feature_id)
        records.append(
            {
                "feature_id": feature_id,
                "feature_name": name,
                "value_type": "text",
                "criticality": FeatureCriticality.REQUIRED.value,
                "aliases": (name,),
                "description": description,
            }
        )
    return records


def _load_json_schema(payload: Any, source: Path) -> FeatureSchema:
    if not isinstance(payload, dict):
        raise ValueError("Feature schema JSON must be an object")

    if "features_to_code" in payload:
        unknown_top_level = set(payload) - {"features_to_code"}
        if unknown_top_level:
            raise ValueError(
                "The simplified feature input supports only the top-level key "
                f"'features_to_code'; unsupported key(s): {', '.join(sorted(unknown_top_level))}"
            )
        items = payload.get("features_to_code")
        if not isinstance(items, list):
            raise ValueError("features_to_code must be a JSON array")
        return FeatureSchema.from_records(
            _simple_feature_records(items),
            schema_id=source.stem,
            required_coverage_threshold=1.0,
        )

    # Backward-compatible loader for existing internal/legacy integrations.
    records = payload.get("features") or payload.get("records") or []
    return FeatureSchema.from_records(
        records,
        schema_id=str(payload.get("schema_id") or source.stem),
        pg_name=str(payload.get("pg_name") or ""),
        required_coverage_threshold=float(payload.get("required_coverage_threshold") or 0.80),
    )


def load_feature_schema(path: str | Path) -> FeatureSchema:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".json":
        return _load_json_schema(json.loads(source.read_text(encoding="utf-8")), source)
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
        return FeatureSchema.from_records(records, schema_id=source.stem)
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd

        records: list[dict[str, Any]] = pd.read_excel(source, dtype=str, keep_default_na=False).to_dict(orient="records")
        return FeatureSchema.from_records(records, schema_id=source.stem)
    raise ValueError(f"Unsupported feature schema format: {suffix}")
