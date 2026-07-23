from pathlib import Path

from product_url_v2.artifacts import ArtifactWriter
from product_url_v2.models import (
    CandidateAssessment,
    GateStatus,
    IdentityMatch,
    SourceRole,
)
from product_url_v2.trace import TRACE_CONTRACT, TRACE_NOTICE, candidate_judgment


def _candidate(**changes) -> CandidateAssessment:
    values = {
        "candidate_id": "C-1",
        "url": "https://shop.example.com/product/me04",
        "domain": "shop.example.com",
        "search_rank": 1,
        "search_support": 1.0,
        "source_role": SourceRole.COUNTRY_RETAILER,
        "identity_match": IdentityMatch.EXACT,
        "identity_confidence": 0.95,
        "direct_product_page": GateStatus.PASS,
        "direct_page_score": 0.8,
        "durable_url": GateStatus.PASS,
        "country_match": GateStatus.PASS,
        "retailer_match": GateStatus.NOT_ASSESSED,
        "browser_access": GateStatus.PASS,
        "text_extractable": GateStatus.PASS,
        "coding_evidence_complete": GateStatus.FAIL,
        "source_authority": 75,
        "evidence": {
            "matched_signals": ["model=ME04"],
            "required_identifier": "",
            "exact_identifier_verified": True,
            "delivery_basis": "rendered_product_evidence",
        },
        "conflicts": (),
        "warnings": ("Some downstream coding fields are incomplete.",),
    }
    values.update(changes)
    return CandidateAssessment(**values)


def test_candidate_judgment_exposes_policy_evidence() -> None:
    judgment = candidate_judgment(_candidate())

    assert judgment["mapping_eligible"] is True
    assert any("Direct product page" in item for item in judgment["strengths"])
    assert any("Downstream coding evidence" in item for item in judgment["risks"])
    assert not judgment["blockers"]


def test_identity_mismatch_is_an_explicit_blocker() -> None:
    judgment = candidate_judgment(
        _candidate(identity_match=IdentityMatch.MISMATCH, identity_confidence=0.1)
    )

    assert judgment["mapping_eligible"] is False
    assert any("different product" in item for item in judgment["blockers"])


def test_trace_contract_is_observable_not_private_reasoning() -> None:
    assert TRACE_CONTRACT == "observable-decision-trace-v1"
    assert "hidden chain-of-thought" in TRACE_NOTICE


def test_artifact_run_directory_is_locally_writable(tmp_path: Path) -> None:
    path = ArtifactWriter(tmp_path).prepare("ROW-1")

    assert path.is_dir()
    assert path.stat().st_mode & 0o200
