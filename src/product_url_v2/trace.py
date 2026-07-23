from __future__ import annotations

from typing import Any, Sequence

from product_url_v2.models import CandidateAssessment, Interpretation, PageEvidence, SearchObservation, to_jsonable
from product_url_v2.policy import evaluate_acceptance, final_rank

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
    verdict = evaluate_acceptance(candidate)
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
        "exact_identifier_required": verdict.identifier_required,
        "exact_identifier_verified": verdict.identifier_verified,
        "direct_page_score": candidate.direct_page_score,
        "delivery_basis": candidate.evidence.get("delivery_basis"),
        "acceptance_policy": verdict.policy_version,
        "mapping_eligible": verdict.eligible,
        "strictly_verified": verdict.strictly_verified,
        "review_eligible": verdict.eligible,
        "gates": verdict.as_dict()["gates"],
        "strengths": list(verdict.strengths),
        "risks": list(verdict.review_reasons),
        "blockers": list(verdict.blockers),
        "evidence": to_jsonable(candidate.evidence),
    }


def gate_rows(candidate: CandidateAssessment) -> list[dict[str, Any]]:
    return evaluate_acceptance(candidate).as_dict()["gates"]


def candidate_ranking(
    candidates: Sequence[CandidateAssessment],
    selected_candidate_id: str | None = None,
) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.candidate_id == selected_candidate_id,
            *final_rank(item),
        ),
        reverse=True,
    )
    return [
        candidate_judgment(item, selected=item.candidate_id == selected_candidate_id)
        for item in ranked
    ]
