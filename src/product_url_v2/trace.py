from __future__ import annotations

from typing import Any, Sequence

from product_url_v2.models import (
    CandidateAssessment,
    GateStatus,
    IdentityMatch,
    Interpretation,
    PageEvidence,
    SearchObservation,
    to_jsonable,
)

TRACE_CONTRACT = "observable-decision-trace-v1"
TRACE_NOTICE = (
    "This trace exposes observable inputs, evidence, hypotheses, gate outcomes and "
    "selection judgments. It does not expose or fabricate hidden chain-of-thought."
)


def interpretation_summary(interpretation: Interpretation) -> dict[str, Any]:
    return {
        "normalized_text": interpretation.normalized_text,
        "signals": [
            {
                "field": item.field,
                "value": item.value,
                "confidence": item.confidence,
                "source": item.source,
                "evidence": item.evidence,
                "exact": item.exact,
            }
            for item in interpretation.signals
        ],
        "hypotheses": [
            {
                "hypothesis_id": item.hypothesis_id,
                "canonical_name": item.canonical_name,
                "attributes": dict(item.attributes),
                "negative_constraints": list(item.negative_constraints),
                "prior_probability": item.prior_probability,
                "rationale": item.rationale,
            }
            for item in interpretation.hypotheses
        ],
        "unresolved_discriminators": list(interpretation.unresolved_discriminators),
        "negative_constraints": list(interpretation.negative_constraints),
        "language_code": interpretation.language_code,
    }


def search_observation_summary(observation: SearchObservation, *, result_limit: int = 8) -> dict[str, Any]:
    product_like = [item for item in observation.results if item.product_like]
    return {
        "credit_number": observation.action.credit_number,
        "engine": observation.action.engine,
        "purpose": observation.action.purpose,
        "scope": observation.action.scope,
        "query": observation.action.query,
        "target_uncertainty": observation.action.target_uncertainty,
        "rationale": observation.action.rationale,
        "status": observation.status,
        "search_id": observation.search_id,
        "result_count": len(observation.results),
        "product_like_count": len(product_like),
        "answer_summary": observation.answer_summary[:2000],
        "error": observation.error,
        "top_results": [
            {
                "position": item.position,
                "title": item.title,
                "url": item.url,
                "source_section": item.source_section,
                "product_like": item.product_like,
                "snippet": item.snippet[:500],
            }
            for item in observation.results[:result_limit]
        ],
    }


def page_evidence_summary(page: PageEvidence) -> dict[str, Any]:
    return {
        "requested_url": page.requested_url,
        "final_url": page.final_url,
        "fetch_status": page.fetch_status.value,
        "status_code": page.status_code,
        "content_type": page.content_type,
        "title": page.title,
        "jsonld_product_count": len(page.jsonld_products),
        "visible_text_length": len(page.visible_text),
        "link_count": len(page.links),
        "image_count": len(page.images),
        "elapsed_ms": page.elapsed_ms,
        "fetch_error": page.fetch_error,
    }


def candidate_judgment(candidate: CandidateAssessment, *, selected: bool = False) -> dict[str, Any]:
    strengths: list[str] = []
    risks: list[str] = []
    blockers: list[str] = []

    if candidate.identity_match is IdentityMatch.EXACT:
        strengths.append("Exact identity threshold passed.")
    elif candidate.identity_match is IdentityMatch.PROBABLE:
        strengths.append("Identity evidence is probable.")
    elif candidate.identity_match is IdentityMatch.MISMATCH:
        blockers.append("Identity evidence indicates a different product.")
    else:
        risks.append("Identity remains unverified.")

    if candidate.evidence.get("search_product_like"):
        strengths.append("Search returned a structurally product-like external URL.")

    # A failed page-verification gate is a review risk when the original search
    # URL remains structurally product-like. It becomes a blocker only when the
    # candidate is not deliverable under the mandatory URL contract.
    _classify_gate(
        candidate.direct_product_page,
        "Direct product-page evidence",
        strengths,
        risks,
        blockers,
        fail_is_blocker=not candidate.review_eligible,
    )
    _classify_gate(candidate.durable_url, "Durable URL", strengths, risks, blockers, fail_is_blocker=True)
    _classify_gate(candidate.country_match, "Country-market alignment", strengths, risks, blockers)
    _classify_gate(candidate.retailer_match, "Requested-retailer alignment", strengths, risks, blockers)
    _classify_gate(candidate.browser_access, "Rendered browser usability", strengths, risks, blockers)
    _classify_gate(candidate.text_extractable, "Text extraction", strengths, risks, blockers)
    _classify_gate(candidate.coding_evidence_complete, "Coding-field coverage", strengths, risks, blockers)

    blockers.extend(candidate.conflicts)
    blockers.extend(candidate.hard_url_blockers)
    risks.extend(candidate.warnings)

    return {
        "candidate_id": candidate.candidate_id,
        "selected": selected,
        "url": candidate.url,
        "domain": candidate.domain,
        "source_role": candidate.source_role.value,
        "source_authority": candidate.source_authority,
        "search_rank": candidate.search_rank,
        "search_support": candidate.search_support,
        "identity_match": candidate.identity_match.value,
        "identity_confidence": candidate.identity_confidence,
        "direct_page_score": candidate.direct_page_score,
        "delivery_basis": candidate.evidence.get("delivery_basis"),
        "strictly_verified": candidate.strictly_verified,
        "review_eligible": candidate.review_eligible,
        "gates": gate_rows(candidate),
        "strengths": _dedupe(strengths),
        "risks": _dedupe(risks),
        "blockers": _dedupe(blockers),
        "evidence": to_jsonable(candidate.evidence),
    }


def gate_rows(candidate: CandidateAssessment) -> list[dict[str, Any]]:
    return [
        {"gate": "Identity", "status": candidate.identity_match.value, "score": candidate.identity_confidence},
        {"gate": "Direct product page", "status": candidate.direct_product_page.value, "score": candidate.direct_page_score},
        {"gate": "Durable URL", "status": candidate.durable_url.value, "score": None},
        {"gate": "Country match", "status": candidate.country_match.value, "score": None},
        {"gate": "Retailer match", "status": candidate.retailer_match.value, "score": None},
        {"gate": "Browser usability", "status": candidate.browser_access.value, "score": None},
        {"gate": "Text extractable", "status": candidate.text_extractable.value, "score": None},
        {"gate": "Coding evidence", "status": candidate.coding_evidence_complete.value, "score": None},
    ]


def candidate_ranking(candidates: Sequence[CandidateAssessment], selected_candidate_id: str | None = None) -> list[dict[str, Any]]:
    rows = [candidate_judgment(item, selected=item.candidate_id == selected_candidate_id) for item in candidates]
    return sorted(
        rows,
        key=lambda item: (
            bool(item["selected"]),
            bool(item["strictly_verified"]),
            bool(item["review_eligible"]),
            float(item["identity_confidence"]),
            float(item["direct_page_score"]),
            int(item["source_authority"]),
        ),
        reverse=True,
    )


def _classify_gate(
    status: GateStatus,
    label: str,
    strengths: list[str],
    risks: list[str],
    blockers: list[str],
    *,
    fail_is_blocker: bool = False,
) -> None:
    if status is GateStatus.PASS:
        strengths.append(f"{label} passed.")
    elif status is GateStatus.FAIL and fail_is_blocker:
        blockers.append(f"{label} failed.")
    elif status is GateStatus.FAIL:
        risks.append(f"{label} failed.")
    else:
        risks.append(f"{label} was not assessed.")


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))
