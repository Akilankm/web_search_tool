from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import requests
import streamlit as st


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "docker-compose.yml").is_file() and (
            candidate / "src" / "product_evidence_harness"
        ).is_dir():
            return candidate
    raise RuntimeError("Could not locate the web_search_tool repository root")


PROJECT_ROOT = find_project_root()
for required in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if required not in sys.path:
        sys.path.insert(0, required)

from product_evidence_harness.demo_runtime_options import (  # noqa: E402
    DEMO_OPTION_SPECS,
    default_demo_runtime_options,
)


AGENT_URL = os.getenv("PRODUCT_AGENT_URL", "http://127.0.0.1:8788").rstrip("/")
EXPECTED_RUNTIME = "belief-url-resolution-v8-leadership-demo"
TERMINAL_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}

CAPABILITIES = (
    ("Product interpretation", "Converts incomplete vendor text into an explicit identity hypothesis and unresolved distinctions."),
    ("Manufacturer-first truth", "Prefers an exact official manufacturer page only after every production gate passes."),
    ("Adaptive multi-engine search", "Uses bounded search credits, observed evidence and rejected candidates to choose the next search action."),
    ("Rendered browser investigation", "Opens promising direct pages and executes controlled observe-plan-act evidence collection."),
    ("Multimodal evidence", "Uses rendered text, structured data, screenshots, product galleries and package images."),
    ("Exact-product safety", "Checks identifiers, model, variant, form, size, quantity and pack before URL promotion."),
    ("Requested-feature coverage", "Requires the selected page to support the feature schema used for downstream coding."),
    ("Durable URL enforcement", "Rejects indirect, signed, session-bound, expiring, category and search-result URLs."),
    ("Controlled fallback", "Uses a qualified retailer or global source when no manufacturer page passes every gate."),
    ("No-fabrication outcome", "Returns a structured review result when no safe direct product page can be found."),
    ("Human-comparable judgment trace", "Records evidence, rule, judgment, alternatives, rejection reason and next action in sequence."),
    ("Artifact-first governance", "Persists result JSON, search trace, browser evidence, source selection and review artifacts per product."),
)

PRESETS: dict[str, dict[str, int]] = {
    "Fast leadership demo": {
        "serpapi_credits": 2,
        "full_scrapes": 3,
        "scrapes_per_domain": 1,
        "planner_candidates": 6,
        "agentic_candidates": 2,
        "browser_turns_per_candidate": 3,
        "browser_actions_per_candidate": 4,
        "images_in_reasoning": 6,
    },
    "Balanced production demo": default_demo_runtime_options(),
    "Deep evidence demo": {
        "serpapi_credits": 3,
        "full_scrapes": 10,
        "scrapes_per_domain": 3,
        "planner_candidates": 15,
        "agentic_candidates": 6,
        "browser_turns_per_candidate": 8,
        "browser_actions_per_candidate": 12,
        "images_in_reasoning": 12,
    },
}

STAGE_PROGRESS = {
    "VALIDATING_INPUT": 0.05,
    "SEARCHING": 0.15,
    "PRODUCT_UNDERSTANDING": 0.18,
    "ADAPTIVE_SEARCH": 0.30,
    "SCRAPING": 0.48,
    "AGENTIC_BROWSER_INVESTIGATION": 0.65,
    "VALIDATING_PRIMARY_URL": 0.84,
    "WRITING_OUTPUTS": 0.94,
    "COMPLETED": 1.0,
    "REVIEW_REQUIRED": 1.0,
    "FAILED": 1.0,
}


