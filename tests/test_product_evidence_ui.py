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


def _no_url_result() -> dict:
    return {
        "job_status": "REVIEW_REQUIRED",
        "coding_ready": False,
        "product": {"row_id": "ROW-NO-URL", "main_text": "LEGO R2-D2 75379"},
        "product_identification": {
            "resolution_status": "EXACT",
            "leading_hypothesis": {
                "hypothesis_id": "H-1",
                "canonical_name": "LEGO Star Wars R2-D2 75379",
                "posterior_probability": 0.96,
            },
            "hypotheses": [
                {
                    "hypothesis_id": "H-1",
                    "canonical_name": "LEGO Star Wars R2-D2 75379",
                    "posterior_probability": 0.96,
                }
            ],
            "claims": [{"field": "brand", "value": "LEGO", "status": "WEB_VERIFIED"}],
            "evidence_ledger": [
                {
                    "field": "model_number",
                    "value": "75379",
                    "polarity": "SUPPORTS",
                    "source_url": "https://example.com/evidence",
                }
            ],
            "uncertainties": [],
            "unknowns": [],
        },
        "primary_url": None,
        "manufacturer_url": None,
        "retailer_url": None,
        "url_delivery": {"delivered": False, "strictly_verified": False, "url": None},
        "primary_url_acceptance": {
            "accepted": False,
            "browser_openable": False,
            "text_scrapable": False,
            "rendered_product_verified": False,
            "exact_product_verified": False,
            "full_feature_coverage": False,
            "durable_url": False,
            "reasons": ["NO_SAFE_DIRECT_PRODUCT_URL_FOUND"],
        },
        "resolution_outcome": {
            "message": "No safe direct product page passed all required gates.",
            "suggested_next_actions": ["Provide a known retailer URL."],
        },
        "search": {
            "serpapi_requests_used": 3,
            "serpapi_request_limit": 3,
            "stages": [
                {
                    "name": "manufacturer_primary",
                    "results_returned": 20,
                    "new_candidate_urls": 5,
                    "candidates_qualified": 2,
                    "candidates_scraped": 1,
                },
                {
                    "name": "country_alternative",
                    "results_returned": 15,
                    "new_candidate_urls": 4,
                    "candidates_qualified": 1,
                    "candidates_scraped": 1,
                },
            ],
        },
        "agentic_browser": {"candidate_investigations_completed": 2},
        "business_judgement_review": {"steps": []},
    }


def _usable_url_result() -> dict:
    result = _no_url_result()
    result.update(
        {
            "job_status": "COMPLETED",
            "coding_ready": True,
            "primary_url": "https://www.lego.com/product/75379",
            "manufacturer_url": "https://www.lego.com/product/75379",
            "url_delivery": {
                "delivered": True,
                "strictly_verified": True,
                "url": "https://www.lego.com/product/75379",
            },
            "source_selection": {
                "source_role": "MANUFACTURER",
                "source_tier_name": "GLOBAL_MANUFACTURER",
                "selection_reason": "Official manufacturer page passed all required gates.",
            },
            "primary_url_acceptance": {
                "accepted": True,
                "browser_openable": True,
                "text_scrapable": True,
                "rendered_product_verified": True,
                "exact_product_verified": True,
                "full_feature_coverage": True,
                "durable_url": True,
                "reasons": ["EXACT_PRODUCT_IDENTITY", "DURABLE_URL"],
            },
            "evidence_set": {"required_coverage": 1.0},
        }
    )
    return result


def test_ui_is_parseable_and_decision_first() -> None:
    source = APP.read_text(encoding="utf-8")
    ast.parse(source, filename=str(APP))

    for token in (
        "Product URL Decision",
        "justifiable product URL",
        "Source, Evidence, Identity and Usability",
        "Overall conclusion",
        "Decision summary",
        "Source",
        "Evidence",
        "Identity",
        "Usability",
        "Why this decision is justifiable",
        "Search work completed",
        "Candidate URL decisions",
        "Review evidence and decision details",
        "Find justifiable URL",
    ):
        assert token in source

    for forbidden in (
        "Runtime controls",
        'st.text_input("Run ID"',
        'st.text_input("Feature set"',
        "Alternative hypotheses",
        "Source evidence",
    ):
        assert forbidden.lower() not in source.lower()


def test_ui_loads_cleanly_when_agent_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product URL Decision" in rendered
    assert "Agent unavailable" in rendered
    assert any(button.disabled for button in app.button)


def test_no_url_outcome_is_explicit_and_quantifies_work(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _no_url_result()
    app.session_state["run_elapsed_seconds"] = 2.4
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "No justifiable product URL found" in rendered
    assert "LEGO Star Wars R2-D2 75379" in rendered
    assert "Overall conclusion" in rendered
    assert "Search work completed" in rendered
    assert "Results reviewed" in rendered
    assert "No URL is displayed because" in rendered
    assert "Technical execution failure" not in rendered


def test_usable_url_is_the_primary_result(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _usable_url_result()
    app.session_state["run_elapsed_seconds"] = 2.4
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Justifiable product URL found" in rendered
    assert "Selected source: Manufacturer" in rendered
    assert "Ready" in rendered
    assert "Why this decision is justifiable" in rendered


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


def test_ui_document_defines_decision_first_contract() -> None:
    text = DOC.read_text(encoding="utf-8")
    for token in (
        "Product URL Decision",
        "Primary outcome",
        "justifiable URL",
        "Source",
        "Evidence",
        "Identity",
        "Usability",
        "No justifiable URL",
        "Search work completed",
        "Review evidence and decision details",
        "Fast",
        "Standard",
        "Deep review",
    ):
        assert token in text
    assert "URLs are evidence locations" not in text
