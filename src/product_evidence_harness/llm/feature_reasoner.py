from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Sequence

from loguru import logger

from src.product_evidence_harness.contracts import ProductQuery, ScrapeResult
from src.product_evidence_harness.feature_schema import (
    FeatureDefinition,
    FeatureEvidence,
    FeatureEvidenceStatus,
    FeatureSchema,
)
from src.product_evidence_harness.llm.service import LLMService


@dataclass
class LLMFeatureReasoner:
    """Post-scrape LLM evidence extraction with strict grounding controls.

    The reasoner cannot search, fetch URLs, or override product-identity rejection.
    It is called only by ``FeatureAwareEvidenceExtractor`` after a URL has passed
    deterministic identity acceptance. Returned evidence is accepted only when the
    cited quote is present in the scraped page text and all feature/value constraints
    are satisfied.
    """

    service: LLMService
    max_calls: int = 2
    max_context_chars: int = 16_000
    _calls: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def from_env(cls, *, max_calls: int = 2) -> "LLMFeatureReasoner":
        return cls(service=LLMService(), max_calls=max(0, min(int(max_calls), 4)))

    def evaluate(
        self,
        *,
        product: ProductQuery,
        schema: FeatureSchema,
        scrape: ScrapeResult,
        deterministic_evidence: Sequence[FeatureEvidence],
    ) -> Sequence[FeatureEvidence]:
        missing_ids = {item.feature_id for item in deterministic_evidence if not item.supported}
        features = [feature for feature in schema.features if feature.feature_id in missing_ids]
        if not features:
            return ()

        page_text = self._page_text(scrape)
        if not page_text or not self._consume_call():
            return ()

        prompt = self._build_prompt(product, scrape, features, page_text)
        try:
            response = self.service.predict(
                prompt,
                system_prompt=(
                    "You extract product feature evidence from the supplied page text only. "
                    "Do not browse, infer, guess, use world knowledge, or follow URLs. "
                    "Return strict JSON matching the requested schema."
                ),
                response_format={"type": "json_object"},
                temperature=0.0,
                purpose="post_scrape_feature_evidence",
            )
        except Exception as exc:
            # Optional reasoning must never weaken deterministic evidence or abort the
            # product workflow. Fail closed: accept no LLM evidence and keep the item
            # in feature review.
            logger.warning(
                "Optional LLM feature reasoning unavailable | error_type={} | url={}",
                type(exc).__name__,
                scrape.final_url or scrape.url,
            )
            return ()
        return self._validated_evidence(response.content, schema, scrape, page_text, missing_ids)

    def _consume_call(self) -> bool:
        with self._lock:
            if self._calls >= self.max_calls:
                return False
            self._calls += 1
            return True

    def _build_prompt(
        self,
        product: ProductQuery,
        scrape: ScrapeResult,
        features: Sequence[FeatureDefinition],
        page_text: str,
    ) -> str:
        feature_payload = [
            {
                "feature_id": feature.feature_id,
                "feature_name": feature.feature_name,
                "value_type": feature.value_type,
                "allowed_values": list(feature.allowed_values),
                "description": feature.description,
            }
            for feature in features
        ]
        return json.dumps(
            {
                "task": "Extract only explicitly supported feature values from PAGE_TEXT.",
                "rules": [
                    "Return one result only when an exact supporting quote exists in PAGE_TEXT.",
                    "evidence_quote must be copied verbatim from PAGE_TEXT.",
                    "Do not return a value inferred from product category, image, brand knowledge, or common sense.",
                    "For closed-set features, value must exactly match one allowed_values entry.",
                    "Omit unsupported features rather than guessing.",
                    "Output: {\"features\":[{\"feature_id\":str,\"value\":any,\"evidence_quote\":str,\"confidence\":number}]}",
                ],
                "product_identity": {
                    "main_text": product.main_text,
                    "ean": product.ean or "",
                    "country_code": product.country_code,
                },
                "requested_features": feature_payload,
                "page_url": scrape.final_url or scrape.url,
                "PAGE_TEXT": page_text,
            },
            ensure_ascii=False,
        )

    def _validated_evidence(
        self,
        content: str,
        schema: FeatureSchema,
        scrape: ScrapeResult,
        page_text: str,
        allowed_feature_ids: set[str],
    ) -> tuple[FeatureEvidence, ...]:
        try:
            payload = json.loads(content or "{}")
        except json.JSONDecodeError:
            logger.warning("Discarding non-JSON LLM feature response")
            return ()

        records = payload.get("features", []) if isinstance(payload, dict) else []
        if not isinstance(records, list):
            return ()

        definitions = {feature.feature_id: feature for feature in schema.features}
        folded_page = self._fold(page_text)
        accepted: list[FeatureEvidence] = []
        seen: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                continue
            feature_id = str(record.get("feature_id") or "").strip()
            if feature_id in seen or feature_id not in allowed_feature_ids or feature_id not in definitions:
                continue
            definition = definitions[feature_id]
            quote = str(record.get("evidence_quote") or "").strip()
            value = record.get("value")
            if not quote or len(quote) > 800 or self._fold(quote) not in folded_page:
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if definition.allowed_values:
                matched = next(
                    (candidate for candidate in definition.allowed_values if self._fold(candidate) == self._fold(value)),
                    None,
                )
                if matched is None:
                    continue
                value = matched
            try:
                confidence = float(record.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue
            confidence = max(0.0, min(0.75, confidence))
            if confidence < 0.50:
                continue

            accepted.append(
                FeatureEvidence(
                    feature_id=feature_id,
                    feature_name=definition.feature_name,
                    source_url=scrape.final_url or scrape.url,
                    value=value,
                    status=FeatureEvidenceStatus.LLM_FOUND,
                    confidence=confidence,
                    evidence_text=quote,
                    evidence_location="scraped_page_text",
                    extraction_method="llm_grounded_post_scrape",
                    notes=("LLM evidence accepted only after exact quote verification.",),
                )
            )
            seen.add(feature_id)
        return tuple(accepted)

    def _page_text(self, scrape: ScrapeResult) -> str:
        chunks = [
            scrape.page_product_name,
            scrape.title,
            scrape.description,
            scrape.markdown_excerpt,
            scrape.verification_text,
            "\n".join(f"{key}: {value}" for key, value in (scrape.specs or {}).items()),
        ]
        text = "\n".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[: self.max_context_chars]

    @staticmethod
    def _fold(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().casefold()