st.set_page_config(
    page_title="Product Evidence Intelligence",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .block-container {padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px;}
    .hero {padding: 1.35rem 1.6rem; border: 1px solid rgba(128,128,128,.22); border-radius: 18px; margin-bottom: 1rem; background: linear-gradient(135deg, rgba(33,150,243,.08), rgba(156,39,176,.05));}
    .hero h1 {margin: 0; font-size: 2.05rem;}
    .hero p {margin: .45rem 0 0 0; opacity: .82; font-size: 1.02rem;}
    .capability {border: 1px solid rgba(128,128,128,.22); border-radius: 14px; padding: .9rem 1rem; min-height: 128px; margin-bottom: .8rem;}
    .capability strong {font-size: .98rem;}
    .small-muted {font-size: .82rem; opacity: .72;}
    .status-ok {padding: .65rem .8rem; border-radius: 10px; background: rgba(46,160,67,.12); border: 1px solid rgba(46,160,67,.28);}
    .status-review {padding: .8rem 1rem; border-radius: 12px; background: rgba(245,158,11,.12); border: 1px solid rgba(245,158,11,.32);}
    .status-fail {padding: .8rem 1rem; border-radius: 12px; background: rgba(220,38,38,.10); border: 1px solid rgba(220,38,38,.28);}
    div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.18); padding: .7rem .8rem; border-radius: 12px;}
</style>
""",
    unsafe_allow_html=True,
)


def api_json(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    response = requests.request(
        method,
        f"{AGENT_URL}{path}",
        json=payload,
        timeout=timeout,
    )
    if not response.ok:
        detail = response.text[:4000]
        raise RuntimeError(f"Agent API returned HTTP {response.status_code}: {detail}")
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Agent API returned a non-object JSON response")
    return data


@st.cache_data(ttl=5, show_spinner=False)
def runtime_health() -> dict[str, Any]:
    return api_json("GET", "/health", timeout=15)


def clean_optional(value: str) -> str | None:
    text = value.strip()
    return text or None


def stage_progress(stage: str, status: str) -> float:
    upper = (stage or status or "").upper()
    for key, value in STAGE_PROGRESS.items():
        if key in upper:
            return value
    return 0.10


def host_artifact_dir(result: Mapping[str, Any]) -> Path | None:
    row_id = str((result.get("product") or {}).get("row_id") or "").strip()
    return PROJECT_ROOT / "data" / "artifacts" / row_id if row_id else None


def compact(value: Any, limit: int = 260) -> str:
    if value in (None, "", [], {}, ()):
        return "—"
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def url_link(label: str, url: str | None) -> None:
    if url:
        st.link_button(label, url, use_container_width=True)
    else:
        st.button(label, disabled=True, use_container_width=True)


def result_metric(label: str, value: Any, help_text: str | None = None) -> None:
    st.metric(label, compact(value, 80), help=help_text)


def capability_grid() -> None:
    st.subheader("Full platform capability")
    columns = st.columns(4)
    for index, (title, description) in enumerate(CAPABILITIES):
        with columns[index % 4]:
            st.markdown(
                f'<div class="capability"><strong>{title}</strong><p class="small-muted">{description}</p></div>',
                unsafe_allow_html=True,
            )


def initialize_budget_state(preset: str) -> None:
    if st.session_state.get("active_budget_preset") == preset:
        return
    for key, value in PRESETS[preset].items():
        st.session_state[f"budget_{key}"] = value
    st.session_state["active_budget_preset"] = preset


def budget_controls() -> dict[str, int]:
    st.sidebar.subheader("Run budget")
    preset = st.sidebar.selectbox("Budget profile", tuple(PRESETS), index=1)
    initialize_budget_state(preset)
    options: dict[str, int] = {}
    for spec in DEMO_OPTION_SPECS:
        options[spec.key] = int(
            st.sidebar.number_input(
                spec.label,
                min_value=spec.minimum,
                max_value=spec.maximum,
                step=1,
                key=f"budget_{spec.key}",
                help=spec.help_text,
            )
        )
    st.sidebar.caption(
        "These are per-job limits. The UI cannot change credentials, identity gates, URL durability, source policy or the no-fabrication rule."
    )
    return options


def runtime_sidebar() -> dict[str, Any] | None:
    st.sidebar.header("Runtime")
    try:
        health = runtime_health()
    except Exception as exc:
        st.sidebar.error("Agent unavailable")
        st.sidebar.code("./scripts/azureml_startup.sh --clean-build")
        with st.sidebar.expander("Connection detail"):
            st.code(str(exc))
        return None

    contract = str(health.get("runtime_contract_version") or "unknown")
    healthy = health.get("status") == "healthy"
    if healthy and contract == EXPECTED_RUNTIME:
        st.sidebar.markdown('<div class="status-ok"><strong>● Runtime ready</strong></div>', unsafe_allow_html=True)
    elif healthy:
        st.sidebar.warning(f"Stale runtime: {contract}")
    else:
        st.sidebar.error(f"Runtime status: {health.get('status')}")

    browser = health.get("browser_service") or {}
    st.sidebar.caption(f"Agent: {AGENT_URL}")
    st.sidebar.caption(f"Contract: {contract}")
    st.sidebar.caption(f"Browser: {browser.get('status') or 'unknown'}")
    st.sidebar.caption(
        "Multimodal: enabled" if health.get("business_judgement_review_artifact") else "Multimodal status unavailable"
    )
    return health


def render_pipeline() -> None:
    st.markdown(
        """
