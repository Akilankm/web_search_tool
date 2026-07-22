from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


from product_url_v2.models import IdentitySignal, Interpretation, ProductHypothesis, ProductInput


class ReasoningPort(Protocol):
    def refine(self, product: ProductInput, deterministic: Interpretation) -> Interpretation: ...


@dataclass(frozen=True, slots=True)
class ReasoningSettings:
    enabled: bool = False
    required: bool = False
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout_seconds: int = 60
    temperature: float = 0.0
    max_hypotheses: int = 5


@dataclass(slots=True)
class StructuredIdentityReasoner:
    settings: ReasoningSettings
    client: Any = None

    def refine(self, product: ProductInput, deterministic: Interpretation) -> Interpretation:
        if not self.settings.enabled:
            return deterministic
        if not self.settings.model or not self.settings.api_key:
            if self.settings.required:
                raise RuntimeError("reasoning is required but LLM_MODEL or LLM_API_KEY is missing")
            return deterministic
        if self.client is not None:
            client = self.client
        else:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.settings.api_key,
                base_url=self.settings.base_url or None,
                timeout=self.settings.timeout_seconds,
            )
        try:
            response = client.chat.completions.create(
                model=self.settings.model,
                temperature=self.settings.temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(_payload(product, deterministic), ensure_ascii=False)},
                ],
            )
            raw = response.choices[0].message.content or "{}"
            payload = json.loads(raw)
            return _merge(product, deterministic, payload, self.settings.max_hypotheses)
        except Exception:
            if self.settings.required:
                raise
            return deterministic


_SYSTEM_PROMPT = """You are a product-identity hypothesis builder. You have no internet access. Separate observed facts, assumptions and unknowns. Preserve every exact identifier from the input. Never invent EAN/GTIN, model codes, pack counts, retailer names or URLs. Generic terms such as booster must retain plausible sibling commercial forms. Return one JSON object with: facts [{field,value,confidence,evidence}], unknowns [string], negative_constraints [string], hypotheses [{name,attributes,negative_constraints,probability,rationale}]. Probabilities must be between 0 and 1. Use concise values."""


def _payload(product: ProductInput, deterministic: Interpretation) -> dict[str, Any]:
    return {
        "input": {
            "main_text": product.main_text,
            "country_code": product.country_code,
            "retailer_name": product.retailer_name,
            "ean": product.ean,
            "language_code": product.language_code,
        },
        "deterministic_facts": [
            {"field": item.field, "value": item.value, "confidence": item.confidence, "exact": item.exact, "evidence": item.evidence}
            for item in deterministic.signals
        ],
        "deterministic_unknowns": list(deterministic.unresolved_discriminators),
        "deterministic_hypotheses": [
            {"name": item.canonical_name, "attributes": dict(item.attributes), "negative_constraints": list(item.negative_constraints), "probability": item.prior_probability}
            for item in deterministic.hypotheses
        ],
    }


def _merge(product: ProductInput, deterministic: Interpretation, payload: Mapping[str, Any], max_hypotheses: int) -> Interpretation:
    signals = list(deterministic.signals)
    source_text = product.main_text.casefold()
    for item in payload.get("facts") or []:
        if not isinstance(item, Mapping):
            continue
        field = str(item.get("field") or "").strip().lower()
        value = " ".join(str(item.get("value") or "").split())
        evidence = " ".join(str(item.get("evidence") or value).split())
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.5)))
        except (TypeError, ValueError, OverflowError):
            confidence = 0.5
        if not field or not value:
            continue
        if field in {"ean", "gtin", "model", "sku", "mpn"} and value.casefold() not in source_text:
            continue
        signals.append(IdentitySignal(field, value, min(confidence, 0.85), "LLM_INFERENCE", evidence, exact=False))
    hypotheses: list[ProductHypothesis] = []
    for index, item in enumerate(payload.get("hypotheses") or [], start=1):
        if not isinstance(item, Mapping):
            continue
        name = " ".join(str(item.get("name") or "").split())
        attrs = item.get("attributes") if isinstance(item.get("attributes"), Mapping) else {}
        attrs = {str(key): " ".join(str(value).split()) for key, value in attrs.items() if str(value).strip()}
        if not name or _contains_invented_identifier(product, deterministic, attrs):
            continue
        try:
            probability = max(0.0, min(1.0, float(item.get("probability") or 0.0)))
        except (TypeError, ValueError, OverflowError):
            probability = 0.0
        hypotheses.append(ProductHypothesis(
            f"L{index}", name, attrs,
            tuple(str(value) for value in item.get("negative_constraints") or [] if str(value).strip()),
            probability,
            str(item.get("rationale") or "LLM-refined interpretation"),
        ))
    if not hypotheses:
        hypotheses = list(deterministic.hypotheses)
    unknowns = tuple(dict.fromkeys([*deterministic.unresolved_discriminators, *(str(item) for item in payload.get("unknowns") or [] if str(item).strip())]))
    constraints = tuple(dict.fromkeys([*deterministic.negative_constraints, *(str(item) for item in payload.get("negative_constraints") or [] if str(item).strip())]))
    deduped = {}
    for signal in signals:
        key = (signal.field, signal.value.casefold())
        current = deduped.get(key)
        if current is None or (signal.exact, signal.confidence) > (current.exact, current.confidence):
            deduped[key] = signal
    return Interpretation(deterministic.normalized_text, tuple(deduped.values()), tuple(hypotheses[:max_hypotheses]), unknowns, constraints, deterministic.language_code)


def _contains_invented_identifier(product: ProductInput, deterministic: Interpretation, attrs: Mapping[str, str]) -> bool:
    allowed = product.main_text.casefold() + " " + " ".join(item.value.casefold() for item in deterministic.signals)
    for key in ("ean", "gtin", "model", "sku", "mpn"):
        value = attrs.get(key)
        if value and value.casefold() not in allowed:
            return True
    return False
