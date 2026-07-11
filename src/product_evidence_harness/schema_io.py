from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.product_evidence_harness.feature_schema import FeatureSchema


def load_feature_schema(path: str | Path) -> FeatureSchema:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return FeatureSchema.from_records(payload, schema_id=source.stem)
        if not isinstance(payload, dict):
            raise ValueError("Feature schema JSON must be an object or list")
        records = payload.get("features") or payload.get("records") or []
        return FeatureSchema.from_records(
            records,
            schema_id=str(payload.get("schema_id") or source.stem),
            pg_name=str(payload.get("pg_name") or ""),
            required_coverage_threshold=float(payload.get("required_coverage_threshold") or 0.80),
        )
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
        return FeatureSchema.from_records(records, schema_id=source.stem)
    if suffix in {".xlsx", ".xls"}:
        import pandas as pd

        records: list[dict[str, Any]] = pd.read_excel(source, dtype=str, keep_default_na=False).to_dict(orient="records")
        return FeatureSchema.from_records(records, schema_id=source.stem)
    raise ValueError(f"Unsupported feature schema format: {suffix}")