```text
Product input
→ identity interpretation and uncertainty
→ manufacturer-first adaptive search
→ retailer / country / global fallback
→ candidate preflight and full-page extraction
→ controlled rendered-browser investigation
→ text + structured data + screenshots + images
→ exact-product and requested-feature gates
→ durable source-authority selection
→ final URL or explicit no-safe-URL review outcome
→ human-comparable judgment artifact
```
"""
    )


def render_result(result: dict[str, Any], elapsed_seconds: float | None = None) -> None:
    status = str(result.get("job_status") or "UNKNOWN")
    delivery = dict(result.get("url_delivery") or {})
    acceptance = dict(result.get("primary_url_acceptance") or {})
    selection = dict(result.get("source_selection") or {})
    search = dict(result.get("search") or {})
    browser = dict(result.get("agentic_browser") or {})
    outcome = dict(result.get("resolution_outcome") or {})
    run_configuration = dict(result.get("run_configuration") or {})
    effective_budget = dict(run_configuration.get("effective_runtime_options") or {})

    st.divider()
    if status == "COMPLETED":
        st.markdown('<div class="status-ok"><strong>URL identification completed</strong><br>The selected direct page passed the strict production gates.</div>', unsafe_allow_html=True)
    elif status == "REVIEW_REQUIRED" and outcome:
        st.markdown(
            '<div class="status-review"><strong>No safe direct URL was found within the selected budget.</strong><br>The system preserved the complete trace, refused to fabricate a URL, and returned a controlled review outcome.</div>',
            unsafe_allow_html=True,
        )
    elif status == "REVIEW_REQUIRED":
        st.markdown('<div class="status-review"><strong>Human review required</strong><br>A real direct reference was preserved, but one or more decisions require confirmation.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-fail"><strong>Execution failed</strong><br>This represents a technical or contract failure, not a controlled no-match outcome.</div>', unsafe_allow_html=True)

    st.subheader("Executive decision")
    metric_columns = st.columns(6)
    with metric_columns[0]:
        result_metric("Status", status)
    with metric_columns[1]:
        result_metric("Primary role", result.get("primary_url_role"))
    with metric_columns[2]:
        result_metric("Strictly verified", delivery.get("strictly_verified"))
    with metric_columns[3]:
        result_metric("Search credits", f"{search.get('serpapi_requests_used', 0)} / {search.get('serpapi_request_limit', effective_budget.get('serpapi_credits', '—'))}")
    with metric_columns[4]:
        result_metric("Browser candidates", browser.get("candidate_urls_admitted", 0))
    with metric_columns[5]:
        result_metric("Elapsed", f"{elapsed_seconds:.1f}s" if elapsed_seconds is not None else "—")

    url_columns = st.columns(3)
    with url_columns[0]:
        url_link("Open primary product URL", result.get("primary_url"))
    with url_columns[1]:
        url_link("Open manufacturer URL", result.get("manufacturer_url"))
    with url_columns[2]:
        url_link("Open retailer URL", result.get("retailer_url"))

    decision_tab, budget_tab, evidence_tab, judgment_tab, artifacts_tab = st.tabs(
        ["Decision", "Search & budget", "Evidence & images", "Judgment trace", "Artifacts"]
    )

    with decision_tab:
        identity = dict(result.get("product_identification") or {})
        hypothesis = identity.get("leading_hypothesis") or identity.get("selected_hypothesis") or {}
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("#### Interpreted product")
            st.json(hypothesis or identity, expanded=True)
        with d2:
            st.markdown("#### Source decision")
            source_rows = [
                {"field": "Selection policy", "value": selection.get("policy")},
                {"field": "Selection reason", "value": selection.get("selection_reason")},
                {"field": "Source tier", "value": selection.get("source_tier_name")},
                {"field": "Manufacturer conditional", "value": selection.get("manufacturer_priority_is_conditional")},
                {"field": "Delivery status", "value": delivery.get("status")},
            ]
            st.dataframe(pd.DataFrame(source_rows), hide_index=True, use_container_width=True)

        gate_names = (
            "browser_openable",
            "text_scrapable",
            "rendered_product_verified",
            "exact_product_verified",
            "full_feature_coverage",
            "durable_url",
            "accepted",
        )
        gate_rows = [
            {"Production gate": name.replace("_", " ").title(), "Passed": acceptance.get(name)}
            for name in gate_names
            if name in acceptance
        ]
        if gate_rows:
            st.markdown("#### Non-negotiable acceptance gates")
            st.dataframe(pd.DataFrame(gate_rows), hide_index=True, use_container_width=True)

        if outcome:
            st.markdown("#### Controlled review action")
            st.write(outcome.get("message"))
            for action in outcome.get("suggested_next_actions") or []:
                st.write(f"• {action}")

    with budget_tab:
        requested = dict(run_configuration.get("requested_runtime_options") or {})
        catalog = {
            item["key"]: item
            for item in run_configuration.get("option_catalog") or []
            if isinstance(item, dict) and item.get("key")
        }
        budget_rows = []
        for key, effective in effective_budget.items():
            item = catalog.get(key, {})
            budget_rows.append(
                {
                    "Budget control": item.get("label") or key.replace("_", " ").title(),
                    "Requested": requested.get(key, "environment default"),
                    "Effective": effective,
                    "Allowed range": (
                        f"{item.get('minimum')}–{item.get('maximum')}"
                        if item
                        else "—"
                    ),
                }
            )
        st.dataframe(pd.DataFrame(budget_rows), hide_index=True, use_container_width=True)

        stages = search.get("stages") or []
        if stages:
            stage_rows = []
            for index, item in enumerate(stages, start=1):
                if not isinstance(item, Mapping):
                    continue
                stage_rows.append(
                    {
                        "#": index,
                        "Stage": item.get("name") or item.get("stage") or item.get("market_stage"),
                        "Engine": item.get("engine"),
                        "Scope": item.get("scope"),
                        "Query": item.get("query"),
                        "Results": item.get("results_returned") or item.get("result_count") or 0,
                        "New URLs": item.get("new_candidate_urls") or item.get("candidate_count") or 0,
                        "Qualified": item.get("candidates_qualified") or item.get("qualified_candidates") or 0,
                        "Reason": item.get("reason"),
                    }
                )
            st.markdown("#### Search route")
            st.dataframe(pd.DataFrame(stage_rows), hide_index=True, use_container_width=True)

        safety = run_configuration.get("safety_contract") or {}
        if safety:
            st.markdown("#### Locked safety policy")
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Control": key.replace("_", " ").title(), "Value": value}
                        for key, value in safety.items()
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )

    with evidence_tab:
        review = dict(result.get("business_judgement_review") or {})
        visual = dict(review.get("visual_evidence_summary") or {})
        visual_rows = [
            {"Visual measure": key.replace("_", " ").title(), "Recorded value": compact(value)}
            for key, value in visual.items()
        ]
        if visual_rows:
            st.markdown("#### Visual evidence impact")
            st.dataframe(pd.DataFrame(visual_rows), hide_index=True, use_container_width=True)

        e1, e2, e3, e4 = st.columns(4)
        with e1:
            result_metric("Browser evidence records", len(result.get("browser_evidence") or []))
        with e2:
            result_metric("Candidate investigations", len(result.get("candidate_investigations") or []))
        with e3:
            result_metric("Feature assessments", len(result.get("feature_assessments") or []))
        with e4:
            result_metric("Multimodal ready", result.get("multimodal_ready"))

        assessments = result.get("feature_assessments") or []
        candidate_rows = []
        for item in assessments:
            if not isinstance(item, Mapping):
                continue
            candidate_rows.append(
                {
                    "URL": item.get("url"),
                    "Identity": item.get("identity_status"),
                    "Identity accepted": item.get("identity_accepted"),
                    "Coverage": item.get("coverage"),
                    "Missing features": compact(item.get("missing_features")),
                    "Conflicts": compact(item.get("conflicting_features")),
                    "Rejection reasons": compact(item.get("rejection_reasons")),
                }
            )
        if candidate_rows:
            st.markdown("#### Candidate evidence summary")
            st.dataframe(pd.DataFrame(candidate_rows), hide_index=True, use_container_width=True)

    with judgment_tab:
        review = dict(result.get("business_judgement_review") or {})
        steps = review.get("steps") or []
        step_rows = []
        for item in steps:
            if not isinstance(item, Mapping):
                continue
            step_rows.append(
                {
                    "Step": item.get("sequence_number"),
                    "Stage": item.get("decision_stage"),
                    "Business question": item.get("business_question"),
                    "Evidence": compact(item.get("evidence_considered"), 600),
                    "Rule": item.get("business_rule_applied"),
                    "Agent judgment": item.get("agent_judgement"),
                    "Next action": item.get("effect_on_next_action"),
                    "Visual": item.get("visual_evidence_used"),
                    "Outcome": item.get("final_outcome"),
                }
            )
        if step_rows:
            st.dataframe(pd.DataFrame(step_rows), hide_index=True, use_container_width=True, height=520)
        else:
            st.info("No structured judgment steps were returned.")

    with artifacts_tab:
        artifact_root = host_artifact_dir(result)
        if artifact_root and artifact_root.is_dir():
            files = sorted(path for path in artifact_root.rglob("*") if path.is_file())
            inventory = [
                {
                    "Artifact": str(path.relative_to(artifact_root)),
                    "Size KB": round(path.stat().st_size / 1024, 2),
                }
                for path in files
            ]
            st.caption(str(artifact_root))
            st.dataframe(pd.DataFrame(inventory), hide_index=True, use_container_width=True)

            review_path = artifact_root / "business_judgement_review.md"
            if review_path.is_file():
                review_text = review_path.read_text(encoding="utf-8", errors="replace")
                st.download_button(
                    "Download human review Markdown",
                    review_text,
                    file_name=review_path.name,
                    mime="text/markdown",
                    use_container_width=True,
                )
                with st.expander("Preview human review artifact"):
                    st.markdown(review_text)

            result_path = artifact_root / "orchestrated_result.json"
            if result_path.is_file():
                st.download_button(
                    "Download complete result JSON",
                    result_path.read_bytes(),
                    file_name=result_path.name,
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            st.warning("The host artifact directory is not available from this Streamlit process.")

        with st.expander("Technical result JSON"):
            st.json(result, expanded=False)


st.markdown(
    """
