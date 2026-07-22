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

st.set_page_config(page_title="Product URL Resolver", page_icon="◈", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px;}
    .trace-note {border-left: 4px solid #6b7280; padding: .65rem .9rem; background: rgba(107,114,128,.08); border-radius: .25rem;}
    .stage-card {padding: .55rem .65rem; border: 1px solid rgba(128,128,128,.25); border-radius: .45rem; text-align:center; min-height: 68px;}
    .stage-active {border-width: 2px; font-weight: 700;}
    .stage-complete {opacity: .9;}
    .small-muted {opacity: .7; font-size: .86rem;}
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


def runtime_sidebar(runtime: Mapping[str, Any]) -> tuple[bool, float]:
    st.sidebar.success("Runtime ready")
    st.sidebar.caption(f"Version {runtime.get('version')} · {runtime.get('runtime_contract')}")
    st.sidebar.caption(f"Trace: {runtime.get('trace_contract', 'unavailable')}")
    browser = runtime.get("browser") or {}
    reasoning = runtime.get("reasoning") or {}
    st.sidebar.caption(f"Browser: {browser.get('status', 'unknown')}")
    st.sidebar.caption(
        "PCA reasoning: "
        f"enabled={reasoning.get('enabled')} · deployment={reasoning.get('deployment') or 'not configured'}"
    )
    st.sidebar.divider()
    trace_mode = st.sidebar.toggle(
        "Thinking mode: live decision trace",
        value=True,
        help="Shows observable evidence, hypotheses, gates and decisions in real time. It does not expose hidden chain-of-thought.",
    )
    poll_seconds = float(
        st.sidebar.select_slider(
            "Live refresh",
            options=[0.5, 1.0, 2.0, 3.0],
            value=1.0,
            format_func=lambda value: f"{value:g}s",
        )
    )
    st.sidebar.markdown(f'<div class="trace-note">{TRACE_NOTICE}</div>', unsafe_allow_html=True)
    return trace_mode, poll_seconds


def run_live_job(
    payload: dict[str, Any],
    *,
    trace_mode: bool,
    poll_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    job = api("POST", "/v1/jobs", payload)
    job_id = str(job["job_id"])
    events: list[dict[str, Any]] = []
    last_sequence = 0
    deadline = time.monotonic() + 1800

    st.markdown("---")
    st.markdown("## Live resolution")
    top_metrics = st.empty()
    stage_placeholder = st.empty()
    status_placeholder = st.empty()
    trace_placeholder = st.empty()

    while time.monotonic() < deadline:
        job = api("GET", f"/v1/jobs/{job_id}")
        trace = api("GET", f"/v1/jobs/{job_id}/trace?after_sequence={last_sequence}")
        events = merge_events(events, trace.get("events") or [])
        last_sequence = max(last_sequence, int(trace.get("last_event_sequence") or 0))

        with top_metrics.container():
            cols = st.columns(4)
            cols[0].metric("Job", job_id)
            cols[1].metric("Status", str(job.get("status") or "UNKNOWN").replace("_", " ").title())
            cols[2].metric("Stage", str(job.get("stage") or "QUEUED").replace("_", " ").title())
            cols[3].metric("Trace events", int(job.get("event_count") or len(events)))

        with stage_placeholder.container():
            render_stage_tracker(events, str(job.get("stage") or "QUEUED"), str(job.get("status") or "QUEUED"))

        status_placeholder.info(f"{job.get('stage')} · {job.get('message')}")

        if trace_mode:
            with trace_placeholder.container():
                render_live_trace(events)

        if job.get("status") in TERMINAL_STATUSES:
            break
        time.sleep(poll_seconds)
    else:
        raise TimeoutError("Product-resolution job exceeded 1800 seconds")

    result = api("GET", f"/v1/jobs/{job_id}/result", timeout=60)
    events = merge_events(events, result.get("events") or [])
    status_placeholder.success(f"Completed with {str((result.get('decision') or {}).get('status') or 'UNKNOWN')}")
    with stage_placeholder.container():
        render_stage_tracker(events, "COMPLETE", str(job.get("status") or "COMPLETED"))
    if trace_mode:
        with trace_placeholder.container():
            render_live_trace(events, final=True)
    return result, events


def render_stage_tracker(events: Sequence[Mapping[str, Any]], current_stage: str, status: str) -> None:
    rows = stage_rows(events, current_stage, status)
    columns = st.columns(len(rows))
    icon = {"COMPLETE": "✓", "ACTIVE": "●", "OBSERVED": "•", "PENDING": "○"}
    css = {"COMPLETE": "stage-complete", "ACTIVE": "stage-active", "OBSERVED": "", "PENDING": ""}
    for column, row in zip(columns, rows):
        state = row["state"]
        column.markdown(
            f'<div class="stage-card {css[state]}"><strong>{icon[state]} {row["stage"].title()}</strong><br>'
            f'<span class="small-muted">{state.replace("_", " ").title()}</span></div>',
            unsafe_allow_html=True,
        )


def render_live_trace(events: Sequence[Mapping[str, Any]], *, final: bool = False) -> None:
    st.markdown("### Observable decision trace")
    st.caption(TRACE_NOTICE)
    if not events:
        st.info("Waiting for the first structured trace event.")
        return
    visible = list(events) if final else list(events)[-24:]
    for index, event in enumerate(visible):
        sequence = int(event.get("sequence") or 0)
        stage = str(event.get("stage") or "UNKNOWN")
        event_type = str(event.get("event_type") or "EVENT")
        message = str(event.get("message") or "")
        expanded = index == len(visible) - 1
        with st.expander(f"{sequence:02d} · {stage} · {event_type.replace('_', ' ').title()}", expanded=expanded):
            st.write(message)
            render_event_details(event_type, event.get("details") or {})


def render_event_details(event_type: str, details: Mapping[str, Any]) -> None:
    if event_type == "SEARCH_ACTION":
        cols = st.columns(4)
        cols[0].metric("Credit", details.get("credit_number"))
        cols[1].metric("Engine", details.get("engine"))
        cols[2].metric("Purpose", str(details.get("purpose") or "").replace("_", " ").title())
        cols[3].metric("Scope", details.get("scope"))
        if details.get("query"):
            st.code(str(details["query"]), language=None)
        st.caption(str(details.get("rationale") or ""))
        return

    if event_type == "SEARCH_OBSERVATION":
        cols = st.columns(4)
        cols[0].metric("Status", details.get("status"))
        cols[1].metric("Results", details.get("result_count"))
        cols[2].metric("Product-like", details.get("product_like_count"))
        cols[3].metric("Search ID", details.get("search_id") or "—")
        top_results = details.get("top_results") or []
        if top_results:
            st.dataframe(pd.DataFrame(top_results), hide_index=True, use_container_width=True)
        if details.get("answer_summary"):
            st.markdown("**Search answer summary**")
            st.write(details.get("answer_summary"))
        if details.get("error"):
            st.error(str(details.get("error")))
        return

    if event_type == "SEARCH_CANDIDATES":
        candidates = details.get("candidates") or []
        if candidates:
            st.dataframe(pd.DataFrame(candidates), hide_index=True, use_container_width=True)
        return

    if event_type in {"DETERMINISTIC_INTERPRETATION", "INTERPRETATION_READY"}:
        signals = details.get("signals") or []
        hypotheses = details.get("hypotheses") or []
        cols = st.columns(4)
        cols[0].metric("Signals", len(signals))
        cols[1].metric("Hypotheses", len(hypotheses))
        cols[2].metric("Unresolved", len(details.get("unresolved_discriminators") or []))
        cols[3].metric("LLM inferences", details.get("llm_inference_count", 0))
        if signals:
            st.dataframe(pd.DataFrame(signals), hide_index=True, use_container_width=True)
        if hypotheses:
            st.dataframe(pd.DataFrame(hypotheses), hide_index=True, use_container_width=True)
        unresolved = details.get("unresolved_discriminators") or []
        if unresolved:
            st.warning("Unresolved: " + ", ".join(str(item) for item in unresolved))
        return

    if event_type == "ACQUISITION_PLAN":
        cols = st.columns(4)
        cols[0].metric("Submitted", details.get("submitted_candidate_count"))
        cols[1].metric("Selected", details.get("selected_candidate_count"))
        cols[2].metric("Per domain", details.get("max_per_domain"))
        cols[3].metric("Workers", details.get("max_workers"))
        st.write(details.get("selected_urls") or [])
        return

    if event_type == "PAGE_FETCHED":
        cols = st.columns(5)
        cols[0].metric("Fetch", details.get("fetch_status"))
        cols[1].metric("HTTP", details.get("status_code") or "—")
        cols[2].metric("JSON-LD products", details.get("jsonld_product_count"))
        cols[3].metric("Text length", details.get("visible_text_length"))
        cols[4].metric("Elapsed", f"{int(details.get('elapsed_ms') or 0)} ms")
        st.code(str(details.get("final_url") or details.get("requested_url") or ""), language=None)
        if details.get("fetch_error"):
            st.error(str(details.get("fetch_error")))
        return

    if event_type == "CANDIDATE_ASSESSED":
        cols = st.columns(5)
        cols[0].metric("Identity", details.get("identity_match"))
        cols[1].metric("Confidence", f"{float(details.get('identity_confidence') or 0):.1%}")
        cols[2].metric("Direct score", f"{float(details.get('direct_page_score') or 0):.2f}")
        cols[3].metric("Authority", details.get("source_authority"))
        cols[4].metric("Review eligible", details.get("review_eligible"))
        st.code(str(details.get("url") or ""), language=None)
        gates = details.get("gates") or []
        if gates:
            st.dataframe(pd.DataFrame(gates), hide_index=True, use_container_width=True)
        render_judgment_lists(details)
        return

    if event_type in {"BROWSER_ALLOCATION", "BROWSER_STARTED", "BROWSER_COMPLETED"}:
        if details.get("candidates"):
            st.dataframe(pd.DataFrame(details.get("candidates")), hide_index=True, use_container_width=True)
        else:
            cols = st.columns(4)
            cols[0].metric("Candidate", details.get("candidate_id") or "—")
            cols[1].metric("Access", details.get("access") or "RUNNING")
            cols[2].metric("Controls", len(details.get("product_controls") or []))
            cols[3].metric("Screenshot", "yes" if details.get("screenshot_path") else "no")
            st.code(str(details.get("final_url") or details.get("url") or ""), language=None)
            if details.get("error"):
                st.warning(str(details.get("error")))
        return

    if event_type == "CANDIDATE_RANKING":
        ranking = details.get("ranking") or []
        if ranking:
            rows = [
                {
                    "selected": item.get("selected"),
                    "candidate": item.get("candidate_id"),
                    "identity": item.get("identity_match"),
                    "confidence": item.get("identity_confidence"),
                    "direct_score": item.get("direct_page_score"),
                    "authority": item.get("source_authority"),
                    "review_eligible": item.get("review_eligible"),
                    "blockers": "; ".join(item.get("blockers") or []),
                    "url": item.get("url"),
                }
                for item in ranking
            ]
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        return

    if event_type == "DECISION_COMPLETE":
        cols = st.columns(4)
        cols[0].metric("Status", details.get("status"))
        cols[1].metric("Confidence", f"{float(details.get('confidence') or 0):.1%}")
        cols[2].metric("Coding ready", details.get("coding_ready"))
        cols[3].metric("Candidate", details.get("selected_candidate_id") or "—")
        if details.get("selected_url"):
            st.code(str(details.get("selected_url")), language=None)
        for reason in details.get("reasons") or []:
            st.success(str(reason))
        for warning in details.get("warnings") or []:
            st.warning(str(warning))
        return

    if details:
        st.json(dict(details), expanded=False)


def render_result(result: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> None:
    decision = result.get("decision") or {}
    status = str(decision.get("status") or "UNKNOWN")
    selected_url = decision.get("selected_url")
    selected_id = decision.get("selected_candidate_id")
    candidates = result.get("candidates") or []

    st.markdown("---")
    st.markdown("## Final review workspace")
    if status == "VERIFIED":
        st.success("Verified direct product URL")
    elif status == "REVIEW_REQUIRED":
        st.warning("Direct product URL delivered for human review")
    else:
        st.error(status.replace("_", " ").title())

    if selected_url:
        st.link_button("Open selected product", str(selected_url), use_container_width=True)
        st.code(str(selected_url), language=None)

    metrics = st.columns(5)
    metrics[0].metric("Status", status.replace("_", " ").title())
    metrics[1].metric("Identity confidence", f"{float(decision.get('confidence') or 0):.1%}")
    metrics[2].metric("Candidates", len(candidates))
    metrics[3].metric("Trace events", len(events))
    metrics[4].metric("Elapsed", f"{int(result.get('elapsed_ms') or 0) / 1000:.1f}s")

    tabs = st.tabs([
        "Decision",
        "Identity",
        "Search & sources",
        "Candidate judgments",
        "Browser & usability",
        "Audit & export",
    ])

    with tabs[0]:
        st.markdown("### Why this decision was made")
        for reason in decision.get("reasons") or []:
            st.success(str(reason))
        for warning in decision.get("warnings") or []:
            st.warning(str(warning))
        ranking = ranking_from_events(events)
        selected_judgment = next((item for item in ranking if item.get("candidate_id") == selected_id), None)
        if selected_judgment:
            st.markdown("### Selected candidate judgment")
            render_judgment_lists(selected_judgment)
            if selected_judgment.get("gates"):
                st.dataframe(pd.DataFrame(selected_judgment["gates"]), hide_index=True, use_container_width=True)
        st.info("URL delivery, identity verification, browser automation and coding-field completeness are independent outcomes.")

    with tabs[1]:
        interpretation = result.get("interpretation") or {}
        st.markdown("### Identity signals")
        signals = signal_rows(interpretation)
        if signals:
            st.dataframe(pd.DataFrame(signals), hide_index=True, use_container_width=True)
        else:
            st.info("No identity signals were produced.")
        st.markdown("### Competing product hypotheses")
        hypotheses = hypothesis_rows(interpretation)
        if hypotheses:
            st.dataframe(pd.DataFrame(hypotheses), hide_index=True, use_container_width=True)
        unresolved = interpretation.get("unresolved_discriminators") or []
        constraints = interpretation.get("negative_constraints") or []
        if unresolved:
            st.warning("Unresolved discriminators: " + ", ".join(str(item) for item in unresolved))
        if constraints:
            st.markdown("**Negative constraints**")
            for item in constraints:
                st.markdown(f"- {item}")

    with tabs[2]:
        observations = result.get("search_observations") or []
        action_rows = []
        for observation in observations:
            action = observation.get("action") or {}
            action_rows.append(
                {
                    "credit": action.get("credit_number"),
                    "purpose": action.get("purpose"),
                    "engine": action.get("engine"),
                    "scope": action.get("scope"),
                    "target_uncertainty": action.get("target_uncertainty"),
                    "query": action.get("query"),
                    "rationale": action.get("rationale"),
                    "status": observation.get("status"),
                    "results": len(observation.get("results") or []),
                }
            )
        st.markdown("### Paid search actions")
        if action_rows:
            st.dataframe(pd.DataFrame(action_rows), hide_index=True, use_container_width=True)
        st.markdown("### Source observations")
        sources = search_rows(observations)
        if sources:
            st.dataframe(pd.DataFrame(sources), hide_index=True, use_container_width=True)
        else:
            st.info("No external source observations were retained.")

    with tabs[3]:
        rows = candidate_rows(candidates, selected_id)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        ranking = ranking_from_events(events)
        ranking_by_id = {str(item.get("candidate_id")): item for item in ranking}
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id") or "UNKNOWN")
            selected = candidate_id == selected_id
            title = f"{'SELECTED · ' if selected else ''}{candidate_id} · {candidate.get('domain')}"
            with st.expander(title, expanded=selected):
                st.code(str(candidate.get("url") or ""), language=None)
                judgment = ranking_by_id.get(candidate_id)
                if judgment:
                    render_judgment_lists(judgment)
                    if judgment.get("gates"):
                        st.dataframe(pd.DataFrame(judgment["gates"]), hide_index=True, use_container_width=True)
                evidence = candidate.get("evidence") or {}
                identity_rows = [
                    {"type": name, "values": "; ".join(evidence.get(name) or [])}
                    for name in ("matched_signals", "missing_signals", "identity_conflicts")
                ]
                st.markdown("**Identity evidence**")
                st.dataframe(pd.DataFrame(identity_rows), hide_index=True, use_container_width=True)
                fields = evidence.get("fields") or {}
                if fields:
                    st.markdown("**Structured product fields**")
                    st.dataframe(pd.DataFrame([fields]), hide_index=True, use_container_width=True)

    with tabs[4]:
        browser_rows = []
        for candidate in candidates:
            browser = (candidate.get("evidence") or {}).get("browser") or {}
            browser_rows.append(
                {
                    "candidate": candidate.get("candidate_id"),
                    "browser": candidate.get("browser_access"),
                    "extractable": candidate.get("text_extractable"),
                    "final_url": browser.get("final_url"),
                    "title": browser.get("title"),
                    "controls": len(browser.get("product_controls") or []),
                    "error": browser.get("error"),
                    "screenshot": browser.get("screenshot_path"),
                }
            )
        if browser_rows:
            st.dataframe(pd.DataFrame(browser_rows), hide_index=True, use_container_width=True)
        for row in browser_rows:
            path = Path(str(row.get("screenshot") or ""))
            if path.is_file():
                with st.expander(f"Screenshot · {row.get('candidate')}", expanded=row.get("candidate") == selected_id):
                    st.image(str(path), caption=f"Rendered evidence for {row.get('candidate')}", use_container_width=True)

    with tabs[5]:
        st.markdown("### Full observable trace")
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
        with st.expander("Raw result", expanded=False):
            st.json(dict(result), expanded=False)


def ranking_from_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    for event in reversed(events):
        if event.get("event_type") == "CANDIDATE_RANKING":
            return [dict(item) for item in (event.get("details") or {}).get("ranking") or []]
    return []


def render_judgment_lists(details: Mapping[str, Any]) -> None:
    columns = st.columns(3)
    sections = (
        (columns[0], "Strengths", details.get("strengths") or [], "No positive gate evidence recorded."),
        (columns[1], "Risks / unknowns", details.get("risks") or [], "No unresolved operational risks recorded."),
        (columns[2], "Blockers", details.get("blockers") or [], "No hard blocker recorded."),
    )
    for column, title, values, empty in sections:
        with column:
            st.markdown(f"**{title}**")
            if values:
                for item in values:
                    st.markdown(f"- {item}")
            else:
                st.caption(empty)


st.title("Product URL Resolver")
st.caption("Human-review workspace for auditable product identification, source evidence and direct URL delivery")

try:
    runtime = health()
    profiles = runtime.get("profiles") or {}
    trace_mode, poll_seconds = runtime_sidebar(runtime)
except Exception as exc:
    st.sidebar.error("Runtime unavailable")
    st.sidebar.code("./scripts/start.sh --build")
    st.sidebar.exception(exc)
    runtime = {}
    profiles = {"Standard": {"search_credits": 3, "max_candidates": 12, "browser_candidates": 3}}
    trace_mode = True
    poll_seconds = 1.0

reasoning_health = runtime.get("reasoning") or {}
reasoning_configured = bool(reasoning_health.get("deployment"))

with st.form("resolve"):
    st.markdown("### Product input")
    left, middle, right = st.columns([1.4, 1, 1])
    with left:
        main_text = st.text_area(
            "Main text",
            placeholder="PKM ME04 WACHSENDES CHAOS BOOSTER",
            height=120,
            help="Vendor-provided product text. Exact identifiers and quantities are preserved as identity anchors.",
        )
        retailer_name = st.text_input("Retailer name (optional)")
    with middle:
        country_code = st.text_input("Country code", value="CH", max_chars=2)
        language_code = st.text_input("Language code (optional)", value="de")
        ean = st.text_input("EAN / GTIN (optional)")
    with right:
        feature_set = st.text_input("Feature set", value="toy")
        profile_names = list(profiles) or ["Standard"]
        profile_name = st.selectbox("Execution profile", profile_names, index=min(1, len(profile_names) - 1))
        use_reasoning = st.toggle(
            "Use PCA LLM hypothesis refinement",
            value=reasoning_configured,
            help="The LLM may refine hypotheses but cannot invent identifiers or URLs.",
        )
        st.caption("The final decision remains evidence-gated even when LLM refinement is enabled.")
    submitted = st.form_submit_button("Resolve product URL", type="primary", use_container_width=True)

if submitted:
    if not main_text.strip() or len(country_code.strip()) != 2:
        st.error("Main text and a two-letter country code are required.")
    else:
        runtime_options = dict(profiles.get(profile_name) or {})
        runtime_options["reasoning_enabled"] = use_reasoning
        payload = {
            "main_text": main_text,
            "country_code": country_code,
            "retailer_name": retailer_name or None,
            "ean": ean or None,
            "language_code": language_code or None,
            "feature_set": feature_set,
            "runtime_options": runtime_options,
        }
        try:
            result, live_events = run_live_job(payload, trace_mode=trace_mode, poll_seconds=poll_seconds)
            render_result(result, live_events)
        except Exception as exc:
            st.exception(exc)
