from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from product_url_v2.models import (
    IdentitySignal,
    Interpretation,
    ProductHypothesis,
    ProductInput,
)


_LANGUAGE_HINTS = {
    "DE": "de",
    "GERMAN": "de",
    "DEUTSCH": "de",
    "EN": "en",
    "ENGLISH": "en",
    "FR": "fr",
    "FRENCH": "fr",
    "FRANCAIS": "fr",
    "IT": "it",
    "ITALIAN": "it",
    "ES": "es",
    "SPANISH": "es",
    "JA": "ja",
    "JAPANESE": "ja",
}

_PRODUCT_FORMS = {
    "BOOSTER": "BOOSTER",
    "BOOSTERPACK": "BOOSTER_PACK",
    "BOOSTER PACK": "BOOSTER_PACK",
    "DISPLAY": "DISPLAY",
    "BUNDLE": "BUNDLE",
    "BOX": "BOX",
    "PACK": "PACK",
    "PROSPEKTHÜLLE": "DOCUMENT_SLEEVE",
    "PROSPEKTHULLE": "DOCUMENT_SLEEVE",
    "DOCUMENT SLEEVE": "DOCUMENT_SLEEVE",
    "ACTION FIGURE": "ACTION_FIGURE",
    "FIGURE": "FIGURE",
    "BUILDING SET": "BUILDING_SET",
    "PUZZLE": "PUZZLE",
    "DOLL": "DOLL",
    "GAME": "GAME",
}

_QUANTITY_WORDS = {
    "STÜCK": "COUNT",
    "STUCK": "COUNT",
    "PCS": "COUNT",
    "PIECES": "COUNT",
    "COUNT": "COUNT",
    "PACK": "PACK_COUNT",
    "PACKS": "PACK_COUNT",
}

_GENERIC_PREFIXES = {"PKM", "TCG", "NEW", "SET", "PRO", "MAX", "PLUS"}
_STOPWORDS = {
    "THE", "A", "AN", "AND", "OR", "FOR", "WITH", "OF", "IN", "ON", "BY", "TO",
    "STÜCK", "STUCK", "PCS", "PIECES", "COUNT", "PACK", "PACKS", "BOOSTER",
}


@dataclass(frozen=True, slots=True)
class DeterministicProductInterpreter:
    max_hypotheses: int = 5

    def interpret(self, product: ProductInput) -> Interpretation:
        normalized = normalize_product_text(product.main_text)
        tokens = normalized.split()
        signals: list[IdentitySignal] = []
        constraints: list[str] = []
        unresolved: list[str] = []

        if product.ean:
            signals.append(IdentitySignal("ean", product.ean, 1.0, "INPUT", product.ean, exact=True))
        for match in re.finditer(r"(?<!\d)(\d{8}|\d{12,14})(?!\d)", normalized):
            value = match.group(1)
            signals.append(IdentitySignal("ean", value, 0.98, "MAIN_TEXT", value, exact=True))

        for token in tokens:
            if _looks_like_model(token):
                signals.append(IdentitySignal("model", token, 0.93, "MAIN_TEXT", token, exact=True))

        quantity = _extract_quantity(tokens)
        if quantity:
            value, evidence = quantity
            signals.append(IdentitySignal("quantity", value, 0.95, "MAIN_TEXT", evidence, exact=True))

        size = _extract_size(normalized)
        if size:
            signals.append(IdentitySignal("size", size, 0.95, "MAIN_TEXT", size, exact=True))

        language = _detect_language(product, tokens)
        signals.append(IdentitySignal("language", language, 0.95 if product.language_code else 0.70, "INPUT" if product.language_code else "INFERENCE", language, exact=bool(product.language_code)))

        form = _detect_product_form(normalized)
        if form:
            signals.append(IdentitySignal("product_form", form, 0.88, "MAIN_TEXT", form, exact=form != "BOOSTER"))

        brand = _brand_candidate(tokens)
        if brand:
            confidence = 0.45 if brand in _GENERIC_PREFIXES or len(brand) <= 3 else 0.78
            signals.append(IdentitySignal("brand", brand, confidence, "MAIN_TEXT", brand, exact=False))
            if confidence < 0.60:
                unresolved.append("brand")

        product_name = _product_name(tokens, brand)
        if product_name:
            signals.append(IdentitySignal("product_name", product_name, 0.72, "MAIN_TEXT", product_name))

        if form == "BOOSTER":
            unresolved.append("pack_configuration")
            constraints.extend(("not booster bundle unless evidenced", "not booster display unless evidenced"))
        if form in {"BUNDLE", "DISPLAY", "BOX", "BOOSTER_PACK"}:
            signals.append(IdentitySignal("pack_configuration", form, 0.90, "MAIN_TEXT", form, exact=True))

        hypotheses = self._hypotheses(normalized, signals, form)
        if len(hypotheses) > 1 and "pack_configuration" not in unresolved:
            unresolved.append("commercial_form")
        return Interpretation(
            normalized_text=normalized,
            signals=tuple(_dedupe_signals(signals)),
            hypotheses=tuple(hypotheses[: self.max_hypotheses]),
            unresolved_discriminators=tuple(dict.fromkeys(unresolved)),
            negative_constraints=tuple(dict.fromkeys(constraints)),
            language_code=language,
        )

    def _hypotheses(
        self,
        normalized: str,
        signals: list[IdentitySignal],
        form: str | None,
    ) -> list[ProductHypothesis]:
        attrs = _strongest_attributes(signals)
        base_name = " ".join(value for value in (attrs.get("brand"), attrs.get("model"), attrs.get("product_name")) if value) or normalized
        if form == "BOOSTER":
            return [
                ProductHypothesis("H1", f"{base_name} single booster pack", attrs | {"pack_configuration": "SINGLE_PACK"}, ("bundle", "display", "box"), 0.55, "Generic booster wording most often denotes one retail pack, but is not decisive."),
                ProductHypothesis("H2", f"{base_name} booster bundle", attrs | {"pack_configuration": "BUNDLE"}, ("single pack", "display"), 0.25, "Bundle remains plausible until seller or manufacturer evidence resolves pack count."),
                ProductHypothesis("H3", f"{base_name} booster display", attrs | {"pack_configuration": "DISPLAY"}, ("single pack", "bundle"), 0.20, "Display/box is a common sibling commercial form and must be excluded explicitly."),
            ]
        return [ProductHypothesis("H1", base_name, attrs, (), 1.0, "Direct interpretation of explicit input signals.")]


