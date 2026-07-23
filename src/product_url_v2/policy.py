from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from product_url_v2.models import (
    CandidateAssessment,
    DeliveryDecision,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    SourceRole,
)

ACCEPTANCE_POLICY_VERSION = "product-url-acceptance-v1"

SOURCE_PRIORITY: Mapping[str, int] = {
    SourceRole.LOCAL_MANUFACTURER.value: 6,
    SourceRole.GLOBAL_MANUFACTURER.value: 5,
    SourceRole.REQUESTED_RETAILER.value: 4,
    SourceRole.COUNTRY_RETAILER.value: 3,
    SourceRole.GLOBAL_RETAILER.value: 2,
    SourceRole.MARKETPLACE.value: 1,
    SourceRole.UNKNOWN.value: 0,
}


@dataclass(frozen=True, slots=True)
class AcceptanceGate:
    key: str
    label: str
    status: str
    mandatory: bool
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.status in {GateStatus.PASS.value, "NOT_REQUIRED"}


@dataclass(frozen=True, slots=True)
class AcceptanceVerdict:
    policy_version: str
    eligible: bool
    strictly_verified: bool
    identifier_required: bool
    identifier_verified: bool
    gates: tuple[AcceptanceGate, ...]
    strengths: tuple[str, ...]
    blockers: tuple[str, ...]
    review_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "eligible": self.eligible,
            "strictly_verified": self.strictly_verified,
            "identifier_required": self.identifier_required,
            "identifier_verified": self.identifier_verified,
            "gates": [
                {
                    "key": gate.key,
                    "gate": gate.label,
                    "status": gate.status,
                    "mandatory": gate.mandatory,
                    "detail": gate.detail,
                }
                for gate in self.gates
            ],
            "strengths": list(self.strengths),
            "blockers": list(self.blockers),
            "review_reasons": list(self.review_reasons),
        }


def evaluate_acceptance(candidate: CandidateAssessment | Mapping[str, Any]) -> AcceptanceVerdict:
    """Evaluate the only authoritative final URL acceptance contract.

    Search, acquisition, browser, trace and UI layers must consume this verdict.
    They must not independently reconstruct mapping eligibility.
    """

    evidence = _mapping(_get(candidate, "evidence"))
    conflicts = _strings(_get(candidate, "conflicts"))
    warnings = _strings(_get(candidate, "warnings"))
    required_identifier = str(evidence.get("required_identifier") or "").strip()
    identifier_required = bool(required_identifier)
    identifier_verified = bool(evidence.get("exact_identifier_verified")) if identifier_required else True

    identity_status = _enum_value(_get(candidate, "identity_match"))
    direct_status = _enum_value(_get(candidate, "direct_product_page"))
    durable_status = _enum_value(_get(candidate, "durable_url"))
    browser_status = _enum_value(_get(candidate, "browser_access"))
    extractable_status = _enum_value(_get(candidate, "text_extractable"))
    coding_status = _enum_value(_get(candidate, "coding_evidence_complete"))
    country_status = _enum_value(_get(candidate, "country_match"))
    retailer_status = _enum_value(_get(candidate, "retailer_match"))

    gates = (
        AcceptanceGate(
            "exact_identity",
            "Exact product identity",
            GateStatus.PASS.value if identity_status == IdentityMatch.EXACT.value else GateStatus.FAIL.value,
            True,
            f"identity_match={identity_status or 'UNKNOWN'}",
        ),
        AcceptanceGate(
            "supplied_identifier",
            "Supplied EAN/GTIN/ISBN",
            (
                GateStatus.PASS.value
                if identifier_verified
                else GateStatus.FAIL.value
            )
            if identifier_required
            else "NOT_REQUIRED",
            True,
            (
                f"required_identifier={required_identifier}"
                if identifier_required
                else "No identifier was supplied."
            ),
        ),
        AcceptanceGate(
            "direct_product_page",
            "Direct product page",
            direct_status or GateStatus.NOT_ASSESSED.value,
            True,
        ),
        AcceptanceGate(
            "durable_url",
            "Durable canonical URL",
            durable_status or GateStatus.NOT_ASSESSED.value,
            True,
        ),
        AcceptanceGate(
            "browser_access",
            "Rendered browser accessibility",
            browser_status or GateStatus.NOT_ASSESSED.value,
            True,
        ),
        AcceptanceGate(
            "scrapable_content",
            "Scrapable rendered product content",
            extractable_status or GateStatus.NOT_ASSESSED.value,
            True,
        ),
        AcceptanceGate(
            "no_identity_conflicts",
            "No identity or edition conflicts",
            GateStatus.PASS.value if not conflicts else GateStatus.FAIL.value,
            True,
            "; ".join(conflicts),
        ),
        AcceptanceGate(
            "coding_evidence",
            "Downstream coding evidence",
            coding_status or GateStatus.NOT_ASSESSED.value,
            False,
        ),
        AcceptanceGate(
            "country_alignment",
            "Country-market alignment",
            country_status or GateStatus.NOT_ASSESSED.value,
            False,
        ),
        AcceptanceGate(
            "requested_retailer_alignment",
            "Requested-retailer alignment",
            retailer_status or GateStatus.NOT_ASSESSED.value,
            False,
        ),
    )

    mandatory = tuple(gate for gate in gates if gate.mandatory)
    eligible = all(gate.passed for gate in mandatory)
    strictly_verified = eligible and coding_status == GateStatus.PASS.value

    strengths = [f"{gate.label} passed." for gate in mandatory if gate.passed]
    blockers = [
        f"{gate.label} failed or was not completed."
        for gate in mandatory
        if not gate.passed
    ]
    blockers.extend(conflicts)

    review_reasons: list[str] = []
    if eligible and coding_status != GateStatus.PASS.value:
        review_reasons.append("Downstream coding evidence is incomplete.")
    if eligible and country_status != GateStatus.PASS.value:
        review_reasons.append("Country-market alignment is not fully confirmed.")
    if eligible and retailer_status == GateStatus.FAIL.value:
        review_reasons.append("The requested retailer did not match; an allowed fallback source was selected.")
    review_reasons.extend(warnings)

    if eligible:
        strengths.append("Candidate satisfies the complete product-to-URL acceptance contract.")
    else:
        blockers.append("Candidate remains discovery evidence and cannot be delivered as the final URL.")

    return AcceptanceVerdict(
        policy_version=ACCEPTANCE_POLICY_VERSION,
        eligible=eligible,
        strictly_verified=strictly_verified,
        identifier_required=identifier_required,
        identifier_verified=identifier_verified,
        gates=gates,
        strengths=tuple(_dedupe(strengths)),
        blockers=tuple(_dedupe(blockers)),
        review_reasons=tuple(_dedupe(review_reasons)),
    )


