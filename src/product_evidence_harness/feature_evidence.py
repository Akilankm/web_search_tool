from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol, Sequence

from src.product_evidence_harness.contracts import MatchVerification, ProductQuery, ScrapeResult
from src.product_evidence_harness.feature_schema import (
    EvidenceSetDecision,
    FeatureDefinition,
    FeatureEvidence,
    FeatureEvidenceStatus,
    FeatureSchema,
    URLFeatureAssessment,
)


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower().strip()


def _compact(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


class FeatureReasoner(Protocol):
    """Optional LLM boundary invoked only after search and scraping."""

    def evaluate(
        self,
        *,
        product: ProductQuery,
        schema: FeatureSchema,
        scrape: ScrapeResult,
        deterministic_evidence: Sequence[FeatureEvidence],
    ) -> Sequence[FeatureEvidence]:
        ...


@dataclass(frozen=True, slots=True)
class FeatureAwareEvidenceExtractor:
    context_window: int = 220

    def extract(
        self,
        *,
        product: ProductQuery,
        schema: FeatureSchema,
        scrape: ScrapeResult,
        verification: MatchVerification | None,
        reasoner: FeatureReasoner | None = None,
    ) -> URLFeatureAssessment:
        identity_status = verification.identity_status if verification else "UNVERIFIED"
        identity_accepted = bool(
            scrape.success
            and scrape.is_scrapable
            and scrape.looks_like_product_page
            and verification
            and verification.identity_status in {"VERIFIED", "PROBABLE"}
            and verification.exact_product_check != "MISMATCH"
        )
        rejection_reasons = tuple(verification.blocking_reasons) if verification and not identity_accepted else ()

        evidence = tuple(self._extract_feature(feature, scrape) for feature in schema.features)
        if reasoner is not None and identity_accepted:
            reasoned = tuple(
                reasoner.evaluate(
                    product=product,
                    schema=schema,
                    scrape=scrape,
                    deterministic_evidence=evidence,
                )
            )
            evidence = self._merge_evidence(schema, evidence, reasoned)

        supported = {item.feature_id for item in evidence if item.supported}
        conflicts = tuple(item.feature_id for item in evidence if item.status == FeatureEvidenceStatus.CONFLICTING_EVIDENCE)
        missing = tuple(item.feature_id for item in evidence if not item.supported and item.status != FeatureEvidenceStatus.NOT_APPLICABLE)
        coverage = self._coverage(schema.features, supported)
        required_coverage = self._coverage(schema.required_features, supported)
        critical_coverage = self._coverage(schema.critical_features, supported)
        source_role = "REJECTED"
        if identity_accepted:
            source_role = "PRIMARY_CANDIDATE" if required_coverage >= schema.required_coverage_threshold else "SUPPLEMENTARY_CANDIDATE"

        return URLFeatureAssessment(
            url=scrape.final_url or scrape.url,
            identity_accepted=identity_accepted,
            identity_status=identity_status,
            source_role=source_role,
            evidence=evidence,
            coverage=coverage,
            required_coverage=required_coverage,
            critical_coverage=critical_coverage,
            missing_features=missing,
            conflicting_features=conflicts,
            rejection_reasons=rejection_reasons,
        )

    def _extract_feature(self, feature: FeatureDefinition, scrape: ScrapeResult) -> FeatureEvidence:
        structured = {
            **{_fold(key): _compact(value) for key, value in (scrape.specs or {}).items()},
            **{_fold(key): _compact(value) for key, value in (scrape.attributes or {}).items() if not key.endswith("_json")},
            "brand": _compact(scrape.brand),
            "manufacturer": _compact(scrape.manufacturer),
            "product name": _compact(scrape.page_product_name or scrape.title),
        }
        aliases = tuple(dict.fromkeys(_fold(alias) for alias in feature.aliases if _fold(alias)))

        for alias in aliases:
            if alias in structured and structured[alias]:
                return self._evidence(feature, scrape, structured[alias], FeatureEvidenceStatus.STRUCTURED_FOUND, "structured_data", alias, 0.99)
        for alias in aliases:
            for key, value in structured.items():
                if value and (alias in key or key in alias):
                    return self._evidence(feature, scrape, value, FeatureEvidenceStatus.STRUCTURED_FOUND, "specification_table", key, 0.95)

        text = _compact(" ".join([scrape.description, scrape.markdown_excerpt, scrape.verification_text]))
        folded_text = _fold(text)
        for alias in aliases:
            index = folded_text.find(alias)
            if index < 0:
                continue
            start = max(0, index - self.context_window // 3)
            end = min(len(text), index + len(alias) + self.context_window)
            context = text[start:end].strip(" -:;,.\n")
            value = self._value_from_context(feature, context)
            return self._evidence(feature, scrape, value, FeatureEvidenceStatus.EXPLICITLY_FOUND, "page_text", context, 0.82)

        return self._evidence(feature, scrape, None, FeatureEvidenceStatus.NOT_FOUND, "", "", 0.0)

    def _value_from_context(self, feature: FeatureDefinition, context: str):
        if feature.allowed_values:
            folded = _fold(context)
            matches = [value for value in feature.allowed_values if _fold(value) in folded]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                return " | ".join(matches)
        value_type = feature.value_type.lower()
        if value_type in {"integer", "number"}:
            match = re.search(r"\b\d+(?:[.,]\d+)?\b", context)
            if match:
                return match.group(0).replace(",", ".")
        if value_type in {"boolean", "bool"}:
            folded = f" {_fold(context)} "
            if any(token in folded for token in (" no ", " not required", "without", " nein", " non ")):
                return "NO"
            if any(token in folded for token in (" yes ", " required", " with ", " ja", " oui")):
                return "YES"
        return context

    def _evidence(
        self,
        feature: FeatureDefinition,
        scrape: ScrapeResult,
        value,
        status: FeatureEvidenceStatus,
        method: str,
        evidence_text: str,
        confidence: float,
    ) -> FeatureEvidence:
        if isinstance(value, str) and " | " in value and feature.allowed_values:
            status = FeatureEvidenceStatus.CONFLICTING_EVIDENCE
            confidence = min(confidence, 0.40)
        return FeatureEvidence(
            feature_id=feature.feature_id,
            feature_name=feature.feature_name,
            source_url=scrape.final_url or scrape.url,
            value=value,
            status=status,
            confidence=confidence,
            evidence_text=_compact(evidence_text)[:500],
            evidence_location=method,
            extraction_method=method,
        )

    def _merge_evidence(
        self,
        schema: FeatureSchema,
        deterministic: Sequence[FeatureEvidence],
        reasoned: Sequence[FeatureEvidence],
    ) -> tuple[FeatureEvidence, ...]:
        merged = {item.feature_id: item for item in deterministic}
        valid_ids = {feature.feature_id for feature in schema.features}
        for item in reasoned:
            if item.feature_id not in valid_ids:
                continue
            current = merged.get(item.feature_id)
            if current is None or (not current.supported and item.supported) or item.confidence > current.confidence:
                merged[item.feature_id] = item
        return tuple(merged[feature.feature_id] for feature in schema.features)

    @staticmethod
    def _coverage(features: Sequence[FeatureDefinition], supported: set[str]) -> float:
        if not features:
            return 1.0
        return round(sum(1 for feature in features if feature.feature_id in supported) / len(features), 4)


@dataclass(frozen=True, slots=True)
class EvidenceSetSelector:
    """Choose one identity source plus the smallest useful supplementary set."""

    max_supplementary_urls: int = 3

    def select(
        self,
        *,
        schema: FeatureSchema,
        assessments: Sequence[URLFeatureAssessment],
        preferred_primary_url: str | None,
    ) -> EvidenceSetDecision:
        accepted = [assessment for assessment in assessments if assessment.identity_accepted]
        if not accepted:
            return EvidenceSetDecision(
                primary_url=None,
                supplementary_urls=(),
                selected_urls=(),
                coding_ready=False,
                status="NO_IDENTITY_ACCEPTED_SOURCE",
                total_coverage=0.0,
                required_coverage=0.0,
                critical_coverage=0.0,
                covered_features=(),
                missing_features=tuple(feature.feature_id for feature in schema.features),
                conflicting_features=(),
                reasons=("No scraped URL passed exact-product identity acceptance.",),
            )

        primary = next((item for item in accepted if item.url == preferred_primary_url), None)
        primary = primary or max(accepted, key=lambda item: (item.required_coverage, item.critical_coverage, item.coverage))
        selected = [primary]
        covered = set(primary.supported_feature_ids)
        remaining = [item for item in accepted if item.url != primary.url]

        while len(selected) - 1 < self.max_supplementary_urls:
            best = max(remaining, key=lambda item: len(item.supported_feature_ids - covered), default=None)
            if best is None:
                break
            gain = best.supported_feature_ids - covered
            if not gain:
                break
            selected.append(best)
            covered.update(gain)
            remaining = [item for item in remaining if item.url != best.url]

        required_ids = {feature.feature_id for feature in schema.required_features}
        critical_ids = {feature.feature_id for feature in schema.critical_features}
        all_ids = {feature.feature_id for feature in schema.features}
        conflicts = tuple(sorted({feature for item in selected for feature in item.conflicting_features}))
        missing = tuple(sorted(all_ids - covered))
        total_coverage = round(len(covered & all_ids) / max(1, len(all_ids)), 4)
        required_coverage = round(len(covered & required_ids) / max(1, len(required_ids)), 4) if required_ids else 1.0
        critical_coverage = round(len(covered & critical_ids) / max(1, len(critical_ids)), 4) if critical_ids else 1.0
        coding_ready = critical_coverage == 1.0 and required_coverage >= schema.required_coverage_threshold and not conflicts
        status = "CODING_READY" if coding_ready else "CODING_READY_WITH_FEATURE_REVIEW" if covered else "IDENTITY_READY_EVIDENCE_INCOMPLETE"
        return EvidenceSetDecision(
            primary_url=primary.url,
            supplementary_urls=tuple(item.url for item in selected[1:]),
            selected_urls=tuple(item.url for item in selected),
            coding_ready=coding_ready,
            status=status,
            total_coverage=total_coverage,
            required_coverage=required_coverage,
            critical_coverage=critical_coverage,
            covered_features=tuple(sorted(covered)),
            missing_features=missing,
            conflicting_features=conflicts,
            reasons=(
                "Primary URL proves product identity.",
                "Supplementary URLs are selected only when they add uncovered feature evidence.",
            ),
        )
