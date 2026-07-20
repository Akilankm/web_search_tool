from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.product_evidence_harness.agentic_fallback_runtime import (
    apply_agentic_browser_fallback_patch,
)
from src.product_evidence_harness.agent_service.orchestrator import (
    AgentRuntimeConfig,
    ProductEvidenceOrchestrator,
)
from src.product_evidence_harness.llm.agentic_browser import (
    AgenticBrowserConfig,
    AgenticBrowserInvestigator,
)
from src.product_evidence_harness.notebook_runtime import (
    PlatformRecovery,
    check_health,
    ensure_platform_ready,
    validate_result_contract,
)
from src.product_evidence_harness.runtime_contract import RUNTIME_CONTRACT_VERSION
from src.product_evidence_harness.structured_no_url_outcome import (
    NO_URL_DELIVERY_STATUS,
    NO_URL_OUTCOME_CODE,
)


class _Browser:
    def __init__(self) -> None:
        self.aborted = False
        self.fallback_bundle = SimpleNamespace(
            requested_url="https://shop.example/product",
            final_url="https://shop.example/product",
            browser_openable=True,
            text_scrapable=True,
        )

    def health(self):
        return {"status": "healthy", "agentic_tools": True}

    def start_agentic_session(self, request):
        return SimpleNamespace(
            session_id="session-1",
            terminal=False,
            blockers=(),
            url=request.url,
            title="Product",
            visible_product_name="Product",
            visible_text="Product details",
            interactive_elements=(),
            images=(),
            action_count=0,
            maximum_actions=4,
            warnings=(),
            screenshot_path=None,
        )

    def abort_agentic_session(self, session_id):
        self.aborted = True

    def acquire(self, request):
        return self.fallback_bundle


class _ForbiddenService:
    def predict(self, *args, **kwargs):
        raise PermissionError("403 Forbidden")


def _healthy_payload() -> dict:
    return {
        "status": "healthy",
        "runtime_contract_version": RUNTIME_CONTRACT_VERSION,
        "belief_driven_product_resolution": True,
        "mandatory_review_url_delivery": True,
        "deterministic_browser_fallback_on_llm_error": True,
        "notebook_self_healing_runtime": True,
        "compatibility_patches_applied": True,
        "manufacturer_first_primary_url": True,
        "business_judgement_review_artifact": True,
        "structured_no_url_review_outcome": True,
        "browser_service": {"agentic_tools": True},
        "configuration": {
            "three_stage_contract_enforced": True,
            "adaptive_search_contract_enforced": True,
            "llm_search_planning_enabled": True,
            "llm_search_feedback_enabled": True,
            "agentic_browser_contract_enforced": True,
            "llm_configured": True,
            "serpapi_request_limit": 3,
        },
    }


def _judgement_review() -> dict:
    return {
        "schema_version": "business-judgement-review-v1",
        "artifact_filename": "business_judgement_review.md",
        "artifact_path": "/data/artifacts/ROW-1/business_judgement_review.md",
        "human_review_status": "PENDING_HUMAN_COMPARISON",
        "judgement_count": 1,
        "visual_evidence_summary": {},
        "steps": [{"sequence_number": 1}],
    }


def test_agentic_llm_failure_falls_back_to_rendered_browser(monkeypatch) -> None:
    monkeypatch.setenv(
        "PRODUCT_HARNESS_ALLOW_DETERMINISTIC_BROWSER_FALLBACK_ON_LLM_ERROR",
        "true",
    )
    apply_agentic_browser_fallback_patch()
    browser = _Browser()
    investigator = AgenticBrowserInvestigator(
        browser=browser,
        service=_ForbiddenService(),
        config=AgenticBrowserConfig(
            max_turns_per_candidate=1,
            max_actions_per_candidate=1,
            max_observation_chars=2000,
            max_elements_in_prompt=10,
            max_images_in_prompt=4,
            image_detail="high",
        ),
    )
    request = SimpleNamespace(
        candidate_id="CAND-001",
        url="https://shop.example/product",
        product_identity=SimpleNamespace(to_dict=lambda: {}),
    )
    bundle, dossier = investigator.investigate(
        request=request,
        schema=SimpleNamespace(features=()),
    )
    assert bundle is browser.fallback_bundle
    assert dossier.status == "COMPLETED"
    assert dossier.termination_reason == "DETERMINISTIC_BROWSER_FALLBACK_AFTER_LLM_FAILURE"
    assert dossier.final_llm_assessment["agentic_llm_failed"] is True
    assert dossier.final_llm_assessment["deterministic_browser_fallback"] is True
    assert dossier.error is None
    assert browser.aborted is True


def test_health_exposes_runtime_contract(tmp_path: Path) -> None:
    orchestrator = ProductEvidenceOrchestrator(
        config=AgentRuntimeConfig(
            private_feature_root=tmp_path,
            artifact_root=tmp_path / "artifacts",
            browser_enabled=True,
        ),
        browser_client=_Browser(),
    )
    health = orchestrator.health()
    assert health["runtime_contract_version"] == RUNTIME_CONTRACT_VERSION
    assert health["belief_driven_product_resolution"] is True
    assert health["manufacturer_first_primary_url"] is True
    assert health["business_judgement_review_artifact"] is True
    assert health["structured_no_url_review_outcome"] is True


