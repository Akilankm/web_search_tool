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
    schema = SimpleNamespace(features=())

    bundle, dossier = investigator.investigate(request=request, schema=schema)

    assert bundle is browser.fallback_bundle
    assert dossier.status == "COMPLETED"
    assert dossier.termination_reason == (
        "DETERMINISTIC_BROWSER_FALLBACK_AFTER_LLM_FAILURE"
    )
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
    assert health["mandatory_review_url_delivery"] is True
    assert health["deterministic_browser_fallback_on_llm_error"] is True
    assert health["notebook_self_healing_runtime"] is True


def test_notebook_rejects_legacy_agent_before_submission(monkeypatch) -> None:
    import src.product_evidence_harness.notebook_runtime as runtime

    legacy = _healthy_payload()
    legacy.pop("runtime_contract_version")
    monkeypatch.setattr(runtime, "api_json", lambda *args, **kwargs: legacy)

    with pytest.raises(RuntimeError, match="STALE_AGENT_IMAGE"):
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

    assert health["runtime_contract_version"] == RUNTIME_CONTRACT_VERSION
    assert result.attempted is True
    assert result.recovered is True
    assert result.clean_build is True
    assert "STALE_AGENT_IMAGE" in result.trigger


def test_review_required_result_with_real_url_passes_delivery_contract() -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "primary_url": "https://shop.example/product",
        "product_identification": {"resolution_status": "PROBABLE"},
        "search": {"market_decision_path": ["country_alternative", "global_fallback"]},
        "url_delivery": {"delivered": True, "strictly_verified": False},
        "product_match": {"match_reason": "BEST_AVAILABLE_REVIEW_URL"},
    }
    assert validate_result_contract(result) is result


def test_missing_url_raises_concise_delivery_error() -> None:
    result = {
        "job_status": "REVIEW_REQUIRED",
        "primary_url": None,
        "product_identification": {"resolution_status": "AMBIGUOUS"},
        "search": {"market_decision_path": ["country_alternative", "global_fallback"]},
        "url_delivery": {"delivered": False, "status": "NOT_DELIVERED"},
        "product_match": {
            "match_reason": "MANDATORY_PRODUCT_URL_NOT_FOUND",
            "best_available_url": None,
        },
        "artifact_dir": "/data/artifacts/ROW-1",
    }
    with pytest.raises(RuntimeError, match="MANDATORY_PRODUCT_URL_NOT_DELIVERED") as exc:
        validate_result_contract(result)
    assert "artifact_dir=/data/artifacts/ROW-1" in str(exc.value)
    assert len(str(exc.value)) < 1000
