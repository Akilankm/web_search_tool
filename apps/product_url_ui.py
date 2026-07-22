from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import requests
import streamlit as st

from product_url_v2.ui_presenter import (
    TERMINAL_STATUSES,
    TRACE_NOTICE,
    candidate_rows,
    event_rows,
    hypothesis_rows,
    merge_events,
    search_rows,
    signal_rows,
    stage_rows,
)

API_URL = str(os.getenv("PRODUCT_URL_API_URL") or "http://127.0.0.1:8788").rstrip("/")

st.set_page_config(page_title="Product URL Delivery Workbench", page_icon="◈", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1550px;}
    .contract {padding: .9rem 1rem; border: 1px solid rgba(128,128,128,.28); border-radius: .6rem; margin-bottom: 1rem;}
    .url-card {padding: 1rem 1.1rem; border: 2px solid rgba(46,160,67,.55); border-radius: .65rem; margin: .65rem 0 1rem 0;}
    .trace-note {border-left: 4px solid #6b7280; padding: .65rem .9rem; background: rgba(107,114,128,.08); border-radius: .25rem;}
    .stage-card {padding: .55rem .45rem; border: 1px solid rgba(128,128,128,.25); border-radius: .45rem; text-align:center; min-height: 62px;}
    .stage-active {border-width: 2px; font-weight: 700;}
    .stage-complete {opacity: .9;}
    .small-muted {opacity: .72; font-size: .86rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def api(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    response = requests.request(method, f"{API_URL}{path}", json=payload, timeout=timeout)
    if not response.ok:
        raise RuntimeError(f"API HTTP {response.status_code}: {response.text[:2000]}")
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("API returned non-object JSON")
    return value


@st.cache_data(ttl=5, show_spinner=False)
def health() -> dict[str, Any]:
    return api("GET", "/health", timeout=15)


def latest_event(events: Sequence[Mapping[str, Any]], event_type: str) -> Mapping[str, Any] | None:
    return next((item for item in reversed(events) if item.get("event_type") == event_type), None)


def candidate_count_from_trace(events: Sequence[Mapping[str, Any]]) -> int:
    event = latest_event(events, "SEARCH_CANDIDATES")
    if not event:
        return 0
    return int((event.get("details") or {}).get("candidate_count") or 0)


def render_stage_tracker(events: Sequence[Mapping[str, Any]], current_stage: str, status: str) -> None:
    rows = stage_rows(events, current_stage, status)
    columns = st.columns(len(rows))
    for column, row in zip(columns, rows):
        state = row["state"]
        css = "stage-active" if state == "ACTIVE" else "stage-complete" if state == "COMPLETE" else ""
        marker = "●" if state == "ACTIVE" else "✓" if state == "COMPLETE" else "○"
        column.markdown(
            f'<div class="stage-card {css}"><strong>{marker} {row["stage"].title()}</strong><br><span class="small-muted">{state.title()}</span></div>',
            unsafe_allow_html=True,
        )


def render_live_trace(events: Sequence[Mapping[str, Any]]) -> None:
    if not events:
        st.info("Waiting for the first observable decision event.")
        return
    for event in reversed(events[-12:]):
        sequence = event.get("sequence")
        stage = event.get("stage")
        event_type = event.get("event_type")
        message = event.get("message")
        with st.expander(f"#{sequence} · {stage} · {event_type} — {message}", expanded=event is events[-1]):
            details = event.get("details") or {}
            if event_type == "SEARCH_ACTION":
                st.code(str(details.get("query") or details.get("page_token") or ""), language=None)
                cols = st.columns(4)
                cols[0].metric("Credit", details.get("credit_number"))
                cols[1].metric("Purpose", details.get("purpose"))
                cols[2].metric("Engine", details.get("engine"))
                cols[3].metric("Scope", details.get("scope"))
                st.caption(str(details.get("rationale") or ""))
            elif event_type == "SEARCH_OBSERVATION":
                cols = st.columns(3)
                cols[0].metric("External results", details.get("result_count"))
                cols[1].metric("Product-like", details.get("product_like_count"))
                cols[2].metric("Search status", details.get("status"))
                if details.get("top_results"):
                    st.dataframe(pd.DataFrame(details["top_results"]), hide_index=True, use_container_width=True)
            elif event_type in {"CANDIDATE_ASSESSED", "CANDIDATE_RANKING", "DECISION_COMPLETE"}:
                st.json(dict(details), expanded=False)
            elif details:
                st.json(dict(details), expanded=False)


def run_live_job(payload: dict[str, Any], trace_mode: bool, poll_seconds: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    job = api("POST", "/v1/jobs", payload)
    job_id = str(job["job_id"])
    events: list[dict[str, Any]] = []
    last_sequence = 0
    deadline = time.monotonic() + 1800

    st.markdown("---")
    st.markdown("## Live URL recovery")
    metrics_placeholder = st.empty()
    stage_placeholder = st.empty()
    status_placeholder = st.empty()
    trace_placeholder = st.empty()

    while time.monotonic() < deadline:
        job = api("GET", f"/v1/jobs/{job_id}")
        trace = api("GET", f"/v1/jobs/{job_id}/trace?after_sequence={last_sequence}")
        events = merge_events(events, trace.get("events") or [])
        last_sequence = max(last_sequence, int(trace.get("last_event_sequence") or 0))

        with metrics_placeholder.container():
            cols = st.columns(4)
            cols[0].metric("Job", job_id)
            cols[1].metric("Current stage", str(job.get("stage") or "QUEUED").title())
            cols[2].metric("Product-like URLs", candidate_count_from_trace(events))
            cols[3].metric("Observable events", len(events))

        with stage_placeholder.container():
            render_stage_tracker(events, str(job.get("stage") or "QUEUED"), str(job.get("status") or "QUEUED"))

        status_placeholder.info(str(job.get("message") or "Working"))
        if trace_mode:
            with trace_placeholder.container():
                st.markdown("### Observable decision trace")
                st.caption(TRACE_NOTICE)
                render_live_trace(events)

        if str(job.get("status")) in TERMINAL_STATUSES:
            result = api("GET", f"/v1/jobs/{job_id}/result", timeout=60)
            return result, events
        time.sleep(poll_seconds)

    raise TimeoutError("Product URL resolution exceeded 30 minutes")


def status_heading(status: str, selected_url: str | None) -> tuple[str, str]:
    if status == "VERIFIED" and selected_url:
        return "URL DELIVERED — VERIFIED", "success"
    if status == "REVIEW_REQUIRED" and selected_url:
        return "URL DELIVERED — HUMAN REVIEW REQUIRED", "warning"
    if status == "TECHNICAL_FAILURE":
        return "TECHNICAL FAILURE — NO VALID DECISION", "error"
    return "NO USABLE PRODUCT URL FOUND", "error"


def render_judgment_lists(details: Mapping[str, Any]) -> None:
    columns = st.columns(3)
    sections = (
        (columns[0], "Strengths", details.get("strengths") or [], "No positive evidence recorded."),
        (columns[1], "Risks / unknowns", details.get("risks") or [], "No unresolved risks recorded."),
        (columns[2], "Hard blockers", details.get("blockers") or [], "No hard blocker recorded."),
    )
    for column, title, values, empty in sections:
        with column:
            st.markdown(f"**{title}**")
            if values:
                for item in values:
                    st.markdown(f"- {item}")
            else:
                st.caption(empty)


def ranking_from_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    event = latest_event(events, "CANDIDATE_RANKING")
    return [dict(item) for item in ((event or {}).get("details") or {}).get("ranking") or []]


def render_result(result: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> None:
    decision = result.get("decision") or {}
    status = str(decision.get("status") or "UNKNOWN")
    selected_url = decision.get("selected_url")
    selected_id = decision.get("selected_candidate_id")
    candidates = result.get("candidates") or []
    heading, style = status_heading(status, str(selected_url) if selected_url else None)

    st.markdown("---")
    st.markdown("## Product URL delivery result")
    getattr(st, style)(heading)

    top = st.columns(5)
    top[0].metric("URL delivered", "YES" if selected_url else "NO")
    top[1].metric("Delivery grade", status.replace("_", " ").title())
    top[2].metric("Identity evidence", f"{float(decision.get('confidence') or 0):.1%}")
    top[3].metric("Candidates assessed", len(candidates))
    top[4].metric("Elapsed", f"{int(result.get('elapsed_ms') or 0) / 1000:.1f}s")

    if selected_url:
        st.markdown('<div class="url-card"><strong>Selected direct product URL</strong></div>', unsafe_allow_html=True)
        st.link_button("Open selected product", str(selected_url), use_container_width=True)
        st.code(str(selected_url), language=None)
        if status == "REVIEW_REQUIRED":
            st.info("The URL is the strongest surviving product-like candidate. Verification gaps are shown below for the human coder; they do not erase the URL.")

    tabs = st.tabs([
        "Decision",
        "Candidate evidence",
        "Identity & hypotheses",
        "Search sources",
        "Browser usability",
        "Audit & export",
    ])

    ranking = ranking_from_events(events)
    ranking_by_id = {str(item.get("candidate_id")): item for item in ranking}

    with tabs[0]:
        st.markdown("### Why this URL was selected")
        for reason in decision.get("reasons") or []:
            st.success(str(reason))
        for warning in decision.get("warnings") or []:
            st.warning(str(warning))
        selected_judgment = ranking_by_id.get(str(selected_id))
        if selected_judgment:
            render_judgment_lists(selected_judgment)
            if selected_judgment.get("gates"):
                st.dataframe(pd.DataFrame(selected_judgment["gates"]), hide_index=True, use_container_width=True)
        st.caption("URL delivery, identity confidence, browser automation and coding readiness are independent outcomes.")

    with tabs[1]:
        rows = candidate_rows(candidates, selected_id)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id") or "UNKNOWN")
            selected = candidate_id == str(selected_id)
            with st.expander(f"{'SELECTED · ' if selected else ''}{candidate_id} · {candidate.get('domain')}", expanded=selected):
                st.code(str(candidate.get("url") or ""), language=None)
                judgment = ranking_by_id.get(candidate_id)
                if judgment:
                    st.caption(f"Delivery basis: {judgment.get('delivery_basis') or 'not recorded'}")
                    render_judgment_lists(judgment)
                    if judgment.get("gates"):
                        st.dataframe(pd.DataFrame(judgment["gates"]), hide_index=True, use_container_width=True)
                evidence = candidate.get("evidence") or {}
                identity_rows = [
                    {"type": name, "values": "; ".join(evidence.get(name) or [])}
                    for name in ("matched_signals", "missing_signals", "identity_conflicts", "hard_url_blockers")
                ]
                st.dataframe(pd.DataFrame(identity_rows), hide_index=True, use_container_width=True)
                if evidence.get("fields"):
                    st.dataframe(pd.DataFrame([evidence["fields"]]), hide_index=True, use_container_width=True)

    with tabs[2]:
        interpretation = result.get("interpretation") or {}
        signals = signal_rows(interpretation)
        hypotheses = hypothesis_rows(interpretation)
        st.markdown("### Identity signals")
        if signals:
            st.dataframe(pd.DataFrame(signals), hide_index=True, use_container_width=True)
        else:
            st.info("No identity signal was confirmed automatically.")
        st.markdown("### Competing hypotheses")
        if hypotheses:
            st.dataframe(pd.DataFrame(hypotheses), hide_index=True, use_container_width=True)
        unresolved = interpretation.get("unresolved_discriminators") or []
        if unresolved:
            st.warning("Unresolved: " + ", ".join(str(item) for item in unresolved))

    with tabs[3]:
        observations = result.get("search_observations") or []
        action_rows = []
        for observation in observations:
            action = observation.get("action") or {}
            action_rows.append({
                "credit": action.get("credit_number"),
                "purpose": action.get("purpose"),
                "engine": action.get("engine"),
                "scope": action.get("scope"),
                "query": action.get("query"),
                "rationale": action.get("rationale"),
                "status": observation.get("status"),
                "results": len(observation.get("results") or []),
            })
        if action_rows:
            st.dataframe(pd.DataFrame(action_rows), hide_index=True, use_container_width=True)
        sources = search_rows(observations)
        if sources:
            st.dataframe(pd.DataFrame(sources), hide_index=True, use_container_width=True)

    with tabs[4]:
        browser_rows = []
        for candidate in candidates:
            browser = (candidate.get("evidence") or {}).get("browser") or {}
            browser_rows.append({
                "candidate": candidate.get("candidate_id"),
                "browser": candidate.get("browser_access"),
                "extractable": candidate.get("text_extractable"),
                "final_url": browser.get("final_url"),
                "title": browser.get("title"),
                "controls": len(browser.get("product_controls") or []),
                "error": browser.get("error"),
                "screenshot": browser.get("screenshot_path"),
            })
        if browser_rows:
            st.dataframe(pd.DataFrame(browser_rows), hide_index=True, use_container_width=True)
        for row in browser_rows:
            path = Path(str(row.get("screenshot") or ""))
            if path.is_file():
                with st.expander(f"Screenshot · {row.get('candidate')}", expanded=str(row.get("candidate")) == str(selected_id)):
                    st.image(str(path), caption=f"Rendered evidence for {row.get('candidate')}", use_container_width=True)

    with tabs[5]:
        st.caption(TRACE_NOTICE)
        trace_table = event_rows(events)
        if trace_table:
            st.dataframe(pd.DataFrame(trace_table), hide_index=True, use_container_width=True)
        result_json = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        st.download_button(
            "Download complete result JSON",
            data=result_json.encode("utf-8"),
            file_name=f"{(result.get('product') or {}).get('row_id', 'product')}_result.json",
            mime="application/json",
            use_container_width=True,
        )
        candidate_csv = pd.DataFrame(candidate_rows(candidates, selected_id)).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Download candidate review CSV",
            data=candidate_csv,
            file_name=f"{(result.get('product') or {}).get('row_id', 'product')}_candidates.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption(f"Artifacts: {result.get('artifact_dir')}")


st.title("Product URL Delivery Workbench")
st.caption("Mandatory direct URL delivery with auditable identity, source, usability and coding evidence")
st.markdown(
    """
    <div class="contract">
    <strong>Business invariant:</strong> when a non-conflicting product-like URL is found, the system delivers it.
    Incomplete identity, scrape, browser or coding evidence changes the review grade; it does not remove the URL.
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    runtime = health()
    st.sidebar.success("Runtime ready")
    st.sidebar.caption(f"Version {runtime.get('version')} · {runtime.get('runtime_contract')}")
    st.sidebar.caption(f"Delivery policy: {runtime.get('url_delivery_policy', 'unknown')}")
    st.sidebar.caption(f"Trace: {runtime.get('trace_contract', 'unavailable')}")
    browser = runtime.get("browser") or {}
    reasoning = runtime.get("reasoning") or {}
    st.sidebar.caption(f"Browser: {browser.get('status', 'unknown')}")
    st.sidebar.caption(f"PCA reasoning: enabled={reasoning.get('enabled')} · {reasoning.get('deployment') or 'not configured'}")
    profiles = runtime.get("profiles") or {}
except Exception as exc:
    st.sidebar.error("Runtime unavailable")
    st.sidebar.code("./scripts/start.sh --build")
    st.sidebar.exception(exc)
    profiles = {"Standard": {"search_credits": 3, "max_candidates": 12, "browser_candidates": 3}}

trace_mode = st.sidebar.toggle(
    "Thinking mode: live decision trace",
    value=True,
    help="Displays observable evidence, hypotheses, search actions, gates and judgments. It does not expose hidden chain-of-thought.",
)
poll_seconds = float(st.sidebar.select_slider("Live refresh", options=[0.5, 1.0, 2.0, 3.0], value=1.0, format_func=lambda value: f"{value:g}s"))
st.sidebar.markdown(f'<div class="trace-note">{TRACE_NOTICE}</div>', unsafe_allow_html=True)

with st.form("resolve"):
    left, right = st.columns(2)
    with left:
        main_text = st.text_area("Main text", placeholder="PKM ME04 WACHSENDES CHAOS BOOSTER", height=110)
        country_code = st.text_input("Country code", value="CH", max_chars=2)
        retailer_name = st.text_input("Retailer name (optional)")
    with right:
        ean = st.text_input("EAN / GTIN (optional)")
        language_code = st.text_input("Language code (optional)")
        feature_set = st.text_input("Feature set", value="toy")
        profile_names = list(profiles) or ["Standard"]
        default_index = profile_names.index("Standard") if "Standard" in profile_names else 0
        profile_name = st.selectbox("Execution profile", profile_names, index=default_index)
    submitted = st.form_submit_button("Find and deliver product URL", type="primary", use_container_width=True)

if submitted:
    if not main_text.strip() or len(country_code.strip()) != 2:
        st.error("Main text and a two-letter country code are required.")
    else:
        payload = {
            "main_text": main_text,
            "country_code": country_code,
            "retailer_name": retailer_name or None,
            "ean": ean or None,
            "language_code": language_code or None,
            "feature_set": feature_set,
            "runtime_options": profiles.get(profile_name) or {},
        }
        try:
            result, events = run_live_job(payload, trace_mode, poll_seconds)
            render_result(result, events)
        except Exception as exc:
            st.exception(exc)
