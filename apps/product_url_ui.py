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

st.set_page_config(page_title="Exact Product Mapping Console", page_icon="◆", layout="wide")
st.markdown(
    """
    <style>
    :root {
      --ink: #f8fafc;
      --muted: #94a3b8;
      --panel: rgba(15, 23, 42, .72);
      --line: rgba(148, 163, 184, .18);
      --accent: #8b5cf6;
      --accent2: #22d3ee;
      --ok: #22c55e;
      --bad: #ef4444;
    }
    .stApp {
      background:
        radial-gradient(circle at 15% 10%, rgba(139,92,246,.18), transparent 30%),
        radial-gradient(circle at 85% 5%, rgba(34,211,238,.12), transparent 28%),
        linear-gradient(180deg, #07101f 0%, #0b1220 42%, #0f172a 100%);
    }
    .block-container {padding-top: 1.4rem; padding-bottom: 4rem; max-width: 1540px;}
    h1, h2, h3 {letter-spacing: -.025em;}
    .hero {
      padding: 1.45rem 1.55rem;
      border: 1px solid rgba(139,92,246,.34);
      border-radius: 1rem;
      background: linear-gradient(135deg, rgba(139,92,246,.16), rgba(34,211,238,.06));
      box-shadow: 0 18px 50px rgba(0,0,0,.22);
      margin-bottom: 1.15rem;
    }
    .hero-kicker {font-size: .78rem; font-weight: 800; letter-spacing: .16em; color: #c4b5fd; text-transform: uppercase;}
    .hero-title {font-size: 2.05rem; font-weight: 780; margin: .25rem 0 .4rem 0; color: var(--ink);}
    .hero-copy {max-width: 980px; color: #cbd5e1; line-height: 1.55;}
    .contract-grid {display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:.65rem; margin-top:1rem;}
    .contract-card {padding:.8rem .9rem; border:1px solid var(--line); border-radius:.7rem; background:rgba(2,6,23,.36);}
    .contract-card b {display:block; color:#f8fafc; font-size:.9rem; margin-bottom:.15rem;}
    .contract-card span {color:#94a3b8; font-size:.8rem;}
    .result-card {
      padding: 1.25rem 1.35rem;
      border-radius: .95rem;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: 0 14px 35px rgba(0,0,0,.18);
      margin: .75rem 0 1rem 0;
    }
    .result-ok {border-color: rgba(34,197,94,.5); box-shadow: 0 0 0 1px rgba(34,197,94,.08), 0 18px 45px rgba(0,0,0,.2);}
    .result-bad {border-color: rgba(239,68,68,.5);}
    .badge {display:inline-block; padding:.25rem .55rem; border-radius:999px; font-size:.72rem; font-weight:800; letter-spacing:.06em;}
    .badge-ok {background:rgba(34,197,94,.16); color:#86efac; border:1px solid rgba(34,197,94,.34);}
    .badge-bad {background:rgba(239,68,68,.14); color:#fca5a5; border:1px solid rgba(239,68,68,.32);}
    .mapped-url {font-family:ui-monospace,SFMono-Regular,Menlo,monospace; word-break:break-all; color:#cffafe; margin-top:.7rem;}
    .stage-card {padding:.62rem .35rem; border:1px solid var(--line); border-radius:.62rem; text-align:center; min-height:64px; background:rgba(15,23,42,.52);}
    .stage-active {border-color:rgba(34,211,238,.65); box-shadow:0 0 0 1px rgba(34,211,238,.12);}
    .stage-complete {border-color:rgba(34,197,94,.38);}
    .small-muted {color:#94a3b8; font-size:.76rem;}
    .trace-note {border-left:3px solid #8b5cf6; padding:.65rem .8rem; background:rgba(139,92,246,.08); border-radius:.35rem; color:#cbd5e1;}
    div[data-testid="stMetric"] {background:rgba(15,23,42,.62); border:1px solid var(--line); padding:.75rem .85rem; border-radius:.75rem;}
    div[data-testid="stForm"] {background:rgba(15,23,42,.48); border:1px solid var(--line); padding:1rem; border-radius:.9rem;}
    @media (max-width: 900px) {.contract-grid {grid-template-columns:1fr 1fr;}}
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


def ranking_from_events(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    event = latest_event(events, "CANDIDATE_RANKING")
    return [dict(item) for item in ((event or {}).get("details") or {}).get("ranking") or []]


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
        st.info("Waiting for observable mapping evidence.")
        return
    for event in reversed(events[-10:]):
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
            elif event_type in {"CANDIDATE_ASSESSED", "BROWSER_COMPLETED", "DECISION_COMPLETE"}:
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
    st.markdown("## Live mapping campaign")
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
            cols[1].metric("Stage", str(job.get("stage") or "QUEUED").title())
            cols[2].metric("Evidence events", len(events))
            cols[3].metric("Status", str(job.get("status") or "RUNNING").replace("_", " ").title())
        with stage_placeholder.container():
            render_stage_tracker(events, str(job.get("stage") or "QUEUED"), str(job.get("status") or "QUEUED"))
        status_placeholder.info(str(job.get("message") or "Mapping product"))
        if trace_mode:
            with trace_placeholder.container():
                st.markdown("### Observable evidence trace")
                st.caption(TRACE_NOTICE)
                render_live_trace(events)
        if str(job.get("status")) in TERMINAL_STATUSES:
            return api("GET", f"/v1/jobs/{job_id}/result", timeout=60), events
        time.sleep(poll_seconds)
    raise TimeoutError("Exact product mapping exceeded 30 minutes")


def render_judgment_lists(details: Mapping[str, Any]) -> None:
    columns = st.columns(3)
    sections = (
        (columns[0], "Passed evidence", details.get("strengths") or [], "No mandatory gate passed."),
        (columns[1], "Secondary risks", details.get("risks") or [], "No secondary risk recorded."),
        (columns[2], "Mapping blockers", details.get("blockers") or [], "No blocker recorded."),
    )
    for column, title, values, empty in sections:
        with column:
            st.markdown(f"**{title}**")
            if values:
                for item in values:
                    st.markdown(f"- {item}")
            else:
                st.caption(empty)


def gate_value(candidate: Mapping[str, Any], field: str) -> bool:
    if field == "identifier":
        evidence = candidate.get("evidence") or {}
        return bool(evidence.get("exact_identifier_verified")) if evidence.get("required_identifier") else True
    return candidate.get(field) == "PASS"


def render_result(result: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> None:
    decision = result.get("decision") or {}
    status = str(decision.get("status") or "UNKNOWN")
    selected_url = decision.get("selected_url")
    selected_id = decision.get("selected_candidate_id")
    candidates = result.get("candidates") or []
    selected = next((item for item in candidates if item.get("candidate_id") == selected_id), None) or {}
    mapping_passed = bool(selected_url)

    st.markdown("---")
    st.markdown("## Final product mapping")
    badge = "EXACT MAPPING COMPLETE" if mapping_passed else "NO DEFENSIBLE MAPPING"
    badge_class = "badge-ok" if mapping_passed else "badge-bad"
    card_class = "result-ok" if mapping_passed else "result-bad"
    title = "One product. One verified URL." if mapping_passed else "A candidate URL was not falsely accepted."
    copy = (
        "The selected page confirms the exact product, opens in the rendered browser, and exposes scrapable product content."
        if mapping_passed
        else "The campaign found discovery evidence, but no URL passed every mandatory identity, accessibility, and scrapability gate."
    )
    url_html = f'<div class="mapped-url">{selected_url}</div>' if selected_url else ""
    st.markdown(
        f'<div class="result-card {card_class}"><span class="badge {badge_class}">{badge}</span><h2>{title}</h2><p>{copy}</p>{url_html}</div>',
        unsafe_allow_html=True,
    )

    metrics = st.columns(6)
    metrics[0].metric("Exact product mapped", "YES" if mapping_passed else "NO")
    metrics[1].metric("Identifier verified", "YES" if selected and gate_value(selected, "identifier") else "NO")
    metrics[2].metric("Browser opens", "YES" if selected and gate_value(selected, "browser_access") else "NO")
    metrics[3].metric("Scrapable", "YES" if selected and gate_value(selected, "text_extractable") else "NO")
    metrics[4].metric("Source", str(selected.get("source_role") or "—").replace("_", " ").title())
    metrics[5].metric("Elapsed", f"{int(result.get('elapsed_ms') or 0) / 1000:.1f}s")

    if selected_url:
        st.link_button("Open exact mapped product", str(selected_url), use_container_width=True, type="primary")
        st.code(str(selected_url), language=None)

    tabs = st.tabs(["Mapping decision", "Candidate proof", "Identity", "Search campaign", "Browser evidence", "Audit & export"])
    ranking = ranking_from_events(events)
    ranking_by_id = {str(item.get("candidate_id")): item for item in ranking}

    with tabs[0]:
        st.markdown("### Decision basis")
        for reason in decision.get("reasons") or []:
            st.success(str(reason)) if mapping_passed else st.warning(str(reason))
        for warning in decision.get("warnings") or []:
            st.warning(str(warning))
        if selected_id and ranking_by_id.get(str(selected_id)):
            render_judgment_lists(ranking_by_id[str(selected_id)])
            st.dataframe(pd.DataFrame(ranking_by_id[str(selected_id)].get("gates") or []), hide_index=True, use_container_width=True)

    with tabs[1]:
        rows = candidate_rows(candidates, selected_id)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        for candidate in candidates:
            cid = str(candidate.get("candidate_id") or "UNKNOWN")
            judgment = ranking_by_id.get(cid) or {}
            with st.expander(f"{'SELECTED · ' if cid == str(selected_id) else ''}{cid} · {candidate.get('domain')}", expanded=cid == str(selected_id)):
                st.code(str(candidate.get("url") or ""), language=None)
                st.caption(f"Delivery basis: {judgment.get('delivery_basis') or 'discovery only'}")
                render_judgment_lists(judgment)
                gates = judgment.get("gates") or []
                if gates:
                    st.dataframe(pd.DataFrame(gates), hide_index=True, use_container_width=True)

    with tabs[2]:
        interpretation = result.get("interpretation") or {}
        signals = signal_rows(interpretation)
        hypotheses = hypothesis_rows(interpretation)
        st.markdown("### Submitted identity and extracted anchors")
        if signals:
            st.dataframe(pd.DataFrame(signals), hide_index=True, use_container_width=True)
        if hypotheses:
            st.markdown("### Product hypotheses")
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
            })
        if action_rows:
            st.dataframe(pd.DataFrame(action_rows), hide_index=True, use_container_width=True)
        sources = search_rows(observations)
        if sources:
            st.dataframe(pd.DataFrame(sources), hide_index=True, use_container_width=True)

    with tabs[4]:
        browser_rows = []
        for candidate in candidates:
            evidence = candidate.get("evidence") or {}
            browser = evidence.get("browser") or {}
            browser_rows.append({
                "candidate": candidate.get("candidate_id"),
                "mapping_eligible": next((row["mapping_eligible"] for row in candidate_rows([candidate]) if row), False),
                "access": candidate.get("browser_access"),
                "scrapable": candidate.get("text_extractable"),
                "identifier_verified": evidence.get("exact_identifier_verified"),
                "final_url": browser.get("final_url"),
                "visible_text_length": browser.get("visible_text_length"),
                "error": browser.get("error"),
                "screenshot": browser.get("screenshot_path"),
            })
        if browser_rows:
            st.dataframe(pd.DataFrame(browser_rows), hide_index=True, use_container_width=True)
        for row in browser_rows:
            path = Path(str(row.get("screenshot") or ""))
            if path.is_file():
                with st.expander(f"Rendered screenshot · {row.get('candidate')}", expanded=str(row.get("candidate")) == str(selected_id)):
                    st.image(str(path), use_container_width=True)

    with tabs[5]:
        st.caption(TRACE_NOTICE)
        trace_table = event_rows(events)
        if trace_table:
            st.dataframe(pd.DataFrame(trace_table), hide_index=True, use_container_width=True)
        result_json = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        st.download_button(
            "Download complete mapping evidence",
            data=result_json.encode("utf-8"),
            file_name=f"{(result.get('product') or {}).get('row_id', 'product')}_mapping.json",
            mime="application/json",
            use_container_width=True,
        )
        candidate_csv = pd.DataFrame(candidate_rows(candidates, selected_id)).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Download candidate gate report",
            data=candidate_csv,
            file_name=f"{(result.get('product') or {}).get('row_id', 'product')}_candidates.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption(f"Artifacts: {result.get('artifact_dir')}")


st.markdown(
    """
    <div class="hero">
      <div class="hero-kicker">Exact Product Mapping</div>
      <div class="hero-title">Map the submitted product to one defensible URL</div>
      <div class="hero-copy">Manufacturer first. Retailer fallback. A URL is delivered only when the exact product identity is proven, the page opens in the rendered browser, and usable product content can be scraped.</div>
      <div class="contract-grid">
        <div class="contract-card"><b>1 · Exact identity</b><span>EAN/GTIN, model, edition and variant must agree.</span></div>
        <div class="contract-card"><b>2 · Source hierarchy</b><span>Manufacturer or publisher first; retailer only when necessary.</span></div>
        <div class="contract-card"><b>3 · Human usable</b><span>The final page must actually open and remain on a product URL.</span></div>
        <div class="contract-card"><b>4 · Scrapable</b><span>Rendered content must expose the product details needed downstream.</span></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    runtime = health()
    st.sidebar.success("Resolver ready")
    st.sidebar.caption(f"Version {runtime.get('version')} · {runtime.get('runtime_contract')}")
    st.sidebar.caption(f"Policy: {runtime.get('url_delivery_policy', 'unknown')}")
    browser = runtime.get("browser") or {}
    st.sidebar.caption(f"Browser: {browser.get('status', 'unknown')}")
    profiles = runtime.get("profiles") or {}
except Exception as exc:
    st.sidebar.error("Resolver unavailable")
    st.sidebar.code("./scripts/start.sh --build")
    st.sidebar.exception(exc)
    profiles = {"Standard": {"search_credits": 3, "max_candidates": 16, "browser_candidates": 6, "browser_required": True}}

trace_mode = st.sidebar.toggle("Live evidence trace", value=True)
poll_seconds = float(st.sidebar.select_slider("Refresh", options=[0.5, 1.0, 2.0, 3.0], value=1.0, format_func=lambda value: f"{value:g}s"))
st.sidebar.markdown(f'<div class="trace-note">{TRACE_NOTICE}</div>', unsafe_allow_html=True)

with st.form("resolve"):
    left, right = st.columns(2)
    with left:
        main_text = st.text_area("Product main text", placeholder="MENSCH TÖTE DICH NICHT!", height=120)
        country_code = st.text_input("Country code", value="CH", max_chars=2)
        retailer_name = st.text_input("Requested retailer (optional)")
    with right:
        ean = st.text_input("EAN / GTIN / ISBN (recommended)", placeholder="9783311706717")
        language_code = st.text_input("Language code (optional)", value="de")
        feature_set = st.text_input("Feature set", value="toy")
        profile_names = list(profiles) or ["Standard"]
        default_index = profile_names.index("Standard") if "Standard" in profile_names else 0
        profile_name = st.selectbox("Evidence profile", profile_names, index=default_index)
    submitted = st.form_submit_button("Map exact product to URL", type="primary", use_container_width=True)

if submitted:
    if not main_text.strip() or len(country_code.strip()) != 2:
        st.error("Product main text and a two-letter country code are required.")
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
