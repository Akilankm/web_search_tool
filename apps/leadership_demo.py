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
from product_evidence_harness.numeric_safety import safe_int  # noqa: E402


AGENT_URL = os.getenv("PRODUCT_AGENT_URL", "http://127.0.0.1:8788").rstrip("/")
EXPECTED_RUNTIME = "belief-url-resolution-v8-leadership-demo"
TERMINAL_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}
MAX_POLL_SECONDS = 30 * 60

PRESETS: dict[str, dict[str, int]] = {
    "Fast demo": {
        "serpapi_credits": 2,
        "full_scrapes": 3,
        "scrapes_per_domain": 1,
        "planner_candidates": 6,
        "agentic_candidates": 2,
        "browser_turns_per_candidate": 3,
        "browser_actions_per_candidate": 4,
        "images_in_reasoning": 6,
    },
    "Balanced": default_demo_runtime_options(),
    "Deep evidence": {
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

WORKFLOW = (
    ("INPUT", "Input", "Product text + market context"),
    ("UNDERSTAND", "Interpret", "Identity hypothesis + uncertainty"),
    ("SEARCH", "Search", "Manufacturer → local → global"),
    ("INVESTIGATE", "Investigate", "Rendered pages + images"),
    ("VERIFY", "Verify", "Identity + features + durability"),
    ("SELECT", "Select", "Authority-aware URL decision"),
    ("EXPLAIN", "Explain", "Business judgment artifact"),
)

STAGE_TO_FLOW = {
    "VALIDATING_INPUT": "INPUT",
    "PRODUCT_UNDERSTANDING": "UNDERSTAND",
    "SEARCHING": "SEARCH",
    "ADAPTIVE_SEARCH": "SEARCH",
    "SCRAPING": "INVESTIGATE",
    "AGENTIC_BROWSER_INVESTIGATION": "INVESTIGATE",
    "VALIDATING_PRIMARY_URL": "VERIFY",
    "WRITING_OUTPUTS": "EXPLAIN",
    "COMPLETED": "EXPLAIN",
    "REVIEW_REQUIRED": "EXPLAIN",
    "FAILED": "EXPLAIN",
}

STAGE_PROGRESS = {
    "VALIDATING_INPUT": 0.05,
    "PRODUCT_UNDERSTANDING": 0.16,
    "SEARCHING": 0.24,
    "ADAPTIVE_SEARCH": 0.34,
    "SCRAPING": 0.48,
    "AGENTIC_BROWSER_INVESTIGATION": 0.66,
    "VALIDATING_PRIMARY_URL": 0.84,
    "WRITING_OUTPUTS": 0.94,
    "COMPLETED": 1.0,
    "REVIEW_REQUIRED": 1.0,
    "FAILED": 1.0,
}


st.set_page_config(
    page_title="Product Evidence Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1480px;}
.hero {padding: 1.25rem 1.5rem; border: 1px solid rgba(128,128,128,.22); border-radius: 18px; background: linear-gradient(130deg, rgba(26,115,232,.11), rgba(99,102,241,.05)); margin-bottom: .9rem;}
.hero h1 {font-size: 2rem; margin: 0;}
.hero p {margin: .35rem 0 0; opacity: .76;}
.flow-row {display: grid; grid-template-columns: repeat(7, 1fr); gap: .45rem; margin: .5rem 0 1rem;}
.flow-step {border: 1px solid rgba(128,128,128,.22); border-radius: 12px; padding: .72rem .68rem; min-height: 88px; position: relative;}
.flow-step.done {border-color: rgba(34,197,94,.55); background: rgba(34,197,94,.08);}
.flow-step.active {border-color: rgba(37,99,235,.75); background: rgba(37,99,235,.12); box-shadow: 0 0 0 1px rgba(37,99,235,.15);}
.flow-step.pending {opacity: .62;}
.flow-index {font-size: .72rem; opacity: .65;}
.flow-title {font-weight: 700; margin-top: .18rem;}
.flow-detail {font-size: .74rem; opacity: .72; margin-top: .22rem; line-height: 1.25;}
.trace-card {border-left: 4px solid rgba(37,99,235,.72); background: rgba(128,128,128,.055); border-radius: 10px; padding: .82rem 1rem; margin: .55rem 0;}
.trace-card.rejected {border-left-color: rgba(239,68,68,.75);}
.trace-card.selected {border-left-color: rgba(34,197,94,.8);}
.trace-stage {font-size: .72rem; letter-spacing: .04em; opacity: .64; text-transform: uppercase;}
.trace-question {font-weight: 700; margin: .15rem 0 .38rem;}
.trace-grid {display: grid; grid-template-columns: 1fr 1fr; gap: .35rem .9rem; font-size: .84rem;}
.gate-pass {padding: .55rem .7rem; border-radius: 10px; border: 1px solid rgba(34,197,94,.42); background: rgba(34,197,94,.08); text-align:center;}
.gate-fail {padding: .55rem .7rem; border-radius: 10px; border: 1px solid rgba(239,68,68,.42); background: rgba(239,68,68,.08); text-align:center;}
.status-ok {padding: .75rem .9rem; border-radius: 11px; background: rgba(34,197,94,.10); border: 1px solid rgba(34,197,94,.34);}
.status-review {padding: .75rem .9rem; border-radius: 11px; background: rgba(245,158,11,.10); border: 1px solid rgba(245,158,11,.36);}
.status-fail {padding: .75rem .9rem; border-radius: 11px; background: rgba(239,68,68,.09); border: 1px solid rgba(239,68,68,.32);}
div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.18); padding: .65rem .75rem; border-radius: 12px;}
@media (max-width: 1000px) {.flow-row {grid-template-columns: repeat(2, 1fr);} .trace-grid {grid-template-columns: 1fr;}}
</style>
""",
    unsafe_allow_html=True,
)


def api_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
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
    text = str(value or "").strip()
    return text or None


def compact(value: Any, limit: int = 260) -> str:
    if value in (None, "", [], {}, ()):
        return "—"
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def stage_progress(stage: str, status: str) -> float:
    upper = (stage or status or "").upper()
    for key, value in STAGE_PROGRESS.items():
        if key in upper:
            return value
    return 0.10


def flow_key(stage: str, status: str = "") -> str:
    upper = (stage or status or "").upper()
    for key, value in STAGE_TO_FLOW.items():
        if key in upper:
            return value
    return "INPUT"


def render_workflow(active: str | None = None, terminal: bool = False) -> None:
    active_key = active or ""
    keys = [item[0] for item in WORKFLOW]
    active_index = keys.index(active_key) if active_key in keys else -1
    cards = []
    for index, (key, title, detail) in enumerate(WORKFLOW, start=1):
        if terminal or (active_index >= 0 and index - 1 < active_index):
            state = "done"
        elif key == active_key:
            state = "active"
        else:
            state = "pending"
        cards.append(
            f'<div class="flow-step {state}"><div class="flow-index">0{index}</div>'
            f'<div class="flow-title">{title}</div><div class="flow-detail">{detail}</div></div>'
        )
    st.markdown('<div class="flow-row">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def initialize_budget_state(preset: str) -> None:
    preset_values = PRESETS[preset]
    preset_changed = st.session_state.get("active_budget_preset") != preset
    for spec in DEMO_OPTION_SPECS:
        state_key = f"budget_{spec.key}"
        fallback = preset_values.get(spec.key, spec.default)
        current = st.session_state.get(state_key)
        normalized = safe_int(
            current,
            fallback,
            minimum=spec.minimum,
            maximum=spec.maximum,
            field_name=state_key,
        )
        if preset_changed or current is None or normalized != current:
            st.session_state[state_key] = fallback if preset_changed else normalized
    st.session_state["active_budget_preset"] = preset


def budget_controls() -> dict[str, int]:
    st.sidebar.subheader("Controllable run budget")
    preset = st.sidebar.selectbox("Profile", tuple(PRESETS), index=1)
    initialize_budget_state(preset)
    options: dict[str, int] = {}
    for spec in DEMO_OPTION_SPECS:
        state_key = f"budget_{spec.key}"
        fallback = PRESETS[preset].get(spec.key, spec.default)
        raw = st.sidebar.number_input(
            spec.label,
            min_value=spec.minimum,
            max_value=spec.maximum,
            value=safe_int(
                st.session_state.get(state_key),
                fallback,
                minimum=spec.minimum,
                maximum=spec.maximum,
                field_name=state_key,
            ),
            step=1,
            key=state_key,
            help=spec.help_text,
        )
        options[spec.key] = safe_int(
            raw,
            fallback,
            minimum=spec.minimum,
            maximum=spec.maximum,
            field_name=state_key,
        )
    st.sidebar.caption("Per-job only. Identity, durability and no-fabrication rules remain locked.")
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
    browser = dict(health.get("browser_service") or {})
    ready = health.get("status") == "healthy" and contract == EXPECTED_RUNTIME
    if ready:
        st.sidebar.success("Runtime ready")
    elif health.get("status") == "healthy":
        st.sidebar.warning(f"Stale runtime: {contract}")
    else:
        st.sidebar.error(f"Runtime: {health.get('status') or 'unknown'}")
    st.sidebar.caption(f"Agent · {AGENT_URL}")
    st.sidebar.caption(f"Browser · {browser.get('status') or 'unknown'}")
    st.sidebar.caption(f"Contract · {contract}")
    return health


def host_artifact_dir(result: Mapping[str, Any]) -> Path | None:
    row_id = str((result.get("product") or {}).get("row_id") or "").strip()
    return PROJECT_ROOT / "data" / "artifacts" / row_id if row_id else None


def result_metric(label: str, value: Any, help_text: str | None = None) -> None:
    st.metric(label, compact(value, 80), help=help_text)


def url_link(label: str, url: str | None) -> None:
    if url:
        st.link_button(label, url, use_container_width=True)
    else:
        st.button(label, disabled=True, use_container_width=True)


def render_gates(acceptance: Mapping[str, Any]) -> None:
    gates = (
        ("browser_openable", "Browser"),
        ("text_scrapable", "Scrapable"),
        ("rendered_product_verified", "Product page"),
        ("exact_product_verified", "Exact identity"),
        ("full_feature_coverage", "Features"),
        ("durable_url", "Durable URL"),
    )
    visible = [(key, label) for key, label in gates if key in acceptance]
    if not visible:
        return
    columns = st.columns(len(visible))
    for column, (key, label) in zip(columns, visible):
        passed = bool(acceptance.get(key))
        with column:
            css = "gate-pass" if passed else "gate-fail"
            symbol = "PASS" if passed else "FAIL"
            st.markdown(
                f'<div class="{css}"><strong>{label}</strong><br><small>{symbol}</small></div>',
                unsafe_allow_html=True,
            )


def render_search_route(search: Mapping[str, Any]) -> None:
    stages = [item for item in search.get("stages") or [] if isinstance(item, Mapping)]
    if not stages:
        st.info("No stage-level search trace was returned.")
        return
    for index, item in enumerate(stages, start=1):
        title = item.get("name") or item.get("stage") or item.get("market_stage") or "search"
        engine = item.get("engine") or "—"
        query = item.get("query") or "—"
        results = item.get("results_returned") or item.get("result_count") or 0
        qualified = item.get("candidates_qualified") or item.get("qualified_candidates") or 0
        reason = item.get("reason") or "Stage evaluated under the bounded search policy."
        st.markdown(
            f"**{index}. {str(title).replace('_', ' ').title()}** · `{engine}` · "
            f"results **{results}** · qualified **{qualified}**  \n"
            f"Query: `{compact(query, 220)}`  \n"
            f"Decision: {compact(reason, 300)}"
        )


def render_judgment_trace(result: Mapping[str, Any]) -> None:
    review = dict(result.get("business_judgement_review") or {})
    steps = [item for item in review.get("steps") or [] if isinstance(item, Mapping)]
    if not steps:
        st.info("No structured business judgment sequence was returned.")
        return
    st.caption("Observable evidence → explicit rule → business judgment → next action. This is not hidden chain-of-thought.")
    for item in steps:
        status = str(item.get("judgement_status") or "").upper()
        outcome = str(item.get("final_outcome") or "").upper()
        css = "selected" if any(token in outcome for token in ("SELECT", "DELIVER", "ELIGIBLE")) else "rejected" if any(token in status + outcome for token in ("REJECT", "FAIL", "NOT_ELIGIBLE")) else ""
        st.markdown(
            f"""
<div class="trace-card {css}">
  <div class="trace-stage">Step {compact(item.get('sequence_number'), 20)} · {compact(item.get('decision_stage'), 100)}</div>
  <div class="trace-question">{compact(item.get('business_question'), 320)}</div>
  <div class="trace-grid">
    <div><strong>Evidence</strong><br>{compact(item.get('evidence_considered'), 520)}</div>
    <div><strong>Rule</strong><br>{compact(item.get('business_rule_applied'), 420)}</div>
    <div><strong>Judgment</strong><br>{compact(item.get('agent_judgement'), 420)}</div>
    <div><strong>Next action</strong><br>{compact(item.get('effect_on_next_action'), 420)}</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
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
    render_workflow("EXPLAIN", terminal=True)
    if status == "COMPLETED":
        st.markdown('<div class="status-ok"><strong>Accepted direct product URL</strong> · Every mandatory production gate passed.</div>', unsafe_allow_html=True)
    elif status == "REVIEW_REQUIRED" and outcome:
        st.markdown('<div class="status-review"><strong>No safe direct URL within the bounded run</strong> · Trace preserved; no URL fabricated.</div>', unsafe_allow_html=True)
    elif status == "REVIEW_REQUIRED":
        st.markdown('<div class="status-review"><strong>Human review required</strong> · A real reference exists, but one or more judgments need confirmation.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-fail"><strong>Technical execution failure</strong> · No business result was fabricated.</div>', unsafe_allow_html=True)

    st.subheader("Decision")
    metrics = st.columns(6)
    metric_values = (
        ("Status", status),
        ("Primary role", result.get("primary_url_role")),
        ("Strictly verified", delivery.get("strictly_verified")),
        ("Search credits", f"{search.get('serpapi_requests_used', 0)} / {search.get('serpapi_request_limit', effective_budget.get('serpapi_credits', '—'))}"),
        ("Browser candidates", browser.get("candidate_urls_admitted", 0)),
        ("Elapsed", f"{elapsed_seconds:.1f}s" if elapsed_seconds is not None else "—"),
    )
    for column, (label, value) in zip(metrics, metric_values):
        with column:
            result_metric(label, value)

    links = st.columns(3)
    with links[0]:
        url_link("Primary URL", result.get("primary_url"))
    with links[1]:
        url_link("Manufacturer URL", result.get("manufacturer_url"))
    with links[2]:
        url_link("Retailer URL", result.get("retailer_url"))

    render_gates(acceptance)

    decision_tab, trace_tab, evidence_tab, budget_tab, artifacts_tab = st.tabs(
        ["Decision flow", "Business judgments", "Evidence", "Budget", "Artifacts"]
    )

    with decision_tab:
        identity = dict(result.get("product_identification") or {})
        hypothesis = identity.get("leading_hypothesis") or identity.get("selected_hypothesis") or identity
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("#### Product interpretation")
            st.json(hypothesis, expanded=True)
        with d2:
            st.markdown("#### Source decision")
            st.markdown(
                f"**Policy:** {compact(selection.get('policy'))}  \n"
                f"**Reason:** {compact(selection.get('selection_reason'), 500)}  \n"
                f"**Source tier:** {compact(selection.get('source_tier_name'))}  \n"
                f"**Delivery:** {compact(delivery.get('status'))}"
            )
            if outcome:
                st.warning(compact(outcome.get("message") or outcome.get("code"), 600))
        st.markdown("#### Search-to-decision route")
        render_search_route(search)

    with trace_tab:
        render_judgment_trace(result)

    with evidence_tab:
        review = dict(result.get("business_judgement_review") or {})
        visual = dict(review.get("visual_evidence_summary") or {})
        visual_cols = st.columns(4)
        visual_values = (
            ("Visual assets", visual.get("visual_assets_collected", 0)),
            ("Screenshots", visual.get("screenshots_captured", 0)),
            ("Image inspections", visual.get("agentic_image_inspection_actions", 0)),
            ("Visual decision impact", visual.get("image_influenced_final_decision", "—")),
        )
        for column, (label, value) in zip(visual_cols, visual_values):
            with column:
                result_metric(label, value)

        assessments = [item for item in result.get("feature_assessments") or [] if isinstance(item, Mapping)]
        if assessments:
            st.markdown("#### Candidate evidence")
            for item in assessments:
                accepted = bool(item.get("identity_accepted")) and not (item.get("missing_features") or []) and not (item.get("conflicting_features") or [])
                icon = "✓" if accepted else "×"
                with st.expander(f"{icon} {compact(item.get('url'), 160)}", expanded=accepted):
                    st.markdown(
                        f"**Identity:** {compact(item.get('identity_status'))}  \n"
                        f"**Coverage:** {compact(item.get('coverage'))}  \n"
                        f"**Missing:** {compact(item.get('missing_features'))}  \n"
                        f"**Conflicts:** {compact(item.get('conflicting_features'))}  \n"
                        f"**Rejection:** {compact(item.get('rejection_reasons'), 700)}"
                    )
        else:
            st.info("No candidate feature assessments were returned.")

    with budget_tab:
        requested = dict(run_configuration.get("requested_runtime_options") or {})
        catalog = {
            item["key"]: item
            for item in run_configuration.get("option_catalog") or []
            if isinstance(item, dict) and item.get("key")
        }
        rows = []
        for key, effective in effective_budget.items():
            spec = catalog.get(key, {})
            rows.append(
                {
                    "Control": spec.get("label") or key.replace("_", " ").title(),
                    "Requested": requested.get(key, "default"),
                    "Effective": effective,
                    "Allowed": f"{spec.get('minimum')}–{spec.get('maximum')}" if spec else "—",
                }
            )
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        safety = dict(run_configuration.get("safety_contract") or {})
        if safety:
            st.caption("Locked governance controls")
            st.json(safety, expanded=False)

    with artifacts_tab:
        artifact_root = host_artifact_dir(result)
        if artifact_root and artifact_root.is_dir():
            files = sorted(path for path in artifact_root.rglob("*") if path.is_file())
            st.caption(str(artifact_root))
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Artifact": str(path.relative_to(artifact_root)),
                            "Size KB": round(path.stat().st_size / 1024, 2),
                        }
                        for path in files
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
            review_path = artifact_root / "business_judgement_review.md"
            if review_path.is_file():
                review_text = review_path.read_text(encoding="utf-8", errors="replace")
                st.download_button(
                    "Download business judgment review",
                    review_text,
                    file_name=review_path.name,
                    mime="text/markdown",
                    use_container_width=True,
                )
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
            st.warning("Artifact directory is not available to this Streamlit process.")
        with st.expander("Technical result JSON"):
            st.json(result, expanded=False)