def test_notebook_rejects_legacy_or_incomplete_agent(monkeypatch) -> None:
    import src.product_evidence_harness.notebook_runtime as runtime

    legacy = _healthy_payload()
    legacy.pop("runtime_contract_version")
    monkeypatch.setattr(runtime, "api_json", lambda *args, **kwargs: legacy)
    with pytest.raises(RuntimeError, match="STALE_AGENT_IMAGE"):
        check_health()

    incomplete = _healthy_payload()
    incomplete.pop("business_judgement_review_artifact")
    monkeypatch.setattr(runtime, "api_json", lambda *args, **kwargs: incomplete)
    with pytest.raises(RuntimeError, match="business judgment review artifact"):
        check_health()

    no_structured_outcome = _healthy_payload()
    no_structured_outcome.pop("structured_no_url_review_outcome")
    monkeypatch.setattr(runtime, "api_json", lambda *args, **kwargs: no_structured_outcome)
    with pytest.raises(RuntimeError, match="structured no-safe-URL review outcome"):
        check_health()


def test_notebook_auto_recovers_stale_agent_from_same_checkout(
    monkeypatch, tmp_path: Path
) -> None:
    import src.product_evidence_harness.notebook_runtime as runtime

    calls = iter([RuntimeError("STALE_AGENT_IMAGE: old image"), _healthy_payload()])

    def fake_check_health():
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    recovery = PlatformRecovery(
        attempted=True,
        recovered=True,
        clean_build=True,
        command=("scripts/azureml_startup.sh", "--clean-build"),
        elapsed_seconds=12.5,
    )
    monkeypatch.setattr(runtime, "check_health", fake_check_health)
    monkeypatch.setattr(runtime, "recover_platform", lambda *args, **kwargs: recovery)

    health, result = ensure_platform_ready(
        tmp_path,
        auto_recover=True,
        clean_build=True,
    )
    assert health["business_judgement_review_artifact"] is True
    assert health["structured_no_url_review_outcome"] is True
    assert result.attempted is True
    assert result.recovered is True
    assert result.clean_build is True


def test_review_required_result_with_real_url_passes_delivery_contract() -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "primary_url": "https://shop.example/product",
        "primary_url_role": "RETAILER",
        "manufacturer_url": None,
        "retailer_url": "https://shop.example/product",
        "source_selection": {
            "policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES",
            "selection_reason": "RETAILER_REVIEW_URL_AFTER_MANUFACTURER_GATE_FAILURE",
        },
        "business_judgement_review": _judgement_review(),
        "product_identification": {"resolution_status": "PROBABLE"},
        "search": {
            "market_decision_path": [
                "manufacturer_primary",
                "country_alternative",
                "global_fallback",
            ]
        },
        "url_delivery": {"delivered": True, "strictly_verified": False},
        "product_match": {"match_reason": "BEST_AVAILABLE_REVIEW_URL"},
    }
    assert validate_result_contract(result) is result


def test_structured_no_url_review_result_passes_without_false_success() -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "primary_url": None,
        "primary_url_role": "NONE",
        "manufacturer_url": None,
        "retailer_url": None,
        "source_selection": {
            "policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES",
            "selection_reason": NO_URL_DELIVERY_STATUS,
        },
        "business_judgement_review": _judgement_review(),
        "product_identification": {"resolution_status": "AMBIGUOUS"},
        "search": {
            "market_decision_path": [
                "manufacturer_primary",
                "country_alternative",
                "global_fallback",
            ]
        },
        "url_delivery": {
            "required": True,
            "delivered": False,
            "status": NO_URL_DELIVERY_STATUS,
            "strictly_verified": False,
        },
        "resolution_outcome": {
            "code": NO_URL_OUTCOME_CODE,
            "terminal_status": "REVIEW_REQUIRED",
        },
        "product_match": {
            "match_reason": NO_URL_OUTCOME_CODE,
            "best_available_url": None,
        },
        "artifact_dir": "/data/artifacts/ROW-1",
    }
    assert validate_result_contract(result) is result


def test_missing_business_judgement_review_raises_schema_error() -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "primary_url": "https://shop.example/product",
        "primary_url_role": "RETAILER",
        "manufacturer_url": None,
        "retailer_url": "https://shop.example/product",
        "source_selection": {"policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES"},
        "product_identification": {"resolution_status": "PROBABLE"},
        "search": {"market_decision_path": ["manufacturer_primary"]},
        "url_delivery": {"delivered": True, "strictly_verified": False},
    }
    with pytest.raises(RuntimeError, match="RESULT_CONTRACT_MISMATCH") as exc:
        validate_result_contract(result)
    assert "business_judgement_review" in str(exc.value)


def test_unstructured_missing_url_still_raises_contract_error() -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "primary_url": None,
        "primary_url_role": "RETAILER",
        "manufacturer_url": None,
        "retailer_url": None,
        "source_selection": {
            "policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES",
            "selection_reason": "NO_SAFE_DIRECT_PRODUCT_URL",
        },
        "business_judgement_review": _judgement_review(),
        "product_identification": {"resolution_status": "AMBIGUOUS"},
        "search": {"market_decision_path": ["manufacturer_primary", "global_fallback"]},
        "url_delivery": {"delivered": False, "status": "NOT_DELIVERED"},
        "product_match": {
            "match_reason": "MANDATORY_PRODUCT_URL_NOT_FOUND",
            "best_available_url": None,
        },
        "artifact_dir": "/data/artifacts/ROW-1",
    }
    with pytest.raises(RuntimeError, match="INCONSISTENT_URL_DELIVERY_RESULT") as exc:
        validate_result_contract(result)
    assert "artifact_dir=/data/artifacts/ROW-1" in str(exc.value)
    assert len(str(exc.value)) < 1000