<div class="hero">
  <h1>Product Evidence Intelligence</h1>
  <p>Leadership demo for exact-product identification, multimodal evidence acquisition, governed URL selection and human-comparable agent decisions.</p>
</div>
""",
    unsafe_allow_html=True,
)

health = runtime_sidebar()
runtime_options = budget_controls()

if "demo_row_id" not in st.session_state:
    st.session_state.demo_row_id = f"DEMO-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

with st.form("product_demo_form", clear_on_submit=False):
    st.subheader("Product input")
    main_text = st.text_area(
        "Main product text *",
        placeholder="Paste the incomplete vendor or retailer product description",
        height=100,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        country_code = st.text_input("Country code *", value="CH", max_chars=2)
        retailer_name = st.text_input("Retailer name", placeholder="Optional")
    with c2:
        ean = st.text_input("EAN / GTIN", placeholder="Optional; preserved as text")
        language_code = st.text_input("Language code", placeholder="Optional, e.g. de")
    with c3:
        row_id = st.text_input("Run ID", value=st.session_state.demo_row_id)
        feature_set = st.text_input("Feature set", value="toy_features")

    submitted = st.form_submit_button(
        "Run governed product resolution",
        type="primary",
        use_container_width=True,
        disabled=health is None or str((health or {}).get("runtime_contract_version")) != EXPECTED_RUNTIME,
    )

if submitted:
    if not main_text.strip():
        st.error("Main product text is required.")
    elif len(country_code.strip()) != 2:
        st.error("Country code must contain exactly two letters.")
    else:
        st.session_state.demo_row_id = row_id.strip()
        product = {
            "row_id": row_id.strip(),
            "main_text": main_text.strip(),
            "country_code": country_code.strip().upper(),
            "retailer_name": clean_optional(retailer_name),
            "ean": clean_optional(ean),
            "language_code": clean_optional(language_code.lower()),
        }
        payload = {
            "product": product,
            "feature_set": feature_set.strip() or "toy_features",
            "runtime_options": runtime_options,
        }

        status_box = st.empty()
        progress_bar = st.progress(0.02, text="Submitting product evidence job")
        started = time.monotonic()
        try:
            job = api_json("POST", "/v1/jobs", payload=payload, timeout=30)
            job_id = str(job["job_id"])
            last_signature: tuple[Any, ...] | None = None
            while True:
                status = api_json("GET", f"/v1/jobs/{job_id}", timeout=20)
                signature = (status.get("status"), status.get("stage"), status.get("message"))
                if signature != last_signature:
                    status_box.info(
                        f"{status.get('status')} · {status.get('stage') or 'working'} · {status.get('message') or ''}"
                    )
                    progress_bar.progress(
                        stage_progress(str(status.get("stage") or ""), str(status.get("status") or "")),
                        text=str(status.get("stage") or status.get("status") or "Working"),
                    )
                    last_signature = signature
                if status.get("status") in TERMINAL_STATUSES:
                    if status.get("status") == "FAILED":
                        raise RuntimeError(status.get("error") or status.get("message") or "Job failed")
                    break
                time.sleep(1.5)

            result = api_json("GET", f"/v1/jobs/{job_id}/result", timeout=120)
            elapsed = time.monotonic() - started
            st.session_state.demo_result = result
            st.session_state.demo_elapsed_seconds = elapsed
            st.session_state.demo_job_id = job_id
            progress_bar.progress(1.0, text="Decision package ready")
            status_box.empty()
        except Exception as exc:
            elapsed = time.monotonic() - started
            progress_bar.empty()
            status_box.empty()
            st.markdown('<div class="status-fail"><strong>The demo run could not complete.</strong><br>The error is preserved below; no result has been fabricated.</div>', unsafe_allow_html=True)
            with st.expander("Technical error detail", expanded=True):
                st.code(f"{type(exc).__name__}: {exc}")
                st.caption(f"Elapsed before failure: {elapsed:.1f}s")

if "demo_result" in st.session_state:
    render_result(
        st.session_state.demo_result,
        st.session_state.get("demo_elapsed_seconds"),
    )
else:
    capability_grid()
    st.subheader("Governed workflow")
    render_pipeline()
    st.info("Enter one product above. The app uses the same agent API, feature schema, evidence pipeline, URL gates and artifacts as the supported notebooks.")