def normalize_product_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("×", " X ").replace("–", "-").replace("—", "-")
    text = re.sub(r"[^\w\-./+]+", " ", text, flags=re.UNICODE)
    return " ".join(text.upper().split())


def build_search_context(product: ProductInput, interpretation: Interpretation) -> dict[str, object]:
    exact_anchors = [item.value for item in interpretation.signals if item.exact and item.field in {"ean", "model", "quantity", "size", "pack_configuration"}]
    known_facts = {item.field: item.value for item in sorted(interpretation.signals, key=lambda item: item.confidence) if item.confidence >= 0.70}
    return {
        "row_id": product.row_id,
        "submitted_text": product.main_text,
        "normalized_text": interpretation.normalized_text,
        "country_code": product.country_code,
        "retailer_name": product.retailer_name,
        "language_code": interpretation.language_code,
        "exact_anchors": list(dict.fromkeys(exact_anchors)),
        "known_facts": known_facts,
        "unresolved_discriminators": list(interpretation.unresolved_discriminators),
        "negative_constraints": list(interpretation.negative_constraints),
        "hypotheses": [
            {
                "id": item.hypothesis_id,
                "name": item.canonical_name,
                "attributes": dict(item.attributes),
                "negative_constraints": list(item.negative_constraints),
                "prior_probability": item.prior_probability,
            }
            for item in interpretation.hypotheses
        ],
    }


def _looks_like_model(token: str) -> bool:
    if len(token) < 3 or len(token) > 24:
        return False
    return bool(re.fullmatch(r"(?=.*[A-Z])(?=.*\d)[A-Z0-9][A-Z0-9._/-]*", token))


def _extract_quantity(tokens: list[str]) -> tuple[str, str] | None:
    for index, token in enumerate(tokens[:-1]):
        if token.isdigit() and tokens[index + 1] in _QUANTITY_WORDS:
            return token, f"{token} {tokens[index + 1]}"
    for token in tokens:
        match = re.fullmatch(r"(\d+)[X]", token)
        if match:
            return match.group(1), token
    return None


def _extract_size(text: str) -> str | None:
    match = re.search(r"\b(\d+(?:[.,]\d+)?)\s?(MM|CM|M|G|KG|ML|L)\b", text)
    return "".join(match.groups()).replace(",", ".") if match else None


def _detect_language(product: ProductInput, tokens: list[str]) -> str:
    if product.language_code:
        return product.language_code
    for token in tokens:
        if token in _LANGUAGE_HINTS:
            return _LANGUAGE_HINTS[token]
    return {"DE": "de", "AT": "de", "CH": "de", "FR": "fr", "IT": "it", "ES": "es", "JP": "ja"}.get(product.country_code, "en")


def _detect_product_form(text: str) -> str | None:
    for phrase, value in sorted(_PRODUCT_FORMS.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in text:
            return value
    return None


def _brand_candidate(tokens: list[str]) -> str | None:
    for token in tokens[:3]:
        if token in _STOPWORDS or token.isdigit() or _looks_like_model(token):
            continue
        if len(token) >= 2:
            return token
    return None


def _product_name(tokens: list[str], brand: str | None) -> str:
    values = [token for token in tokens if token not in _STOPWORDS and token != brand and not token.isdigit() and not _looks_like_model(token)]
    return " ".join(values[:8])


def _strongest_attributes(signals: list[IdentitySignal]) -> dict[str, str]:
    output: dict[str, IdentitySignal] = {}
    for item in signals:
        current = output.get(item.field)
        if current is None or (item.exact, item.confidence) > (current.exact, current.confidence):
            output[item.field] = item
    return {key: item.value for key, item in output.items()}


def _dedupe_signals(signals: list[IdentitySignal]) -> list[IdentitySignal]:
    output: dict[tuple[str, str], IdentitySignal] = {}
    for item in signals:
        key = (item.field, item.value)
        current = output.get(key)
        if current is None or (item.exact, item.confidence) > (current.exact, current.confidence):
            output[key] = item
    return list(output.values())
