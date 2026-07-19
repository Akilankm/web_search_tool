from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.product_evidence_harness.compat_patches import (
    apply_compatibility_patches,
    compatibility_patches_applied,
)
from src.product_evidence_harness.runtime_contract import RUNTIME_CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_compatibility_patch_bootstrap_is_idempotent() -> None:
    apply_compatibility_patches()
    apply_compatibility_patches()
    assert compatibility_patches_applied() is True


def test_exact_uvicorn_entrypoint_exposes_runtime_contract_in_clean_process(
    tmp_path: Path,
) -> None:
    script = r'''
import json
from src.product_evidence_harness.agent_service import app as agent_app

agent_app._validate_runtime = lambda: ({
    "three_stage_contract_enforced": True,
    "adaptive_search_contract_enforced": True,
    "llm_search_planning_enabled": True,
    "llm_search_feedback_enabled": True,
    "agentic_browser_contract_enforced": True,
    "llm_configured": True,
    "serpapi_request_limit": 3,
}, None)
agent_app.orchestrator.health = lambda: {
    "status": "healthy",
    "browser_service": {"status": "healthy", "agentic_tools": True},
    "private_feature_root_exists": True,
    "artifact_root": "/tmp/artifacts",
}
payload = agent_app.health()
assert payload["runtime_contract_version"] == "belief-url-resolution-v6-business-judgement-review"
assert payload["belief_driven_product_resolution"] is True
assert payload["mandatory_review_url_delivery"] is True
assert payload["deterministic_browser_fallback_on_llm_error"] is True
assert payload["notebook_self_healing_runtime"] is True
assert payload["compatibility_patches_applied"] is True
assert payload["manufacturer_first_primary_url"] is True
assert payload["business_judgement_review_artifact"] is True
assert payload["agent_entrypoint"] == "src.product_evidence_harness.agent_service.app:app"
print(json.dumps(payload, sort_keys=True))
'''
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(ROOT / "src"),
            "PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE": "false",
            "PRIVATE_FEATURE_ROOT": str(tmp_path / "private"),
            "ARTIFACT_ROOT": str(tmp_path / "artifacts"),
        }
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["runtime_contract_version"] == RUNTIME_CONTRACT_VERSION
    assert payload["compatibility_patches_applied"] is True
    assert payload["manufacturer_first_primary_url"] is True
    assert payload["business_judgement_review_artifact"] is True
