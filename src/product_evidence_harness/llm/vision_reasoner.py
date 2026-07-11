from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.product_evidence_harness.browser_contracts import BrowserEvidenceBundle, VisualAsset
from src.product_evidence_harness.feature_schema import FeatureDefinition, FeatureEvidence, FeatureEvidenceStatus, FeatureSchema
from src.product_evidence_harness.llm.service import LLMService, get_llm_service


@dataclass(frozen=True, slots=True)
class VisionReasonerConfig:
    max_images_per_candidate: int = 4
    max_features_per_call: int = 20
    min_confidence: float = 0.55
    image_detail: str = "high"


class MultimodalFeatureReasoner:
    """Extract only explicit feature evidence from validated browser images/screenshots."""

    def __init__(self, service: LLMService | None = None, config: VisionReasonerConfig | None = None) -> None:
        self.service = service or get_llm_service()
        self.config = config or VisionReasonerConfig()

    def evaluate(
        self,
        *,
        schema: FeatureSchema,
        bundle: BrowserEvidenceBundle,
        missing_feature_ids: Iterable[str] | None = None,
    ) -> tuple[FeatureEvidence, ...]:
        allowed_ids = set(missing_feature_ids or [feature.feature_id for feature in schema.features])
        features = [feature for feature in schema.features if feature.feature_id in allowed_ids]
        if not features:
            return ()
        assets = [asset for asset in bundle.visual_assets if asset.vision_ready and Path(asset.local_path).is_file()]
        assets = assets[: self.config.max_images_per_candidate]
        if not assets:
            return ()

        best: dict[str, FeatureEvidence] = {}
        for asset in assets:
            for chunk in self._chunks(features, self.config.max_features_per_call):
                for evidence in self._evaluate_asset(bundle, asset, chunk):
                    current = best.get(evidence.feature_id)
                    if current is None or evidence.confidence > current.confidence:
                        best[evidence.feature_id] = evidence
        return tuple(best[feature.feature_id] for feature in features if feature.feature_id in best)

    def _evaluate_asset(
        self,
        bundle: BrowserEvidenceBundle,
        asset: VisualAsset,
        features: list[FeatureDefinition],
    ) -> tuple[FeatureEvidence, ...]:
        feature_payload = [
            {
                "feature_id": feature.feature_id,
                "feature_name": feature.feature_name,
                "description": feature.description,
                "allowed_values": list(feature.allowed_values),
            }
            for feature in features
        ]
        prompt = (
            "Inspect the supplied product image or browser screenshot. Return strict JSON only with key "
            "`evidence`, containing zero or more objects. Use only visibly explicit evidence. Do not infer hidden "
            "material, origin, electronics, dimensions, or package contents unless explicitly printed or clearly visible. "
            "Each object must contain feature_id, value, confidence from 0 to 1, evidence_text, and status. "
            "Allowed status values: VISUALLY_EXPLICIT, VISUALLY_OBSERVED, NOT_DETERMINABLE. "
            f"Product page: {bundle.final_url or bundle.requested_url}\n"
            f"Visible page title: {bundle.page_title}\n"
            f"Features: {json.dumps(feature_payload, ensure_ascii=False)}"
        )
        response = self.service.predict(
            prompt,
            image=asset.local_path,
            image_detail=self.config.image_detail,
            response_format={"type": "json_object"},
            purpose="multimodal_feature_evidence",
        )
        payload = self._json_object(response.content)
        valid_ids = {feature.feature_id: feature for feature in features}
        results: list[FeatureEvidence] = []
        for item in payload.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            feature_id = str(item.get("feature_id") or "").strip()
            feature = valid_ids.get(feature_id)
            if feature is None:
                continue
            status = str(item.get("status") or "").strip().upper()
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
            value = item.get("value")
            evidence_text = str(item.get("evidence_text") or "").strip()
            if status == "NOT_DETERMINABLE" or value in {None, ""} or confidence < self.config.min_confidence:
                continue
            if feature.allowed_values and str(value) not in feature.allowed_values:
                continue
            results.append(
                FeatureEvidence(
                    feature_id=feature.feature_id,
                    feature_name=feature.feature_name,
                    source_url=bundle.final_url or bundle.requested_url,
                    value=value,
                    status=FeatureEvidenceStatus.LLM_FOUND,
                    confidence=min(confidence, 0.90),
                    evidence_text=evidence_text[:500],
                    evidence_location=f"visual_asset:{asset.asset_id}",
                    extraction_method="vision_llm",
                    notes=(
                        f"asset_id={asset.asset_id}",
                        f"acquisition_method={asset.acquisition_method.value}",
                        f"local_path={asset.local_path}",
                    ),
                )
            )
        return tuple(results)

    @staticmethod
    def _chunks(items: list[FeatureDefinition], size: int) -> Iterable[list[FeatureDefinition]]:
        size = max(1, int(size))
        for index in range(0, len(items), size):
            yield items[index:index + size]

    @staticmethod
    def _json_object(content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("Vision reasoner returned a non-object JSON response")
        return value
