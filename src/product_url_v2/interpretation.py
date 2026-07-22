from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from product_url_v2.contracts import ProductHypothesis, ProductInput


class SignalField(str, Enum):
    EAN = "EAN"
    BRAND = "BRAND"
    MODEL = "MODEL"
    SERIES = "SERIES"
    PRODUCT_FORM = "PRODUCT_FORM"
    PACK_CONFIGURATION = "PACK_CONFIGURATION"
    QUANTITY = "QUANTITY"
    SIZE = "SIZE"
    LANGUAGE = "LANGUAGE"
    VARIANT = "VARIANT"


class SignalSource(str, Enum):
    PROVIDED_INPUT = "PROVIDED_INPUT"
    DETERMINISTIC_TEXT = "DETERMINISTIC_TEXT"
    LLM_INFERENCE = "LLM_INFERENCE"


class ProductForm(str, Enum):
    BOOSTER = "BOOSTER"
    BOOSTER_PACK = "BOOSTER_PACK"
    BOOSTER_BUNDLE = "BOOSTER_BUNDLE"
    BOOSTER_DISPLAY = "BOOSTER_DISPLAY"
    BOX = "BOX"
    CASE = "CASE"
    SET = "SET"
    PACK = "PACK"
    DOCUMENT_SLEEVE = "DOCUMENT_SLEEVE"
    FOLDER = "FOLDER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class IdentitySignal:
    field: SignalField
    raw_value: str
    normalized_value: str
    confidence: float
    source: SignalSource
    evidence_span: str

    def __post_init__(self) -> None:
        if not self.raw_value.strip():
            raise ValueError("raw_value is required")
        if not self.normalized_value.strip():
            raise ValueError("normalized_value is required")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class IdentityUncertainty:
    key: str
    question: str
    candidate_values: tuple[str, ...]
    severity: float
    reason: str

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("uncertainty key is required")
        if not self.question.strip():
            raise ValueError("uncertainty question is required")
        if not 0.0 <= float(self.severity) <= 1.0:
            raise ValueError("severity must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class InterpretationResult:
    product: ProductInput
    normalized_text: str
    signals: tuple[IdentitySignal, ...]
    uncertainties: tuple[IdentityUncertainty, ...]
    hypotheses: tuple[ProductHypothesis, ...]
    exact_anchors: tuple[str, ...]
    negative_search_terms: tuple[str, ...]

    def signals_for(self, field: SignalField) -> tuple[IdentitySignal, ...]:
        return tuple(item for item in self.signals if item.field is field)

    def strongest_signal(self, field: SignalField) -> IdentitySignal | None:
        values = self.signals_for(field)
        return max(values, key=lambda item: item.confidence) if values else None


@dataclass(frozen=True, slots=True)
class SearchContextPacket:
    exact_anchors: tuple[str, ...]
    known_facts: tuple[tuple[str, str], ...]
    unresolved_discriminators: tuple[str, ...]
    excluded_interpretations: tuple[str, ...]
    hypothesis_summaries: tuple[str, ...]
    country_code: str
    language_code: str | None
    requested_retailer: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "exact_anchors": list(self.exact_anchors),
            "known_facts": [
                {"field": field, "value": value}
                for field, value in self.known_facts
            ],
            "unresolved_discriminators": list(self.unresolved_discriminators),
            "excluded_interpretations": list(self.excluded_interpretations),
            "hypothesis_summaries": list(self.hypothesis_summaries),
            "country_code": self.country_code,
            "language_code": self.language_code,
            "requested_retailer": self.requested_retailer,
        }


