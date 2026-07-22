from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from product_url_v2.models import IdentitySignal, Interpretation, ProductHypothesis, ProductInput


class ReasoningPort(Protocol):
    def refine(self, product: ProductInput, deterministic: Interpretation) -> Interpretation: ...


@dataclass(frozen=True, slots=True)
class ReasoningSettings:
    enabled: bool = False
    required: bool = False
    deployment: str = ""
    endpoint: str = ""
    api_version: str = ""
    api_key: str = ""
    consumer_id: str = ""
    timeout_seconds: int = 60
    max_retries: int = 2
    temperature: float = 0.0
    max_hypotheses: int = 5

    @classmethod
    def from_runtime(cls, config: Any) -> "ReasoningSettings":
        return cls(
            enabled=bool(config.enabled),
            required=bool(config.required),
            deployment=_first_env("PCA_LLM_DEPLOYMENT", "LLM_DEPLOYMENT", "LLM_MODEL") or str(config.deployment or ""),
            endpoint=_first_env("PCA_LLM_ENDPOINT", "LLM_ENDPOINT", "LLM_BASE_URL") or str(config.endpoint or ""),
            api_version=_first_env("PCA_LLM_API_VERSION", "LLM_API_VERSION") or str(config.api_version or ""),
            api_key=_first_env("PCA_LLM_API_KEY", "LLM_API_KEY"),
            consumer_id=_first_env("PCA_LLM_CONSUMER_ID", "LLM_CONSUMER_ID") or str(config.consumer_id or ""),
            timeout_seconds=int(config.timeout_seconds),
            max_retries=int(config.max_retries),
            temperature=float(config.temperature),
            max_hypotheses=int(config.max_hypotheses),
        )

    @property
    def default_headers(self) -> dict[str, str]:
        return {"X-NIQ-CIS-Consumer": self.consumer_id} if self.consumer_id else {}

    def validate(self) -> None:
        if not self.enabled:
            return
        missing = [
            name
            for name, value in {
                "PCA_LLM_API_KEY": self.api_key,
                "PCA_LLM_API_VERSION": self.api_version,
                "PCA_LLM_ENDPOINT": self.endpoint,
                "PCA_LLM_DEPLOYMENT": self.deployment,
            }.items()
            if not str(value or "").strip()
        ]
        if missing and self.required:
            raise RuntimeError("reasoning is required but LLM configuration is missing: " + ", ".join(missing))


@dataclass(slots=True)
class StructuredIdentityReasoner:
    settings: ReasoningSettings
    client: Any = None

    def refine(self, product: ProductInput, deterministic: Interpretation) -> Interpretation:
        if not self.settings.enabled:
            return deterministic
        self.settings.validate()
        if not all((self.settings.deployment, self.settings.endpoint, self.settings.api_version, self.settings.api_key)):
            return deterministic

        client = self.client or self._build_client()
        try:
            response = client.chat.completions.create(
                model=self.settings.deployment,
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

    def _build_client(self) -> Any:
        import httpx
        from openai import AzureOpenAI

        return AzureOpenAI(
            api_key=self.settings.api_key,
            api_version=self.settings.api_version,
            azure_endpoint=self.settings.endpoint,
            azure_deployment=self.settings.deployment,
            default_headers=self.settings.default_headers,
            max_retries=self.settings.max_retries,
            timeout=httpx.Timeout(
                connect=min(float(self.settings.timeout_seconds), 30.0),
                read=float(self.settings.timeout_seconds),
                write=float(self.settings.timeout_seconds),
                pool=float(self.settings.timeout_seconds),
            ),
        )


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
            f"L{index}",
            name,
            attrs,
            tuple(str(value) for value in item.get("negative_constraints") or [] if str(value).strip()),
            probability,
            str(item.get("rationale") or "LLM-refined interpretation"),
        ))

    if not hypotheses:
        hypotheses = list(deterministic.hypotheses)
    unknowns = tuple(dict.fromkeys([
        *deterministic.unresolved_discriminators,
        *(str(item) for item in payload.get("unknowns") or [] if str(item).strip()),
    ]))
    constraints = tuple(dict.fromkeys([
        *deterministic.negative_constraints,
        *(str(item) for item in payload.get("negative_constraints") or [] if str(item).strip()),
    ]))
    deduped = {}
    for signal in signals:
        key = (signal.field, signal.value.casefold())
        current = deduped.get(key)
        if current is None or (signal.exact, signal.confidence) > (current.exact, current.confidence):
            deduped[key] = signal
    return Interpretation(
        deterministic.normalized_text,
        tuple(deduped.values()),
        tuple(hypotheses[:max_hypotheses]),
        unknowns,
        constraints,
        deterministic.language_code,
    )


def _contains_invented_identifier(product: ProductInput, deterministic: Interpretation, attrs: Mapping[str, str]) -> bool:
    allowed = product.main_text.casefold() + " " + " ".join(item.value.casefold() for item in deterministic.signals)
    for key in ("ean", "gtin", "model", "sku", "mpn"):
        value = attrs.get(key)
        if value and value.casefold() not in allowed:
            return True
    return False


def _first_env(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""
