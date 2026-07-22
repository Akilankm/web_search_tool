from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Sequence

from src.product_evidence_harness.browser_contracts import BrowserEvidenceBundle
from src.product_evidence_harness.contracts import CandidateScorecard
from src.product_evidence_harness.feature_schema import FeatureSchema, URLFeatureAssessment
from src.product_evidence_harness.source_authority import (
    SourceTier,
    source_role,
    source_tier,
    source_tier_name,
)
from src.product_evidence_harness.url_durability import ProductURLDurabilityGate
from src.product_evidence_harness.url_utils import normalize_url


_RETAILER_ROLES = {
    "REQUESTED_RETAILER",
    "MAJOR_COUNTRY_RETAILER",
    "GLOBAL_RETAILER",
    "MARKETPLACE",
}


@dataclass(frozen=True, slots=True)
class PrimaryURLAcceptance:
    accepted: bool
    primary_url: str | None
    scope: str
    browser_openable: bool | None
    text_scrapable: bool | None
    rendered_product_verified: bool | None
    exact_product_verified: bool | None
    full_feature_coverage: bool | None
    durable_url: bool | None
    reasons: tuple[str, ...]
    source_tier: int = int(SourceTier.UNKNOWN)
    source_tier_name: str = SourceTier.UNKNOWN.name
    source_role: str = "UNKNOWN"
    manufacturer_url: str | None = None
    retailer_url: str | None = None
    selection_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class StrictPrimaryURLSelector:
    """Select a strict coding URL or the strongest measured URL for review."""

    scope_priority = {
        "manufacturer_primary": 4,
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
        authorities = self._authority_index(scorecards)
        accepted: list[tuple[tuple[float, ...], PrimaryURLAcceptance]] = []
        reviewed: list[tuple[tuple[float, ...], PrimaryURLAcceptance]] = []

        for assessment in assessments:
            normalized = normalize_url(assessment.url)
            bundle = bundles.get(normalized)
            if bundle is None:
                # A candidate that was not investigated is not a browser failure.
                # It must remain unassessed and must not contaminate the selected
                # candidate's measured gate results.
                continue

            opened_url = bundle.final_url or bundle.requested_url or assessment.url
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
            tier, tier_name, role = authorities.get(
                normalized,
                (
                    int(SourceTier.UNKNOWN),
                    SourceTier.UNKNOWN.name,
                    "UNKNOWN",
                ),
            )
            decision = PrimaryURLAcceptance(
                accepted=not reasons,
                primary_url=opened_url,
                scope=scope,
                browser_openable=browser_openable,
                text_scrapable=text_scrapable,
                rendered_product_verified=rendered_verified,
                exact_product_verified=exact_verified,
                full_feature_coverage=full_features,
                durable_url=durable,
                reasons=tuple(dict.fromkeys(reasons)),
                source_tier=tier,
                source_tier_name=tier_name,
                source_role=role,
            )

            strict_score = (
                float(100 - tier),
                float(self.scope_priority.get(scope, 0)),
                assessment.required_coverage,
                assessment.critical_coverage,
                assessment.coverage,
                self._scorecard_confidence(normalized, scorecards),
            )
            review_score = (
                float(
                    browser_openable
                    and text_scrapable
                    and rendered_verified
                    and exact_verified
                    and durable
                ),
                float(exact_verified),
                float(rendered_verified),
                float(browser_openable),
                float(text_scrapable),
                float(durable),
                assessment.required_coverage,
                assessment.critical_coverage,
                assessment.coverage,
                float(100 - tier),
                float(self.scope_priority.get(scope, 0)),
                self._scorecard_confidence(normalized, scorecards),
            )
            reviewed.append((review_score, decision))
            if decision.accepted:
                accepted.append((strict_score, decision))

        if accepted:
            selected = max(accepted, key=lambda item: item[0])[1]
            manufacturer_url = self._best_role_url(
                accepted, roles={"MANUFACTURER"}
            )
            retailer_url = self._best_role_url(accepted, roles=_RETAILER_ROLES)
            reason = (
                "OFFICIAL_MANUFACTURER_PRIMARY_AFTER_STRICT_GATES"
                if selected.source_role == "MANUFACTURER"
                else "RETAILER_PRIMARY_BECAUSE_NO_QUALIFIED_MANUFACTURER_PAGE"
            )
            return replace(
                selected,
                manufacturer_url=manufacturer_url,
                retailer_url=retailer_url,
                selection_reason=reason,
            )

        if reviewed:
            # Deliver the strongest actually measured product URL for review.
            # Missing feature coverage keeps coding_ready=False, but it must not
            # erase a browser-openable, exact, durable product page.
            selected = max(reviewed, key=lambda item: item[0])[1]
            manufacturer_url = (
                selected.primary_url
                if selected.source_role == "MANUFACTURER"
                else None
            )
            retailer_url = (
                selected.primary_url
                if selected.source_role in _RETAILER_ROLES
                else None
            )
            return replace(
                selected,
                accepted=False,
                manufacturer_url=manufacturer_url,
                retailer_url=retailer_url,
                selection_reason="BEST_MEASURED_PRODUCT_URL_REQUIRES_REVIEW",
            )

        return PrimaryURLAcceptance(
            accepted=False,
            primary_url=None,
            scope="unresolved",
            browser_openable=None,
            text_scrapable=None,
            rendered_product_verified=None,
            exact_product_verified=None,
            full_feature_coverage=None,
            durable_url=None,
            reasons=("NO_CANDIDATE_COMPLETED_BROWSER_INVESTIGATION",),
            selection_reason="NO_CANDIDATE_COMPLETED_BROWSER_INVESTIGATION",
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
                and assessment.required_coverage
                >= schema.required_coverage_threshold
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
            "manufacturer_primary",
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
    def _authority_index(
        scorecards: Sequence[CandidateScorecard],
    ) -> dict[str, tuple[int, str, str]]:
        index: dict[str, tuple[int, str, str]] = {}
        for card in scorecards:
            normalized = normalize_url(card.candidate.url)
            if not normalized:
                continue
            authority = (
                source_tier(card.candidate),
                source_tier_name(card.candidate),
                source_role(card.candidate),
            )
            existing = index.get(normalized)
            if existing is None or authority[0] < existing[0]:
                index[normalized] = authority
        return index

    @staticmethod
    def _best_role_url(
        accepted: Sequence[tuple[tuple[float, ...], PrimaryURLAcceptance]],
        *,
        roles: set[str],
    ) -> str | None:
        matching = [item for item in accepted if item[1].source_role in roles]
        if not matching:
            return None
        return max(matching, key=lambda item: item[0])[1].primary_url

    @staticmethod
    def _scorecard_confidence(
        normalized_url: str | None,
        scorecards: Sequence[CandidateScorecard],
    ) -> float:
        for card in scorecards:
            if normalize_url(card.candidate.url) == normalized_url:
                return float(card.final_confidence)
        return 0.0