class StructuredIdentityReasoner(Protocol):
    """Optional structured reasoner port used by a later LLM adapter."""

    def infer_identity(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


_FORM_PATTERNS: tuple[tuple[re.Pattern[str], ProductForm, float], ...] = (
    (
        re.compile(r"\b(?:PROSPEKTH[ÜU]LLE|SICHTH[ÜU]LLE|DOCUMENT\s+SLEEVE)\b", re.I),
        ProductForm.DOCUMENT_SLEEVE,
        0.98,
    ),
    (
        re.compile(r"\b(?:BOOSTER\s+BUNDLE|BUNDLE)\b", re.I),
        ProductForm.BOOSTER_BUNDLE,
        0.98,
    ),
    (
        re.compile(r"\b(?:BOOSTER\s+DISPLAY|DISPLAY)\b", re.I),
        ProductForm.BOOSTER_DISPLAY,
        0.98,
    ),
    (
        re.compile(r"\b(?:BOOSTER\s+PACK|BOOSTERPACK)\b", re.I),
        ProductForm.BOOSTER_PACK,
        0.97,
    ),
    (re.compile(r"\bBOOSTER\b", re.I), ProductForm.BOOSTER, 0.86),
    (re.compile(r"\b(?:BOX|SCHACHTEL)\b", re.I), ProductForm.BOX, 0.88),
    (re.compile(r"\b(?:CASE|KARTON)\b", re.I), ProductForm.CASE, 0.86),
    (re.compile(r"\b(?:SET|KIT)\b", re.I), ProductForm.SET, 0.82),
    (re.compile(r"\b(?:PACK|PKG|PACKUNG)\b", re.I), ProductForm.PACK, 0.78),
    (re.compile(r"\b(?:FOLDER|ORDNER|MAPPE)\b", re.I), ProductForm.FOLDER, 0.86),
)
_LANGUAGE_TERMS = {
    "DE": ("DE", "DEUTSCH", "GERMAN"),
    "EN": ("EN", "ENGLISH", "ANGLAIS"),
    "FR": ("FR", "FRANCAIS", "FRANÇAIS", "FRENCH"),
    "IT": ("IT", "ITALIANO", "ITALIAN"),
    "ES": ("ES", "ESPANOL", "ESPAÑOL", "SPANISH"),
    "NL": ("NL", "NEDERLANDS", "DUTCH"),
    "JA": ("JA", "JAPANESE", "JAPANISCH"),
}
_GENERIC_PREFIXES = {
    "NEW",
    "THE",
    "PACK",
    "BOX",
    "SET",
    "BOOSTER",
    "RECYCLE",
    "PRODUKT",
    "PRODUCT",
}
_QUANTITY_RE = re.compile(
    r"(?<!\d)(\d{1,4})\s*(?:ST[ÜU]CK|STK\.?|PCS?\.?|PIECES?|COUNT|CT\.?)(?![A-Z0-9])",
    re.I,
)
_PACK_QUANTITY_RE = re.compile(
    r"(?<!\d)(\d{1,4})\s*(?:ER\s*)?(?:PACK|PACKUNG|BOOSTER|SLEEVES?)(?![A-Z0-9])",
    re.I,
)
_MULTIPLIER_RE = re.compile(r"(?:^|\s)[X×]\s*(\d{1,4})(?:\s|$)", re.I)
_SIZE_RE = re.compile(
    r"(?<![A-Z0-9])(\d+(?:[.,]\d+)?)\s*(MM|CM|M|ML|CL|L|G|KG)(?![A-Z])",
    re.I,
)
_MODEL_RE = re.compile(
    r"\b(?=[A-Z0-9-]{3,20}\b)(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)*\b"
)
_STANDALONE_GTIN_RE = re.compile(r"(?<!\d)(\d{8}|\d{12}|\d{13}|\d{14})(?!\d)")
_TOKEN_RE = re.compile(r"[A-ZÀ-ÖØ-Þ0-9][A-ZÀ-ÖØ-Þ0-9&+._'-]*", re.I)


def normalize_product_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = normalized.replace("\u00a0", " ")
    return " ".join(normalized.split())


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _valid_gtin(value: str | None) -> str | None:
    digits = _digits(value)
    return digits if len(digits) in {8, 12, 13, 14} else None


class DeterministicProductInterpreter:
    """Conservative multilingual interpretation before any paid search.

    The interpreter extracts explicit anchors and creates hypotheses. It does not
    claim that heuristic brand or product-form signals are verified facts.
    """

    def interpret(self, product: ProductInput) -> InterpretationResult:
        text = normalize_product_text(product.main_text)
        upper = text.upper()
        signals: list[IdentitySignal] = []
        uncertainties: list[IdentityUncertainty] = []

        provided_gtin = _valid_gtin(product.ean)
        if provided_gtin:
            signals.append(
                IdentitySignal(
                    field=SignalField.EAN,
                    raw_value=str(product.ean),
                    normalized_value=provided_gtin,
                    confidence=1.0,
                    source=SignalSource.PROVIDED_INPUT,
                    evidence_span=str(product.ean),
                )
            )
        for match in _STANDALONE_GTIN_RE.finditer(upper):
            value = match.group(1)
            if value != provided_gtin:
                signals.append(
                    IdentitySignal(
                        field=SignalField.EAN,
                        raw_value=value,
                        normalized_value=value,
                        confidence=0.96,
                        source=SignalSource.DETERMINISTIC_TEXT,
                        evidence_span=match.group(0),
                    )
                )

        quantity_match = _QUANTITY_RE.search(upper)
        if quantity_match is None:
            quantity_match = _PACK_QUANTITY_RE.search(upper)
        if quantity_match is None:
            quantity_match = _MULTIPLIER_RE.search(upper)
        if quantity_match:
            quantity = str(int(quantity_match.group(1)))
            signals.append(
                IdentitySignal(
                    field=SignalField.QUANTITY,
                    raw_value=quantity_match.group(0),
                    normalized_value=quantity,
                    confidence=0.96,
                    source=SignalSource.DETERMINISTIC_TEXT,
                    evidence_span=quantity_match.group(0),
                )
            )

        for match in _SIZE_RE.finditer(upper):
            number = match.group(1).replace(",", ".")
            unit = match.group(2).upper()
            signals.append(
                IdentitySignal(
                    field=SignalField.SIZE,
                    raw_value=match.group(0),
                    normalized_value=f"{number} {unit}",
                    confidence=0.94,
                    source=SignalSource.DETERMINISTIC_TEXT,
                    evidence_span=match.group(0),
                )
            )

        ean_values = {
            item.normalized_value for item in signals if item.field is SignalField.EAN
        }
        quantity_values = {
            item.normalized_value
            for item in signals
            if item.field is SignalField.QUANTITY
        }
        for match in _MODEL_RE.finditer(upper):
            value = match.group(0)
            if value in ean_values or value in quantity_values:
                continue
            signals.append(
                IdentitySignal(
                    field=SignalField.MODEL,
                    raw_value=value,
                    normalized_value=value,
                    confidence=0.91,
                    source=SignalSource.DETERMINISTIC_TEXT,
                    evidence_span=value,
                )
            )

        matched_forms: list[IdentitySignal] = []
        for pattern, product_form, confidence in _FORM_PATTERNS:
            match = pattern.search(upper)
            if not match:
                continue
            signal = IdentitySignal(
                field=SignalField.PRODUCT_FORM,
                raw_value=match.group(0),
                normalized_value=product_form.value,
                confidence=confidence,
                source=SignalSource.DETERMINISTIC_TEXT,
                evidence_span=match.group(0),
            )
            matched_forms.append(signal)
        if matched_forms:
            strongest_form = max(matched_forms, key=lambda item: item.confidence)
            signals.append(strongest_form)

        if product.language_code:
            signals.append(
                IdentitySignal(
                    field=SignalField.LANGUAGE,
                    raw_value=product.language_code,
                    normalized_value=product.language_code.upper(),
                    confidence=0.90,
                    source=SignalSource.PROVIDED_INPUT,
                    evidence_span=product.language_code,
                )
            )
        for language, terms in _LANGUAGE_TERMS.items():
            term = next(
                (
                    candidate
                    for candidate in terms
                    if re.search(rf"\b{re.escape(candidate)}\b", upper)
                ),
                None,
            )
            if term:
                signals.append(
                    IdentitySignal(
                        field=SignalField.LANGUAGE,
                        raw_value=term,
                        normalized_value=language,
                        confidence=0.88,
                        source=SignalSource.DETERMINISTIC_TEXT,
                        evidence_span=term,
                    )
                )

        tokens = _TOKEN_RE.findall(text)
        if tokens:
            prefix = tokens[0]
            prefix_upper = prefix.upper()
            if (
                prefix_upper not in _GENERIC_PREFIXES
                and prefix.isupper()
                and prefix.isalpha()
                and 2 <= len(prefix) <= 24
            ):
                confidence = 0.72 if len(prefix) >= 4 else 0.48
                signals.append(
                    IdentitySignal(
                        field=SignalField.BRAND,
                        raw_value=prefix,
                        normalized_value=prefix_upper,
                        confidence=confidence,
                        source=SignalSource.DETERMINISTIC_TEXT,
                        evidence_span=prefix,
                    )
                )
                if confidence < 0.60:
                    uncertainties.append(
                        IdentityUncertainty(
                            key="brand_or_prefix",
                            question="Is the leading abbreviation the brand, retailer prefix, or product-family code?",
                            candidate_values=(prefix_upper, "UNKNOWN"),
                            severity=0.55,
                            reason="Short uppercase prefixes are not reliable brand evidence.",
                        )
                    )

        signals = self._deduplicate_signals(signals)
        hypotheses, form_uncertainties, negative_terms = HypothesisBuilder().build(
            product,
            text,
            tuple(signals),
        )
        uncertainties.extend(form_uncertainties)
        exact_anchors = self._exact_anchors(product, signals)
        return InterpretationResult(
            product=product,
            normalized_text=text,
            signals=tuple(signals),
            uncertainties=tuple(uncertainties),
            hypotheses=hypotheses,
            exact_anchors=exact_anchors,
            negative_search_terms=negative_terms,
        )

    @staticmethod
    def _deduplicate_signals(signals: Sequence[IdentitySignal]) -> list[IdentitySignal]:
        by_key: dict[tuple[SignalField, str], IdentitySignal] = {}
        for signal in signals:
            key = (signal.field, signal.normalized_value)
            current = by_key.get(key)
            if current is None or signal.confidence > current.confidence:
                by_key[key] = signal
        return sorted(
            by_key.values(),
            key=lambda item: (item.field.value, -item.confidence, item.normalized_value),
        )

    @staticmethod
    def _exact_anchors(
        product: ProductInput,
        signals: Sequence[IdentitySignal],
    ) -> tuple[str, ...]:
        anchors: list[str] = []
        for field in (SignalField.EAN, SignalField.MODEL):
            anchors.extend(
                signal.normalized_value
                for signal in signals
                if signal.field is field and signal.confidence >= 0.85
            )
        if product.retailer_name:
            anchors.append(product.retailer_name)
        return tuple(dict.fromkeys(value for value in anchors if value))


class HypothesisBuilder:
    def build(
        self,
        product: ProductInput,
        normalized_text: str,
        signals: Sequence[IdentitySignal],
    ) -> tuple[
        tuple[ProductHypothesis, ...],
        tuple[IdentityUncertainty, ...],
        tuple[str, ...],
    ]:
        attributes = self._strongest_attributes(signals)
        form = attributes.get(SignalField.PRODUCT_FORM.value)
        quantity = attributes.get(SignalField.QUANTITY.value)
        uncertainties: list[IdentityUncertainty] = []
        negative_terms: list[str] = []

        if form == ProductForm.BOOSTER.value:
            uncertainties.append(
                IdentityUncertainty(
                    key="booster_pack_configuration",
                    question="Is this a single booster pack, multi-pack bundle, or sealed display?",
                    candidate_values=(
                        ProductForm.BOOSTER_PACK.value,
                        ProductForm.BOOSTER_BUNDLE.value,
                        ProductForm.BOOSTER_DISPLAY.value,
                    ),
                    severity=0.95,
                    reason=(
                        "The generic word BOOSTER identifies the family but not the commercial pack configuration."
                    ),
                )
            )
            negative_terms.extend(("bundle", "display", "box"))
            hypotheses = (
                self._hypothesis(
                    "H1",
                    normalized_text,
                    attributes,
                    ProductForm.BOOSTER_PACK,
                    0.58,
                    ("not booster bundle", "not booster display"),
                ),
                self._hypothesis(
                    "H2",
                    normalized_text,
                    attributes,
                    ProductForm.BOOSTER_BUNDLE,
                    0.22,
                    ("not single booster pack", "not booster display"),
                ),
                self._hypothesis(
                    "H3",
                    normalized_text,
                    attributes,
                    ProductForm.BOOSTER_DISPLAY,
                    0.20,
                    ("not single booster pack", "not booster bundle"),
                ),
            )
            return hypotheses, tuple(uncertainties), tuple(negative_terms)

        confidence = 0.88 if form and quantity else 0.76 if form else 0.62
        hypothesis = ProductHypothesis(
            hypothesis_id="H1",
            canonical_name=normalized_text,
            attributes=tuple(sorted(attributes.items())),
            negative_constraints=(),
            posterior_probability=confidence,
        )
        return (hypothesis,), tuple(uncertainties), tuple(negative_terms)

    @staticmethod
    def _strongest_attributes(
        signals: Sequence[IdentitySignal],
    ) -> dict[str, str]:
        strongest: dict[SignalField, IdentitySignal] = {}
        for signal in signals:
            current = strongest.get(signal.field)
            if current is None or signal.confidence > current.confidence:
                strongest[signal.field] = signal
        return {
            field.value: signal.normalized_value
            for field, signal in strongest.items()
        }

    @staticmethod
    def _hypothesis(
        hypothesis_id: str,
        canonical_name: str,
        base_attributes: Mapping[str, str],
        product_form: ProductForm,
        probability: float,
        negative_constraints: tuple[str, ...],
    ) -> ProductHypothesis:
        attributes = dict(base_attributes)
        attributes[SignalField.PACK_CONFIGURATION.value] = product_form.value
        return ProductHypothesis(
            hypothesis_id=hypothesis_id,
            canonical_name=canonical_name,
            attributes=tuple(sorted(attributes.items())),
            negative_constraints=negative_constraints,
            posterior_probability=probability,
        )


class IdentityReasoningContract:
    """Build the strict payload expected by a later reasoning-model adapter."""

    @staticmethod
    def request_payload(result: InterpretationResult) -> dict[str, Any]:
        return {
            "objective": (
                "Resolve the commercial product identity before web search. Separate explicit facts, "
                "reasonable assumptions, unresolved discriminators, and negative constraints."
            ),
            "product_input": {
                "main_text": result.product.main_text,
                "country_code": result.product.country_code,
                "retailer_name": result.product.retailer_name,
                "ean": result.product.ean,
                "language_code": result.product.language_code,
            },
            "deterministic_signals": [
                {
                    "field": signal.field.value,
                    "value": signal.normalized_value,
                    "confidence": signal.confidence,
                    "source": signal.source.value,
                    "evidence_span": signal.evidence_span,
                }
                for signal in result.signals
            ],
            "current_hypotheses": [
                {
                    "hypothesis_id": item.hypothesis_id,
                    "canonical_name": item.canonical_name,
                    "attributes": dict(item.attributes),
                    "negative_constraints": list(item.negative_constraints),
                    "posterior_probability": item.posterior_probability,
                }
                for item in result.hypotheses
            ],
            "current_uncertainties": [
                {
                    "key": item.key,
                    "question": item.question,
                    "candidate_values": list(item.candidate_values),
                    "severity": item.severity,
                    "reason": item.reason,
                }
                for item in result.uncertainties
            ],
            "rules": [
                "Do not invent EAN, model, brand, retailer, language, quantity, size or pack configuration.",
                "A short uppercase prefix is not automatically a verified brand.",
                "Keep sibling variants and pack configurations as competing hypotheses until evidence separates them.",
                "Return explicit discriminators that the next search action should resolve.",
                "Facts, assumptions and unknowns must be separate.",
            ],
            "output_schema": {
                "signals": [
                    {
                        "field": "one supported identity field",
                        "value": "normalized value",
                        "status": "FACT|ASSUMPTION|UNKNOWN",
                        "confidence": "0..1",
                        "evidence": "input span or null",
                    }
                ],
                "hypotheses": [
                    {
                        "hypothesis_id": "H#",
                        "canonical_name": "commercial product identity",
                        "attributes": {"field": "value"},
                        "negative_constraints": ["not ..."],
                        "posterior_probability": "0..1",
                    }
                ],
                "unresolved_discriminators": ["specific question"],
                "recommended_search_anchors": ["exact terms"],
                "negative_search_terms": ["term"],
            },
        }


def build_search_context(result: InterpretationResult) -> SearchContextPacket:
    strongest: dict[SignalField, IdentitySignal] = {}
    for signal in result.signals:
        current = strongest.get(signal.field)
        if current is None or signal.confidence > current.confidence:
            strongest[signal.field] = signal
    known_facts = tuple(
        sorted(
            (
                field.value,
                signal.normalized_value,
            )
            for field, signal in strongest.items()
            if signal.confidence >= 0.70
        )
    )
    return SearchContextPacket(
        exact_anchors=result.exact_anchors,
        known_facts=known_facts,
        unresolved_discriminators=tuple(
            item.question for item in sorted(
                result.uncertainties,
                key=lambda value: value.severity,
                reverse=True,
            )
        ),
        excluded_interpretations=tuple(
            dict.fromkeys(
                constraint
                for hypothesis in result.hypotheses
                for constraint in hypothesis.negative_constraints
            )
        ),
        hypothesis_summaries=tuple(
            f"{item.hypothesis_id}: {dict(item.attributes)} | p={item.posterior_probability:.2f}"
            for item in result.hypotheses
        ),
        country_code=result.product.country_code,
        language_code=result.product.language_code,
        requested_retailer=result.product.retailer_name,
    )
