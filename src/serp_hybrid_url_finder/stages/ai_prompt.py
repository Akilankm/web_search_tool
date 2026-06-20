from __future__ import annotations

import json
from dataclasses import dataclass

from serp_hybrid_url_finder.config import ProductURLPipelinePolicy
from serp_hybrid_url_finder.models import CountryContext, ProductQuery, ProductSignature, RetailerResolution


@dataclass(frozen=True)
class AIValidationPromptBuilder:
    policy: ProductURLPipelinePolicy

    def build_validation_prompt(
        self,
        *,
        product: ProductQuery,
        signature: ProductSignature,
        country: CountryContext,
        retailer: RetailerResolution,
        candidates_text: str,
    ) -> str:
        payload = {
            "role": "Validate product URL candidates using indexed web evidence. Use evidence only; do not invent URLs.",
            "task": "Choose the best exact product detail page URL, or return null when no candidate is reliable.",
            "product_input": product.to_dict(),
            "product_signature": signature.to_dict(),
            "country_context": country.to_dict(),
            "retailer_resolution": retailer.to_dict(),
            "rules": [
                "Final URL must be a single product detail page, not home/category/search/listing/social/image/document/cart/help/blog/forum.",
                "If EAN/GTIN is provided, it is the strongest identity signal. A conflicting EAN means reject.",
                "Reject wrong variants, wrong pack sizes, unrelated products, and soft-404/product-not-found pages.",
                "If retailer_name is provided, prefer the dynamically resolved retailer domain; otherwise any verified same-country market retailer is acceptable.",
                "Return JSON only, no markdown prose.",
            ],
            "candidate_urls_text": candidates_text or "NO_CANDIDATES_FOUND",
            "required_json_schema": {
                "final_url": "string or null",
                "match_decision": "EXACT | HIGH | MEDIUM | LOW | NO_MATCH",
                "confidence_reason": "string",
                "ean_evidence": "matched | absent | conflict | not_visible | not_provided",
                "title_evidence": "matched | partial | weak | unknown",
                "retailer_evidence": "matched | alternative | weak | not_provided",
                "country_evidence": "matched | likely | weak | unknown",
                "product_page_evidence": "product_detail | listing | category | homepage | search | document | unknown",
                "candidate_assessments": [
                    {
                        "url": "candidate URL",
                        "verdict": "likely_match | possible_match | reject | unknown",
                        "retailer_match": True,
                        "country_match": True,
                        "product_page_likelihood": "high | medium | low | unknown",
                        "confidence": 0.0,
                        "identity_evidence": {"title": "string", "ean": "string", "variant": "string"},
                        "rejection_reason": "string or null",
                    }
                ],
                "additional_urls": [],
                "rejected_candidates": [],
            },
        }
        return self._truncate(json.dumps(payload, ensure_ascii=False, indent=2), self.policy.ai_validation_query_max_chars)

    def build_repair_prompt(
        self,
        *,
        product: ProductQuery,
        signature: ProductSignature,
        country: CountryContext,
        retailer: RetailerResolution,
        candidates_text: str,
        previous_answer: str,
        rejection_reason: str,
    ) -> str:
        prompt = self.build_validation_prompt(
            product=product,
            signature=signature,
            country=country,
            retailer=retailer,
            candidates_text=candidates_text,
        )
        repair = {
            "repair_context": {
                "previous_ai_answer": previous_answer[:1800],
                "deterministic_rejection_reason": rejection_reason,
                "instruction": "Re-evaluate. Return a different exact product detail URL only if evidence supports it; otherwise final_url must be null and match_decision NO_MATCH.",
            }
        }
        return self._truncate(prompt + "\n" + json.dumps(repair, ensure_ascii=False, indent=2), self.policy.ai_repair_query_max_chars)

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit].rsplit("\n", 1)[0]
