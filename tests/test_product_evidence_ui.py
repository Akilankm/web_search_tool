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
        app.code,
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
        "primary_url_role": "NONE",
        "manufacturer_url": None,
        "retailer_url": None,
        "url_delivery": {
            "required": True,
            "delivered": False,
            "strictly_verified": False,
            "url": None,
            "status": "NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH",
        },
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
        "source_selection": {"source_role": "NONE"},
        "resolution_outcome": {
            "message": "No direct product candidate remained after recovery.",
            "suggested_next_actions": ["Provide a known retailer URL."],
        },
        "search": {
            "market_decision_path": [
                "manufacturer_primary",
                "country_alternative",
                "global_fallback",
            ],
            "serpapi_requests_used": 3,
            "serpapi_request_limit": 3,
            "stages": [
                {
                    "name": "manufacturer_primary",
                    "results_returned": 20,
                    "new_candidate_urls": 5,
                    "candidates_qualified": 2,
                    "candidates_scraped": 1,
                }
            ],
        },
        "agentic_browser": {"candidate_investigations_completed": 2},
        "business_judgement_review": {"steps": []},
    }


def _usable_url_result(*, strict: bool = True) -> dict:
    result = _no_url_result()
    url = "https://www.lego.com/product/75379"
    result.update(
        {
            "job_status": "COMPLETED" if strict else "REVIEW_REQUIRED",
            "coding_ready": strict,
            "primary_url": url,
            "primary_url_role": "OFFICIAL_MANUFACTURER",
            "manufacturer_url": url,
            "url_delivery": {
                "required": True,
                "delivered": True,
                "strictly_verified": strict,
                "url": url,
                "status": (
                    "STRICT_VERIFIED_PRODUCT_URL"
                    if strict
                    else "BEST_AVAILABLE_REVIEW_URL"
                ),
            },
            "source_selection": {
                "source_role": "MANUFACTURER",
                "source_tier_name": "GLOBAL_MANUFACTURER",
                "selection_reason": "Official manufacturer page selected.",
            },
            "primary_url_acceptance": {
                "accepted": strict,
                "browser_openable": True,
                "text_scrapable": True,
                "rendered_product_verified": True,
                "exact_product_verified": True,
                "full_feature_coverage": strict,
                "durable_url": True,
                "reasons": ["EXACT_PRODUCT_IDENTITY", "DURABLE_URL"],
            },
            "evidence_set": {"required_coverage": 1.0 if strict else 0.75},
        }
    )
    return result


def test_ui_is_parseable_and_url_delivery_first() -> None:
    source = APP.read_text(encoding="utf-8")
    ast.parse(source, filename=str(APP))

    for token in (
        "Product URL Finder",
        "strongest usable **product URL**",
        "Source, Evidence, Identity and Usability",
        "Open product URL",
        "URL usability",
        "Justification",
        "Review details",
        "Find product URL",
        "URL delivery failed",
        "This run is not a successful output",
        "Focused",
        "Standard",
        "Extended",
        "belief-url-resolution-v11-url-delivery-first",
    ):
        assert token in source

    for forbidden in (
        "No justifiable product URL found",
        "Search work completed",
        "What can improve the next attempt",
        "Runtime controls",
        'st.text_input("Run ID"',
        'st.text_input("Feature set"',
    ):
        assert forbidden.lower() not in source.lower()


def test_ui_loads_cleanly_when_agent_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product URL Finder" in rendered
    assert "Agent unavailable" in rendered
    assert any(button.disabled for button in app.button)


def test_no_url_is_rendered_as_failed_delivery_not_normal_result(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _no_url_result()
    app.session_state["run_elapsed_seconds"] = 2.4
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "URL delivery failed — escalation required" in rendered
    assert "The required product URL was not delivered" in rendered
    assert "This run is not a successful output" in rendered
    assert "No justifiable product URL found" not in rendered


def test_verified_url_is_the_primary_result(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _usable_url_result(strict=True)
    app.session_state["run_elapsed_seconds"] = 2.4
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product URL delivered" in rendered
    assert "https://www.lego.com/product/75379" in rendered
    assert "Source: Manufacturer" in rendered
    assert "URL delivery failed" not in rendered


def test_review_url_is_still_delivered(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _usable_url_result(strict=False)
    app.run()

    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product URL delivered — review recommended" in rendered
    assert "https://www.lego.com/product/75379" in rendered
    assert "The strongest real direct product URL was delivered" in rendered


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


def test_ui_document_defines_url_delivery_first_contract() -> None:
    text = DOC.read_text(encoding="utf-8")
    for token in (
        "Product URL Finder",
        "Primary deliverable",
        "best available review URL",
        "Source",
        "Evidence",
        "Identity",
        "Usability",
        "URL delivery failure",
        "exceptional escalation",
        "Focused",
        "Standard",
        "Extended",
        "belief-url-resolution-v11-url-delivery-first",
    ):
        assert token in text
