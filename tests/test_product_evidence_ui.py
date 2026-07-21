from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "product_evidence_ui.py"
SCRIPT = ROOT / "scripts" / "run_product_evidence_ui.sh"
DOC = ROOT / "docs" / "PRODUCT_EVIDENCE_UI.md"
CONFIG = ROOT / ".streamlit" / "config.toml"


def _rendered_text(app: AppTest) -> str:
    return "\n".join(
        str(item.value)
        for collection in (
            app.markdown,
            app.subheader,
            app.info,
            app.error,
            app.caption,
        )
        for item in collection
    )


def test_ui_is_parseable_and_exposes_professional_workflow_contract() -> None:
    assert APP.is_file()
    source = APP.read_text(encoding="utf-8")
    ast.parse(source, filename=str(APP))

    for token in (
        "Product Evidence Platform",
        "Latency Optimized",
        "Standard",
        "Coverage Optimized",
        "Runtime controls",
        "Product input",
        "Workflow and decision",
        "Judgment sequence",
        "Observable evidence",
        "Source selection",
        "Exact identity",
        "Durable URL",
        "business_judgement_review.md",
        "run_configuration",
        "belief-url-resolution-v9-product-evidence-ui",
    ):
        assert token in source

    for forbidden in (
        "leadership",
        "management",
        "Fast demo",
        "Deep evidence",
        "SERPAPI_API_KEY",
        "LLM_API_KEY",
        "disable_identity_gate",
        "allow_expiring_url",
    ):
        assert forbidden.lower() not in source.lower()


def test_ui_loads_cleanly_when_agent_is_unavailable(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("agent unavailable for UI smoke test")

    monkeypatch.setattr(requests, "request", unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product Evidence Platform" in rendered
    assert "Agent unavailable" in rendered
    assert app.button
    assert any(button.disabled for button in app.button)


def test_ui_recovers_null_runtime_control_session_state(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("agent unavailable for null-state test")

    monkeypatch.setattr(requests, "request", unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()
    assert app.exception == []

    control_keys = (
        "serpapi_credits",
        "full_scrapes",
        "scrapes_per_domain",
        "planner_candidates",
        "agentic_candidates",
        "browser_turns_per_candidate",
        "browser_actions_per_candidate",
        "images_in_reasoning",
    )
    for key in control_keys:
        app.session_state[f"control_{key}"] = None
    app.run()

    assert app.exception == []
    for key in control_keys:
        assert isinstance(app.session_state[f"control_{key}"], int)


def test_ui_launcher_is_valid_shell() -> None:
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
        "requirements/ui.txt",
        "apps/product_evidence_ui.py",
        "PRODUCT_AGENT_URL",
        "STREAMLIT_PORT",
        "--server.headless true",
        "Ports panel",
    ):
        assert token in source
    for forbidden in ("leadership", "management", "demo"):
        assert forbidden not in source.lower()


def test_streamlit_config_keeps_security_controls_enabled() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert 'address = "0.0.0.0"' in text
    assert "enableCORS = true" in text
    assert "enableXsrfProtection = true" in text
    assert "gatherUsageStats = false" in text


def test_ui_document_covers_contract_and_terminal_outcomes() -> None:
    text = DOC.read_text(encoding="utf-8")
    for token in (
        "Product Evidence Platform UI",
        "Latency Optimized",
        "Standard",
        "Coverage Optimized",
        "Runtime controls",
        "belief-url-resolution-v9-product-evidence-ui",
        "per_job_runtime_controls=true",
        "COMPLETED",
        "REVIEW_REQUIRED",
        "NO_SAFE_DIRECT_PRODUCT_URL_FOUND",
        "Technical failure",
    ):
        assert token in text
    for forbidden in ("leadership", "management", "demo"):
        assert forbidden not in text.lower()
