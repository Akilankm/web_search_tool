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
    collections = (
        app.title,
        app.header,
        app.subheader,
        app.markdown,
        app.success,
        app.warning,
        app.info,
        app.error,
        app.caption,
        app.metric,
    )
    return "\n".join(str(item.value) for collection in collections for item in collection)


def _unavailable(*args, **kwargs):
    raise requests.ConnectionError("agent unavailable for UI test")


def _exact_identity_result() -> dict:
    return {
        "job_status": "REVIEW_REQUIRED",
        "product": {"row_id": "ROW-IDENTITY"},
        "product_identification": {
            "resolution_status": "EXACT",
            "metrics": {
                "identity_completeness": 0.94,
                "ambiguity_entropy": 0.0,
                "posterior_margin": 0.88,
            },
            "leading_hypothesis": {
                "hypothesis_id": "H-1",
                "canonical_name": "LEGO Star Wars R2-D2 75379",
                "posterior_probability": 0.96,
                "attributes": {
                    "brand": "LEGO",
                    "manufacturer": "LEGO Group",
                    "model_number": "75379",
                    "product_form": "construction set",
                },
            },
            "hypotheses": [
                {
                    "hypothesis_id": "H-1",
                    "canonical_name": "LEGO Star Wars R2-D2 75379",
                    "posterior_probability": 0.96,
                    "attributes": {},
                }
            ],
            "claims": [
                {
                    "field": "brand",
                    "value": "LEGO",
                    "status": "WEB_VERIFIED",
                    "confidence": 0.99,
                }
            ],
            "evidence_ledger": [
                {
                    "field": "model_number",
                    "value": "75379",
                    "polarity": "SUPPORTS",
                    "source_url": "https://example.com/evidence",
                    "source_reliability": 0.9,
                    "extraction_confidence": 0.95,
                }
            ],
            "uncertainties": [],
            "unknowns": [],
        },
        "primary_url": None,
        "manufacturer_url": None,
        "retailer_url": None,
        "primary_url_acceptance": {
            "browser_openable": False,
            "text_scrapable": False,
            "rendered_product_verified": False,
            "exact_product_verified": False,
            "full_feature_coverage": False,
            "durable_url": False,
        },
        "search": {"stages": []},
        "business_judgement_review": {"steps": []},
    }


def test_ui_is_parseable_and_product_identification_first() -> None:
    source = APP.read_text(encoding="utf-8")
    ast.parse(source, filename=str(APP))

    for token in (
        "Product Identification Platform",
        "Web pages and URLs are supporting evidence—not the product result",
        "Product identity",
        "Evidence basis",
        "Alternative hypotheses",
        "Source evidence",
        "Unresolved distinctions",
        "VERIFIED",
        "NOT VERIFIED",
        "NOT ASSESSED",
        "Latency Optimized",
        "Standard",
        "Coverage Optimized",
        "Identify product",
    ):
        assert token in source

    for forbidden in (
        "Accepted direct product URL",
        '("browser_openable", "Browser")',
        '("text_scrapable", "Scrapable")',
        '("durable_url", "Durable URL")',
        "Fast demo",
        "Deep evidence",
        "leadership",
        "management",
    ):
        assert forbidden.lower() not in source.lower()


def test_ui_loads_cleanly_when_agent_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product Identification Platform" in rendered
    assert "Agent unavailable" in rendered
    assert any(button.disabled for button in app.button)


def test_exact_product_remains_identified_without_a_usable_url(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _exact_identity_result()
    app.session_state["run_elapsed_seconds"] = 2.4
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product identified: LEGO Star Wars R2-D2 75379" in rendered
    assert "LEGO Star Wars R2-D2 75379" in rendered
    assert "Source URLs are supporting evidence only" in rendered
    assert "Accepted direct product URL" not in rendered
    assert "FAIL" not in rendered


def test_ui_recovers_null_runtime_control_session_state(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
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


def test_streamlit_config_keeps_security_controls_enabled() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert 'address = "0.0.0.0"' in text
    assert "enableCORS = true" in text
    assert "enableXsrfProtection = true" in text
    assert "gatherUsageStats = false" in text


def test_ui_document_defines_product_first_contract() -> None:
    text = DOC.read_text(encoding="utf-8")
    for token in (
        "Product Identification Platform",
        "Primary outcome",
        "identified product",
        "ResolutionStatus",
        "EXACT",
        "PROBABLE",
        "AMBIGUOUS",
        "Source evidence",
        "URLs are evidence locations",
        "Latency Optimized",
        "Standard",
        "Coverage Optimized",
    ):
        assert token in text
    assert "Accepted direct product URL" not in text