def friendly_error(exc: Exception) -> tuple[str, str]:
    detail = f"{type(exc).__name__}: {exc}"
    if "int() argument must be" in detail and "NoneType" in detail:
        return (
            "A missing numeric value reached an older runtime path.",
            "Pull the latest master and rebuild the agent/browser images. The final runtime normalizes null and blank numeric values before execution.",
        )
    if "STALE_AGENT_IMAGE" in detail or "runtime_contract" in detail.lower():
        return (
            "The running agent does not match this UI.",
            "Run ./scripts/azureml_startup.sh --clean-build and reopen the app.",
        )
    return ("The governed run could not complete.", "Open the technical detail below; no result was fabricated.")


st.markdown(
    """
<div class="hero">
  <h1>Product Evidence Intelligence</h1>
  <p>From incomplete product text to a governed URL decision with an observable business-judgment sequence.</p>
</div>
""",
    unsafe_allow_html=True,
)

health = runtime_sidebar()
runtime_options = budget_controls()
render_workflow()

if "demo_row_id" not in st.session_state:
    st.session_state.demo_row_id = f"DEMO-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

with st.form("product_demo_form", clear_on_submit=False):
    st.subheader("Input")
    main_text = st.text_area(
        "Main product text *",
        placeholder="Paste the incomplete product description",
        height=95,
    )
    c1, c2, c3 = st.columns(3)
    with c1:
        country_code = st.text_input("Country code *", value="CH", max_chars=2)
        retailer_name = st.text_input("Retailer", placeholder="Optional")
    with c2:
        ean = st.text_input("EAN / GTIN", placeholder="Optional; preserved as text")
        language_code = st.text_input("Language", placeholder="Optional, e.g. de")
    with c3:
        row_id = st.text_input("Run ID", value=st.session_state.demo_row_id)
        feature_set = st.text_input("Feature set", value="toy_features")

    submitted = st.form_submit_button(
        "Run product resolution",
        type="primary",
        use_container_width=True,
        disabled=health is None
        or str((health or {}).get("runtime_contract_version")) != EXPECTED_RUNTIME,
    )

