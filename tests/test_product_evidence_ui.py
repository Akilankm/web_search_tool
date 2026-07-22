from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import requests
from streamlit.testing.v1 import AppTest

from src.product_evidence_harness.url_delivery_summary import build_url_delivery_summary


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


def _result(*, url: str | None, strict: bool) -> dict:
    result = {
        "job_status": "COMPLETED" if url and strict else "REVIEW_REQUIRED",
        "coding_ready": bool(url and strict),
        "product": {"row_id": "ROW-URL", "main_text": "LEGO R2-D2 75379"},
        "product_identification": {
            "resolution_status": "EXACT",
            "leading_hypothesis": {
                "canonical_name": "LEGO Star Wars R2-D2 75379",
                "posterior_probability": 0.96,
            },
            "claims": [{"field": "model", "value": "75379", "status": "WEB_VERIFIED"}],
            "evidence_ledger": [
                {
                    "field": "model",
                    "value": "75379",
                    "polarity": "SUPPORTS",
                    "source_url": url,
                }
            ],
            "hypotheses": [],
            "uncertainties": [],
            "unknowns": [],
        },
        "primary_url": url,
        "primary_url_role": "OFFICIAL_MANUFACTURER" if url else "NONE",
        "manufacturer_url": url,
        "retailer_url": None,
        "url_delivery": {
            "required": True,
            "delivered": bool(url),
            "strictly_verified": strict,
            "url": url,
            "status": (
                "STRICT_VERIFIED_PRODUCT_URL"
                if url and strict
                else "BEST_AVAILABLE_REVIEW_URL"
                if url
                else "NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH"
            ),
        },
        "source_selection": {
            "source_role": "MANUFACTURER" if url else "NONE",
            "source_tier_name": "GLOBAL_MANUFACTURER" if url else "NONE",
        },
        "primary_url_acceptance": {
            "accepted": strict,
            "browser_openable": bool(url),
            "text_scrapable": bool(url),
            "rendered_product_verified": bool(url),
            "exact_product_verified": bool(url),
            "full_feature_coverage": strict,
            "durable_url": bool(url),
        },
        "evidence_set": {"required_coverage": 1.0 if strict else 0.75 if url else 0.0},
        "search": {
            "market_decision_path": ["manufacturer_primary", "global_fallback"],
            "serpapi_requests_used": 3,
            "serpapi_request_limit": 3,
            "stages": [{"results_returned": 20, "new_candidate_urls": 5}],
        },
        "business_judgement_review": {"steps": []},
    }
    result["executive_summary"] = build_url_delivery_summary(result)
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


def test_verified_url_is_first_result(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _result(url="https://www.lego.com/product/75379", strict=True)
    app.run()
    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product URL delivered" in rendered
    assert "https://www.lego.com/product/75379" in rendered
    assert "Source" in rendered
    assert "Evidence" in rendered
    assert "Identity" in rendered
    assert "Usability" in rendered


def test_review_url_is_still_displayed(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _result(url="https://shop.example/product/75379", strict=False)
    app.run()
    assert app.exception == []
    rendered = _rendered_text(app)
    assert "Product URL delivered — review recommended" in rendered
    assert "https://shop.example/product/75379" in rendered
    assert "strongest real direct product URL was delivered" in rendered


def test_empty_url_is_failed_delivery(monkeypatch) -> None:
    monkeypatch.setattr(requests, "request", _unavailable)
    app = AppTest.from_file(str(APP), default_timeout=30)
    app.session_state["run_result"] = _result(url=None, strict=False)
    app.run()
    assert app.exception == []
    rendered = _rendered_text(app)
    assert "URL delivery failed — escalation required" in rendered
    assert "The required product URL was not delivered" in rendered
    assert "not a successful output" in rendered


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