def browser_precheck(candidate: CandidateAssessment) -> bool:
    """Return whether browser rendering can still resolve this candidate.

    Missing page-only identity or identifier evidence is intentionally not a
    pre-browser blocker because JavaScript-rendered content may provide it.
    Explicit mismatch, transient URL, or a non-product discovery result remains
    disqualifying.
    """

    evidence = _mapping(candidate.evidence)
    return bool(
        candidate.browser_access is GateStatus.NOT_ASSESSED
        and candidate.identity_match is not IdentityMatch.MISMATCH
        and candidate.durable_url is not GateStatus.FAIL
        and bool(evidence.get("search_product_like"))
        and not candidate.conflicts
    )


def browser_rank(candidate: CandidateAssessment) -> tuple[float, ...]:
    evidence = _mapping(candidate.evidence)
    identifier_required = bool(evidence.get("required_identifier"))
    identifier_verified = bool(evidence.get("exact_identifier_verified")) if identifier_required else True
    return (
        1.0 if identifier_verified else 0.0,
        1.0 if candidate.identity_match is IdentityMatch.EXACT else 0.0,
        1.0 if candidate.identity_match is IdentityMatch.PROBABLE else 0.0,
        float(SOURCE_PRIORITY.get(candidate.source_role.value, 0)),
        candidate.identity_confidence,
        candidate.direct_page_score,
        float(candidate.source_authority) / 100.0,
        candidate.search_support,
        float(-(candidate.search_rank or 9999)),
    )


def final_rank(candidate: CandidateAssessment) -> tuple[float, ...]:
    verdict = evaluate_acceptance(candidate)
    return (
        1.0 if verdict.eligible else 0.0,
        float(SOURCE_PRIORITY.get(candidate.source_role.value, 0)),
        1.0 if candidate.country_match is GateStatus.PASS else 0.0,
        1.0 if candidate.retailer_match is GateStatus.PASS else 0.0,
        candidate.identity_confidence,
        candidate.direct_page_score,
        float(candidate.source_authority) / 100.0,
        candidate.search_support,
        float(-(candidate.search_rank or 9999)),
    )


def choose_delivery(candidates: Sequence[CandidateAssessment]) -> DeliveryDecision:
    verdicts = {candidate.candidate_id: evaluate_acceptance(candidate) for candidate in candidates}
    eligible = [candidate for candidate in candidates if verdicts[candidate.candidate_id].eligible]
    if not eligible:
        reasons = [
            f"No candidate passed {ACCEPTANCE_POLICY_VERSION}.",
            "A final URL requires exact identity, identifier agreement when supplied, a direct durable page, rendered-browser access, and scrapable rendered product content.",
        ]
        if candidates:
            reasons.append("Discovery candidates were preserved for audit and recovery but were not reported as successful mappings.")
        else:
            reasons.append("The search campaign produced no admissible direct-product candidate.")
        return DeliveryDecision(
            status=DeliveryStatus.FAILED,
            selected_url=None,
            selected_candidate_id=None,
            confidence=0.0,
            coding_ready=False,
            reasons=tuple(reasons),
        )

    selected = max(eligible, key=final_rank)
    verdict = verdicts[selected.candidate_id]
    manufacturer = selected.source_role in {
        SourceRole.LOCAL_MANUFACTURER,
        SourceRole.GLOBAL_MANUFACTURER,
    }
    reasons = [
        f"The candidate passed every mandatory gate in {ACCEPTANCE_POLICY_VERSION}.",
        "Identity was proven from acquired or rendered product evidence, never from the search snippet alone.",
        (
            "An exact manufacturer or publisher page was selected before retailer alternatives."
            if manufacturer
            else "No exact usable manufacturer page outranked this exact retailer product page."
        ),
    ]
    coding_ready = selected.coding_evidence_complete is GateStatus.PASS
    warnings = tuple(_dedupe([*verdict.review_reasons, *selected.warnings]))
    status = (
        DeliveryStatus.VERIFIED
        if verdict.strictly_verified and not verdict.review_reasons
        else DeliveryStatus.REVIEW_REQUIRED
    )
    if status is DeliveryStatus.REVIEW_REQUIRED:
        reasons.append("The product-to-URL mapping is valid; review is limited to secondary evidence.")

    return DeliveryDecision(
        status=status,
        selected_url=selected.url,
        selected_candidate_id=selected.candidate_id,
        confidence=selected.identity_confidence,
        coding_ready=coding_ready,
        reasons=tuple(reasons),
        warnings=warnings,
    )


def _get(candidate: CandidateAssessment | Mapping[str, Any], key: str) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(key)
    return getattr(candidate, key)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _enum_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))
