from __future__ import annotations

import importlib
import json
import sys
from types import SimpleNamespace

from src.product_evidence_harness.browser_contracts import (
    AcquisitionMethod,
    BrowserEvidenceRequest,
    EvidenceIntent,
    VisualAsset,
)
from src.product_evidence_harness.config import SerpAPIConfig
from src.product_evidence_harness.llm.service import LLMConfig
from src.product_evidence_harness.null_numeric_runtime import _PlannerCounterProxy
from src.product_evidence_harness.numeric_safety import safe_float, safe_int


def test_numeric_helpers_default_null_and_malformed_values() -> None:
    assert safe_int(None, 7) == 7
    assert safe_int("bad", 7) == 7
    assert safe_float(None, 1.5) == 1.5
    assert safe_float("bad", 1.5) == 1.5


def test_evidence_intent_accepts_explicit_null_numeric_payload() -> None:
    intent = EvidenceIntent(
        maximum_images=None,  # type: ignore[arg-type]
        maximum_screenshots=None,  # type: ignore[arg-type]
        maximum_actions=None,  # type: ignore[arg-type]
        requested_evidence_categories=None,  # type: ignore[arg-type]
    )
    assert intent.maximum_images == 10
    assert intent.maximum_screenshots == 8
    assert intent.maximum_actions == 30
    assert intent.requested_evidence_categories == ()


def test_browser_request_deserializes_null_intent_values() -> None:
    request = BrowserEvidenceRequest.from_mapping(
        {
            "job_id": "ROW-1",
            "candidate_id": "CAND-001",
            "url": "https://example.com/product",
            "product_identity": {
                "row_id": "ROW-1",
                "main_text": "Example product",
                "country_code": "GB",
            },
            "intent": {
                "maximum_images": None,
                "maximum_screenshots": None,
                "maximum_actions": None,
            },
        }
    )
    assert request.intent.maximum_images == 10
    assert request.intent.maximum_screenshots == 8
    assert request.intent.maximum_actions == 30


def test_visual_asset_deserializes_null_dimensions() -> None:
    asset = VisualAsset.from_mapping(
        {
            "asset_id": "IMG-001",
            "source_page_url": "https://example.com/product",
            "local_path": "/tmp/image.png",
            "acquisition_method": AcquisitionMethod.BROWSER_ELEMENT_SCREENSHOT.value,
            "width": None,
            "height": None,
            "size_bytes": None,
        }
    )
    assert asset.width == 0
    assert asset.height == 0
    assert asset.size_bytes == 0


def test_planner_proxy_normalizes_optional_counters() -> None:
    planner = SimpleNamespace(calls=None, fallbacks=None)
    proxy = _PlannerCounterProxy(planner)
    assert proxy.calls == 0
    assert proxy.fallbacks == 0
    proxy.calls = None
    proxy.fallbacks = "bad"
    assert planner.calls == 0
    assert planner.fallbacks == 0


def test_serpapi_config_accepts_null_optional_result_limit(monkeypatch) -> None:
    monkeypatch.setenv("SERPAPI_API_KEY", "real-serpapi-key-value-for-test")
    config = SerpAPIConfig.from_env(
        env_file=None,
        country_code="GB",
        language_code="en",
        organic_num_results=None,
    )
    assert config.organic_num_results == 100


def test_llm_config_normalizes_null_optional_numeric_fields() -> None:
    config = LLMConfig(
        api_key="key",
        api_version="2026-01-01",
        endpoint="https://example.openai.azure.com",
        deployment="deployment",
        max_tokens=None,  # type: ignore[arg-type]
        temperature=None,  # type: ignore[arg-type]
        connect_timeout=None,  # type: ignore[arg-type]
        read_timeout=None,  # type: ignore[arg-type]
        max_retries=None,  # type: ignore[arg-type]
    )
    assert config.max_tokens == 1600
    assert config.temperature == 0.0
    assert config.connect_timeout == 15.0
    assert config.read_timeout == 120.0
    assert config.max_retries == 2


def test_agent_failure_writes_traceback_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path))
    monkeypatch.setenv("PRIVATE_FEATURE_ROOT", str(tmp_path / "private"))
    monkeypatch.setenv("PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE", "false")
    sys.modules.pop("src.product_evidence_harness.agent_service.app", None)
    agent_app = importlib.import_module("src.product_evidence_harness.agent_service.app")

    monkeypatch.setattr(
        agent_app,
        "orchestrator",
        SimpleNamespace(config=SimpleNamespace(artifact_root=tmp_path)),
    )
    record = SimpleNamespace(
        job_id="job-1",
        stage="ADAPTIVE_SEARCH",
        payload={"product": {"row_id": "ROW-FAIL"}},
    )

    try:
        int(None)  # type: ignore[arg-type]
    except TypeError as exc:
        path = agent_app._write_failure_diagnostic(record, exc)

    assert path is not None
    payload = json.loads((tmp_path / "ROW-FAIL" / "technical_failure.json").read_text())
    assert payload["error_type"] == "TypeError"
    assert "int() argument must be" in payload["error_message"]
    assert payload["stage"] == "ADAPTIVE_SEARCH"
    assert "test_agent_failure_writes_traceback_artifact" in payload["traceback"]
