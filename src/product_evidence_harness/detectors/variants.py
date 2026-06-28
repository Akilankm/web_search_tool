from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from src.product_evidence_harness.identity.graph import PRODUCT_FORM_FAMILIES, ProductIdentityGraph, ProductIdentityGraphBuilder
from src.product_evidence_harness.identity.normalizer import fold_text


@dataclass(frozen=True)
class DetectorFinding:
    detector: str
    status: str
    severity: str
    input_value: str = ""
    page_value: str = ""
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "detector": self.detector,
            "status": self.status,
            "severity": self.severity,
            "input_value": self.input_value,
            "page_value": self.page_value,
            "explanation": self.explanation,
        }


class VariantConflictDetector:
    """Generic exact-product conflict detector.

    This is intentionally category-extensible: it detects attribute conflicts
    (size/format, color, quantity, language/edition, product form) rather than
    hardcoding individual products or retailers.
    """

    def __init__(self) -> None:
        self.builder = ProductIdentityGraphBuilder()

    def analyze(self, identity: ProductIdentityGraph, page_text: str) -> list[DetectorFinding]:
        page_identity = self.builder.build(_PseudoQuery(page_text, identity.country_code, identity.input_ean, identity.retailer_constraint))
        findings: list[DetectorFinding] = []
        findings.extend(self._compare_sets("size_format_detector", identity.size_terms, page_identity.size_terms, hard=True))
        findings.extend(self._compare_sets("color_detector", identity.color_terms, page_identity.color_terms, hard=True))
        findings.extend(self._compare_sets("quantity_detector", identity.quantity_terms, page_identity.quantity_terms, hard=True))
        findings.extend(self._compare_sets("language_edition_detector", identity.language_or_edition_terms, page_identity.language_or_edition_terms, hard=True))
        findings.extend(self._compare_model_terms(identity, page_identity, page_text))
        findings.extend(self._compare_product_form(identity, page_identity))
        findings.extend(self._negative_terms(identity, page_text))
        findings.extend(self._must_terms(identity, page_text))
        return findings

    def has_hard_conflict(self, findings: Iterable[DetectorFinding]) -> bool:
        return any(f.status == "CONFLICT" and f.severity == "HARD_BLOCKER" for f in findings)

    def conflict_labels(self, findings: Iterable[DetectorFinding]) -> tuple[str, ...]:
        labels = []
        for f in findings:
            if f.status == "CONFLICT":
                labels.append(f"{f.detector}:{f.input_value}_vs_{f.page_value}".replace(" ", "_"))
        return tuple(dict.fromkeys(labels))

    def _compare_sets(self, detector: str, requested: tuple[str, ...], page: tuple[str, ...], *, hard: bool) -> list[DetectorFinding]:
        if not requested:
            return []
        if not page:
            return [DetectorFinding(detector, "MISSING_ON_PAGE", "WARNING", "|".join(requested), "", f"Requested {detector} evidence not found on page.")]
        req = {fold_text(x) for x in requested}
        pg = {fold_text(x) for x in page}
        if req & pg:
            return [DetectorFinding(detector, "MATCHED", "INFO", "|".join(requested), "|".join(page), f"{detector} matches.")]
        return [DetectorFinding(detector, "CONFLICT", "HARD_BLOCKER" if hard else "WARNING", "|".join(requested), "|".join(page), f"Requested {', '.join(requested)} but page indicates {', '.join(page)}.")]

    def _compare_model_terms(self, req: ProductIdentityGraph, page: ProductIdentityGraph, page_text: str) -> list[DetectorFinding]:
        if not req.model_or_series_terms:
            return []
        ft = fold_text(page_text)
        matched = []
        missing = []
        for term in req.model_or_series_terms:
            pattern = rf"(?<![a-z0-9]){re.escape(fold_text(term))}(?![a-z0-9])"
            if re.search(pattern, ft):
                matched.append(term)
            else:
                missing.append(term)
        if not missing:
            return [DetectorFinding("model_identifier_detector", "MATCHED", "INFO", "|".join(req.model_or_series_terms), "|".join(matched), "Model/set/SKU-like identity terms match page evidence.")]
        # If the page exposes different model-like terms, call it conflict. If
        # it exposes none, this is still a hard blocker for exact verification
        # because the product identity cannot be proven.
        page_value = "|".join(page.model_or_series_terms)
        status = "CONFLICT" if page.model_or_series_terms else "MISSING_ON_PAGE"
        explanation = (
            f"Requested model/set/SKU-like term(s) {', '.join(missing)} not found in page evidence."
            + (f" Page indicates {page_value}." if page_value else "")
        )
        return [DetectorFinding("model_identifier_detector", status, "HARD_BLOCKER", "|".join(req.model_or_series_terms), page_value or "missing=" + "|".join(missing), explanation)]

    def _compare_product_form(self, req: ProductIdentityGraph, page: ProductIdentityGraph) -> list[DetectorFinding]:
        if not req.product_form_families:
            return []
        if not page.product_form_families:
            return [DetectorFinding("product_form_detector", "MISSING_ON_PAGE", "WARNING", "|".join(req.product_form_terms), "", "Requested product form not found on page.")]
        req_f = set(req.product_form_families)
        page_f = set(page.product_form_families)
        if req_f & page_f:
            return [DetectorFinding("product_form_detector", "MATCHED", "INFO", "|".join(req.product_form_terms), "|".join(page.product_form_terms), "Product form family matches.")]
        return [DetectorFinding("product_form_detector", "CONFLICT", "HARD_BLOCKER", "|".join(req.product_form_terms), "|".join(page.product_form_terms), "Requested product form family differs from page product form family.")]

    def _negative_terms(self, identity: ProductIdentityGraph, page_text: str) -> list[DetectorFinding]:
        if not identity.conflict_terms:
            return []
        ft = fold_text(page_text)
        hits = []
        for term in identity.conflict_terms:
            t = fold_text(term)
            if not t:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", ft):
                hits.append(term)
        if not hits:
            return []
        return [DetectorFinding("negative_term_detector", "CONFLICT", "HARD_BLOCKER", "avoid=" + "|".join(identity.conflict_terms), "found=" + "|".join(hits), "Page contains LLM/planner conflict terms that should not appear for the exact product.")]

    def _must_terms(self, identity: ProductIdentityGraph, page_text: str) -> list[DetectorFinding]:
        if not identity.must_match_terms:
            return []
        ft = fold_text(page_text)
        missing = []
        matched = []
        for term in identity.must_match_terms:
            pattern = rf"(?<![a-z0-9]){re.escape(fold_text(term))}(?![a-z0-9])"
            if re.search(pattern, ft):
                matched.append(term)
            else:
                missing.append(term)
        if not missing:
            return [DetectorFinding("critical_term_detector", "MATCHED", "INFO", "|".join(identity.must_match_terms), "|".join(matched), "All critical identity terms found.")]
        sev = "WARNING" if matched else "HARD_BLOCKER"
        return [DetectorFinding("critical_term_detector", "PARTIAL" if matched else "CONFLICT", sev, "|".join(identity.must_match_terms), "missing=" + "|".join(missing), "Some critical identity terms are missing from page evidence.")]


class _PseudoQuery:
    def __init__(self, main_text: str, country_code: str = "", ean: str | None = None, retailer_name: str | None = None) -> None:
        self.main_text = main_text
        self.country_code = country_code
        self.ean = ean
        self.retailer_name = retailer_name
