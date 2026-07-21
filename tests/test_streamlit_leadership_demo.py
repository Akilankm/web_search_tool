from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "leadership_demo.py"
SCRIPT = ROOT / "scripts" / "run_leadership_demo.sh"
DOC = ROOT / "docs" / "STREAMLIT_LEADERSHIP_DEMO.md"
CONFIG = ROOT / ".streamlit" / "config.toml"


def test_streamlit_app_is_parseable_and_exposes_full_demo_contract() -> None:
    assert APP.is_file()
    source = APP.read_text(encoding="utf-8")
    ast.parse(source, filename=str(APP))

    required_tokens = (
        "Product Evidence Intelligence",
        "Product interpretation",
        "Manufacturer-first truth",
        "Adaptive multi-engine search",
        "Rendered browser investigation",
        "Multimodal evidence",
        "Exact-product safety",
        "Requested-feature coverage",
        "Durable URL enforcement",
        "Controlled fallback",
        "No-fabrication outcome",
        "Human-comparable judgment trace",
        "Artifact-first governance",
        "Run budget",
        "runtime_options",
        "Search & budget",
        "Evidence & images",
        "Judgment trace",
        "Artifacts",
        "NO_SAFE_DIRECT_PRODUCT_URL_FOUND",
        "business_judgement_review.md",
        "run_configuration",
    )
    for token in required_tokens:
        assert token in source

    forbidden_tokens = (
        "SERPAPI_API_KEY",
        "LLM_API_KEY",
        "disable_identity_gate",
        "allow_expiring_url",
    )
    for token in forbidden_tokens:
        assert token not in source


def test_streamlit_app_loads_cleanly_when_agent_is_unavailable(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("agent unavailable for UI smoke test")

    monkeypatch.setattr(requests, "request", unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()

    assert app.exception == []
    rendered = "\n".join(
        str(item.value)
        for collection in (app.markdown, app.info, app.error, app.caption)
        for item in collection
    )
    assert "Product Evidence Intelligence" in rendered
    assert "Full platform capability" in rendered
    assert "Agent unavailable" in rendered
    assert app.button
    assert any(button.disabled for button in app.button)


def test_streamlit_launcher_is_valid_shell_and_uses_private_host_workflow() -> None:
    assert SCRIPT.is_file()
    completed = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    source = SCRIPT.read_text(encoding="utf-8")
    for token in (
        "requirements/demo.txt",
        "apps/leadership_demo.py",
        "PRODUCT_AGENT_URL",
        "STREAMLIT_PORT",
        "--server.headless true",
        "Ports panel",
    ):
        assert token in source


def test_streamlit_config_keeps_security_controls_enabled() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert 'address = "0.0.0.0"' in text
    assert "enableCORS = true" in text
    assert "enableXsrfProtection = true" in text
    assert "gatherUsageStats = false" in text


def test_leadership_demo_document_covers_azureml_and_terminal_outcomes() -> None:
    text = DOC.read_text(encoding="utf-8")
    for token in (
        "Azure ML VS Code setup",
        "run_leadership_demo.sh --install",
        "Ports",
        "8501",
        "belief-url-resolution-v8-leadership-demo",
        "leadership_demo_runtime_options=true",
        "COMPLETED",
        "REVIEW_REQUIRED",
        "NO_SAFE_DIRECT_PRODUCT_URL_FOUND",
        "Genuine failure",
    ):
        assert token in text
