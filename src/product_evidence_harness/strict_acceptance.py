from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from src.product_evidence_harness.browser_contracts import BrowserEvidenceBundle
from src.product_evidence_harness.contracts import CandidateScorecard
from src.product_evidence_harness.feature_schema import FeatureSchema, URLFeatureAssessment
from src.product_evidence_harness.url_durability import ProductURLDurabilityGate
from src.product_evidence_harness.url_utils import normalize_url


@dataclass(frozen=True, slots=True)
class PrimaryURLAcceptance:
    accepted: bool
    primary_url: str | None
    scope: str
    browser_openable: bool
    text_scrapable: bool
    rendered_product_verified: bool
    exact_product_verified: bool
    full_feature_coverage: bool
    durable_url: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class StrictPrimaryURLSelector:
    """Select only a browser-verified exact product URL with complete feature evidence."""

    scope_priority = {
        "requested_retailer_country": 3,
        "country_primary": 2,
        "country_alternative": 2,
        "global_fallback": 1,
        "unresolved": 0,
    }

    def __init__(
        self,
        *,
        reject_expiring_urls: bool = True,
        require_all_features_on_primary: bool = True,
    ) -> None:
        self.reject_expiring_urls = reject_expiring_urls
        self.require_all_features_on_primary = require_all_features_on_primary
        self.durability_gate = ProductURLDurabilityGate()

    def select(
        self,
        *,
        schema: FeatureSchema,
        assessments: Sequence[URLFeatureAssessment],
        browser_bundles: Sequence[BrowserEvidenceBundle],
        scorecards: Sequence[CandidateScorecard],
    ) -> PrimaryURLAcceptance:
        bundles = self._bundle_index(browser_bundles)
        scopes = self._scope_index(scorecards)
        accepted: list[tuple[tuple[float, ...], PrimaryURLAcceptance]] = []
        rejection_reasons: list[str] = []

        for assessment in assessments:
            normalized = normalize_url(assessment.url)
            bundle = bundles.get(normalized)
            if bundle is None:
                rejection_reasons.append(f"{assessment.url}:BROWSER_EVIDENCE_MISSING")
                continue

            opened_url = bundle.final_url or bundle.requested_url
            durability = self.durability_gate.assess(opened_url)
            browser_openable = bool(bundle.browser_openable)
            text_scrapable = bool(bundle.text_scrapable)
            rendered_verified = bool(bundle.rendered_product_verified)
            exact_verified = bool(
                assessment.identity_accepted
                and assessment.identity_status == "VERIFIED"
                and rendered_verified
            )
            full_features = self._full_feature_coverage(schema, assessment)
            durable = durability.durable or not self.reject_expiring_urls

            reasons: list[str] = []
            if not browser_openable:
                reasons.append("PRIMARY_URL_NOT_BROWSER_OPENABLE")
            if not text_scrapable:
                reasons.append("PRIMARY_URL_NOT_TEXT_SCRAPABLE")
            if not rendered_verified:
                reasons.append("PRIMARY_URL_RENDERED_PRODUCT_NOT_VERIFIED")
            if not exact_verified:
                reasons.append("PRIMARY_URL_NOT_EXACT_PRODUCT")
            if not full_features:
                reasons.append("PRIMARY_URL_MISSING_REQUESTED_FEATURES")
            if not durable:
                reasons.extend(durability.reasons or ("PRIMARY_URL_NOT_DURABLE",))

            scope = scopes.get(normalized, "unresolved")
            decision = PrimaryURLAcceptance(
                accepted=not reasons,
                primary_url=opened_url if not reasons else None,
                scope=scope,
                browser_openable=browser_openable,
                text_scrapable=text_scrapable,
                rendered_product_verified=rendered_verified,
                exact_product_verified=exact_verified,
                full_feature_coverage=full_features,
                durable_url=durable,
                reasons=tuple(dict.fromkeys(reasons)),
            )
            if decision.accepted:
                score = (
                    float(self.scope_priority.get(scope, 0)),
                    assessment.required_coverage,
                    assessment.critical_coverage,
                    assessment.coverage,
                    self._scorecard_confidence(normalized, scorecards),
                )
                accepted.append((score, decision))
            else:
                rejection_reasons.extend(
                    f"{assessment.url}:{reason}" for reason in decision.reasons
                )

        if accepted:
            return max(accepted, key=lambda item: item[0])[1]

        return PrimaryURLAcceptance(
            accepted=False,
            primary_url=None,
            scope="unresolved",
            browser_openable=False,
            text_scrapable=False,
            rendered_product_verified=False,
            exact_product_verified=False,
            full_feature_coverage=False,
            durable_url=False,
            reasons=tuple(dict.fromkeys(rejection_reasons))
            or ("NO_URL_PASSED_STRICT_PRIMARY_ACCEPTANCE",),
        )

    def _full_feature_coverage(
        self,
        schema: FeatureSchema,
        assessment: URLFeatureAssessment,
    ) -> bool:
        if not self.require_all_features_on_primary:
            return bool(
                not assessment.missing_features
                and not assessment.conflicting_features
                and assessment.required_coverage >= schema.required_coverage_threshold
                and assessment.critical_coverage == 1.0
            )
        requested_ids = {feature.feature_id for feature in schema.features}
        return bool(
            requested_ids
            and requested_ids.issubset(assessment.supported_feature_ids)
            and assessment.coverage == 1.0
            and assessment.required_coverage == 1.0
            and assessment.critical_coverage == 1.0
            and not assessment.missing_features
            and not assessment.conflicting_features
        )

    @staticmethod
    def _bundle_index(
        bundles: Sequence[BrowserEvidenceBundle],
    ) -> dict[str, BrowserEvidenceBundle]:
        index: dict[str, BrowserEvidenceBundle] = {}
        for bundle in bundles:
            for value in (bundle.requested_url, bundle.final_url):
                normalized = normalize_url(value)
                if normalized:
                    index[normalized] = bundle
        return index

    @staticmethod
    def _scope_index(
        scorecards: Sequence[CandidateScorecard],
    ) -> dict[str, str]:
        index: dict[str, str] = {}
        ordered = (
            "requested_retailer_country",
            "country_primary",
            "country_alternative",
            "global_fallback",
        )
        for card in scorecards:
            normalized = normalize_url(card.candidate.url)
            if not normalized:
                continue
            markers = set(card.candidate.source_types)
            scope = next(
                (
                    name
                    for name in ordered
                    if f"scope_{name}" in markers
                ),
                "unresolved",
            )
            existing = index.get(normalized)
            if existing is None or StrictPrimaryURLSelector.scope_priority.get(
                scope, 0
            ) > StrictPrimaryURLSelector.scope_priority.get(existing, 0):
                index[normalized] = scope
        return index

    @staticmethod
    def _scorecard_confidence(
        normalized_url: str | None,
        scorecards: Sequence[CandidateScorecard],
    ) -> float:
        for card in scorecards:
            if normalize_url(card.candidate.url) == normalized_url:
                return float(card.final_confidence)
        return 0.0