if submitted:
    if not main_text.strip():
        st.error("Main product text is required.")
    elif len(country_code.strip()) != 2 or not country_code.strip().isalpha():
        st.error("Country code must contain exactly two letters.")
    elif not row_id.strip():
        st.error("Run ID is required.")
    else:
        st.session_state.demo_row_id = row_id.strip()
        payload = {
            "product": {
                "row_id": row_id.strip(),
                "main_text": main_text.strip(),
                "country_code": country_code.strip().upper(),
                "retailer_name": clean_optional(retailer_name),
                "ean": clean_optional(ean),
                "language_code": clean_optional(language_code.lower()),
            },
            "feature_set": feature_set.strip() or "toy_features",
            "runtime_options": runtime_options,
        }

        status_box = st.empty()
        flow_box = st.empty()
        progress_bar = st.progress(0.02, text="Submitting")
        started = time.monotonic()
        try:
            job = api_json("POST", "/v1/jobs", payload=payload, timeout=30)
            job_id = str(job["job_id"])
            last_signature: tuple[Any, ...] | None = None
            while True:
                if time.monotonic() - started > MAX_POLL_SECONDS:
                    raise TimeoutError("The demo exceeded the 30-minute polling limit")
                status_payload = api_json("GET", f"/v1/jobs/{job_id}", timeout=20)
                signature = (
                    status_payload.get("status"),
                    status_payload.get("stage"),
                    status_payload.get("message"),
                )
                if signature != last_signature:
                    stage = str(status_payload.get("stage") or "")
                    state = str(status_payload.get("status") or "")
                    status_box.info(
                        f"{state} · {stage or 'working'} · {status_payload.get('message') or ''}"
                    )
                    with flow_box.container():
                        render_workflow(flow_key(stage, state))
                    progress_bar.progress(
                        stage_progress(stage, state),
                        text=stage or state or "Working",
                    )
                    last_signature = signature
                if status_payload.get("status") in TERMINAL_STATUSES:
                    if status_payload.get("status") == "FAILED":
                        raise RuntimeError(
                            status_payload.get("error")
                            or status_payload.get("message")
                            or "Job failed"
                        )
                    break
                time.sleep(1.5)

            result = api_json("GET", f"/v1/jobs/{job_id}/result", timeout=120)
            elapsed = time.monotonic() - started
            st.session_state.demo_result = result
            st.session_state.demo_elapsed_seconds = elapsed
            st.session_state.demo_job_id = job_id
            progress_bar.progress(1.0, text="Decision package ready")
            status_box.empty()
            flow_box.empty()
        except Exception as exc:
            elapsed = time.monotonic() - started
            progress_bar.empty()
            status_box.empty()
            flow_box.empty()
            title, action = friendly_error(exc)
            st.markdown(
                f'<div class="status-fail"><strong>{title}</strong><br>{action}</div>',
                unsafe_allow_html=True,
            )
            with st.expander("Technical error detail", expanded=True):
                st.code(f"{type(exc).__name__}: {exc}")
                st.caption(f"Elapsed before failure: {elapsed:.1f}s")

if "demo_result" in st.session_state:
    render_result(
        st.session_state.demo_result,
        st.session_state.get("demo_elapsed_seconds"),
    )
else:
    st.caption("Safety policy is fixed. Only the bounded run budget in the sidebar is controllable.")
