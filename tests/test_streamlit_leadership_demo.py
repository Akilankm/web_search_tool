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


def test_streamlit_app_is_parseable_and_flow_first() -> None:
    source = APP.read_text(encoding="utf-8")
    ast.parse(source, filename=str(APP))
    for token in (
        "Product Evidence Intelligence",
        "Product text + market context",
        "Identity hypothesis + uncertainty",
        "Manufacturer → local → global",
        "Rendered pages + images",
        "Identity + features + durability",
        "Authority-aware URL decision",
        "Business judgment artifact",
        "Controllable run budget",
        "Decision flow",
        "Business judgments",
        "Observable evidence → explicit rule → business judgment → next action",
        "business_judgement_review.md",
        "safe_int",
    ):
        assert token in source
    for token in (
        "SERPAPI_API_KEY",
        "LLM_API_KEY",
        "disable_identity_gate",
        "allow_expiring_url",
    ):
        assert token not in source


def _unavailable(*args, **kwargs):
    raise requests.ConnectionError("agent unavailable for UI smoke test")


def test_streamlit_loads_when_agent_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()
    assert app.exception == []
    rendered = "\n".join(
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
    assert "Product Evidence Intelligence" in rendered
    assert "Agent unavailable" in rendered
    assert "Safety policy is fixed" in rendered
    assert any(button.disabled for button in app.button)


def test_null_budget_session_state_is_normalized(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["active_budget_preset"] = "Balanced"
    keys = (
        "serpapi_credits",
        "full_scrapes",
        "scrapes_per_domain",
        "planner_candidates",
        "agentic_candidates",
        "browser_turns_per_candidate",
        "browser_actions_per_candidate",
        "images_in_reasoning",
    )
    for key in keys:
        app.session_state[f"budget_{key}"] = None
    app.run()
    assert app.exception == []
    assert len(app.number_input) == len(keys)
    assert all(isinstance(widget.value, int) for widget in app.number_input)


def test_streamlit_launcher_is_valid_shell() -> None:
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


def test_streamlit_security_config() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert 'address = "0.0.0.0"' in text
    assert "enableCORS = true" in text
    assert "enableXsrfProtection = true" in text
    assert "gatherUsageStats = false" in text


def test_demo_document_covers_azureml_and_outcomes() -> None:
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
