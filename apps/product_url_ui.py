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

st.set_page_config(page_title="Exact Product Mapping", page_icon="◆", layout="wide")
st.markdown(
    """
    <style>
    .stApp {
      background:
        radial-gradient(circle at 15% 5%, rgba(124,58,237,.18), transparent 30%),
        radial-gradient(circle at 85% 0%, rgba(6,182,212,.12), transparent 25%),
        linear-gradient(180deg, #07101f 0%, #0f172a 100%);
    }
    .block-container {max-width: 1480px; padding-top: 1.3rem; padding-bottom: 4rem;}
    .hero, .result-card {
      border: 1px solid rgba(148,163,184,.2);
      border-radius: 1rem;
      background: rgba(15,23,42,.7);
      box-shadow: 0 18px 50px rgba(0,0,0,.22);
    }
    .hero {padding: 1.45rem 1.55rem; margin-bottom: 1rem;}
    .hero-kicker {font-size:.76rem; font-weight:800; letter-spacing:.16em; color:#c4b5fd; text-transform:uppercase;}
    .hero-title {font-size:2rem; font-weight:780; margin:.25rem 0 .4rem; color:#f8fafc;}
    .hero-copy {max-width:980px; color:#cbd5e1; line-height:1.55;}
    .contract-grid {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; margin-top:1rem;}
    .contract-card {padding:.78rem .9rem; border:1px solid rgba(148,163,184,.18); border-radius:.7rem; background:rgba(2,6,23,.35);}
    .contract-card b {display:block; color:#f8fafc; font-size:.9rem; margin-bottom:.15rem;}
    .contract-card span {color:#94a3b8; font-size:.79rem;}
    .result-card {padding:1.2rem 1.35rem; margin:.75rem 0 1rem;}
    .result-ok {border-color:rgba(34,197,94,.52);}
    .result-bad {border-color:rgba(239,68,68,.52);}
    .badge {display:inline-block; padding:.25rem .55rem; border-radius:999px; font-size:.72rem; font-weight:800; letter-spacing:.06em;}
    .badge-ok {background:rgba(34,197,94,.15); color:#86efac; border:1px solid rgba(34,197,94,.34);}
    .badge-bad {background:rgba(239,68,68,.14); color:#fca5a5; border:1px solid rgba(239,68,68,.32);}
    .mapped-url {font-family:ui-monospace,SFMono-Regular,Menlo,monospace; word-break:break-all; color:#cffafe; margin-top:.7rem;}
    .stage-card {padding:.58rem .3rem; border:1px solid rgba(148,163,184,.18); border-radius:.62rem; text-align:center; background:rgba(15,23,42,.52);}
    .stage-active {border-color:rgba(34,211,238,.65);}
    .stage-complete {border-color:rgba(34,197,94,.4);}
    .muted {color:#94a3b8; font-size:.76rem;}
    div[data-testid="stMetric"], div[data-testid="stForm"] {background:rgba(15,23,42,.58); border:1px solid rgba(148,163,184,.18); padding:.75rem; border-radius:.75rem;}
    @media (max-width:900px) {.contract-grid {grid-template-columns:1fr 1fr;}}
    </style>
    """,
    unsafe_allow_html=True,
)


def api(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    response = requests.request(method, f"{API_URL}{path}", json=payload, timeout=timeout)
    if not response.ok:
        raise RuntimeError(f"API HTTP {response.status_code}: {response.text[:2000]}")
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("API returned non-object JSON")
    return data


@st.cache_data(ttl=5, show_spinner=False)
def health() -> dict[str, Any]:
    return api("GET", "/health", timeout=15)


def render_stages(events: Sequence[Mapping[str, Any]], stage: str, status: str) -> None:
    columns = st.columns(7)
    for column, row in zip(columns, stage_rows(events, stage, status)):
        state = row["state"]
        css = "stage-active" if state == "ACTIVE" else "stage-complete" if state == "COMPLETE" else ""
        marker = "●" if state == "ACTIVE" else "✓" if state == "COMPLETE" else "○"
        column.markdown(
            f'<div class="stage-card {css}"><b>{marker} {row["stage"].title()}</b><br><span class="muted">{state.title()}</span></div>',
            unsafe_allow_html=True,
        )


def run_job(payload: dict[str, Any], show_trace: bool, poll_seconds: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    job = api("POST", "/v1/jobs", payload)
    job_id = str(job["job_id"])
    events: list[dict[str, Any]] = []
    last_sequence = 0
    deadline = time.monotonic() + 1800
    metrics = st.empty()
    stages = st.empty()
    status_box = st.empty()
    trace_box = st.empty()

    while time.monotonic() < deadline:
        job = api("GET", f"/v1/jobs/{job_id}")
        trace = api("GET", f"/v1/jobs/{job_id}/trace?after_sequence={last_sequence}")
        events = merge_events(events, trace.get("events") or [])
        last_sequence = max(last_sequence, int(trace.get("last_event_sequence") or 0))

        with metrics.container():
            cols = st.columns(4)
            cols[0].metric("Job", job_id)
            cols[1].metric("Stage", str(job.get("stage") or "QUEUED").title())
            cols[2].metric("Evidence events", len(events))
            cols[3].metric("Status", str(job.get("status") or "RUNNING").replace("_", " ").title())
        with stages.container():
            render_stages(events, str(job.get("stage") or "QUEUED"), str(job.get("status") or "QUEUED"))
        status_box.info(str(job.get("message") or "Mapping product"))
        if show_trace:
            with trace_box.container():
                with st.expander("Live observable evidence", expanded=True):
                    st.caption(TRACE_NOTICE)
                    st.dataframe(pd.DataFrame(event_rows(events[-12:])), hide_index=True, use_container_width=True)
        if str(job.get("status")) in TERMINAL_STATUSES:
            return api("GET", f"/v1/jobs/{job_id}/result", timeout=60), events
        time.sleep(poll_seconds)
    raise TimeoutError("Exact product mapping exceeded 30 minutes")


def selected_judgment(events: Sequence[Mapping[str, Any]], candidate_id: str | None) -> Mapping[str, Any]:
    for event in reversed(events):
        if event.get("event_type") != "CANDIDATE_RANKING":
            continue
        ranking = (event.get("details") or {}).get("ranking") or []
        return next((item for item in ranking if item.get("candidate_id") == candidate_id), {})
    return {}


def render_result(result: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> None:
    decision = result.get("decision") or {}
    selected_url = decision.get("selected_url")
    selected_id = decision.get("selected_candidate_id")
    candidates = result.get("candidates") or []
    selected = next((item for item in candidates if item.get("candidate_id") == selected_id), {})
    rows = candidate_rows(candidates, selected_id)
    selected_row = next((item for item in rows if item.get("selected")), {})
    passed = bool(selected_url and selected_row.get("mapping_eligible"))

    badge = "ACCEPTANCE CONTRACT PASSED" if passed else "NO ACCEPTABLE URL"
    badge_class = "badge-ok" if passed else "badge-bad"
    card_class = "result-ok" if passed else "result-bad"
    title = "One product. One accepted URL." if passed else "No discovery URL was falsely accepted."
    copy = (
        "The selected URL passed exact identity, identifier, direct-page, durability, browser-access, scrapability and conflict gates."
        if passed
        else "Every discovered URL failed at least one mandatory gate in the canonical acceptance policy."
    )
    url_html = f'<div class="mapped-url">{selected_url}</div>' if selected_url else ""
    st.markdown(
        f'<div class="result-card {card_class}"><span class="badge {badge_class}">{badge}</span><h2>{title}</h2><p>{copy}</p>{url_html}</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(6)
    cols[0].metric("Exact mapping", "YES" if passed else "NO")
    cols[1].metric("Identifier", "PASS" if selected_row.get("identifier_verified") else "FAIL")
    cols[2].metric("Browser", str(selected_row.get("browser_accessible") or "—"))
    cols[3].metric("Scrapable", str(selected_row.get("scrapable") or "—"))
    cols[4].metric("Source", str(selected_row.get("source") or "—").replace("_", " ").title())
    cols[5].metric("Elapsed", f"{int(result.get('elapsed_ms') or 0) / 1000:.1f}s")

    if selected_url:
        st.link_button("Open accepted product URL", str(selected_url), use_container_width=True, type="primary")
        st.code(str(selected_url), language=None)

    tabs = st.tabs(["Decision", "Candidate gates", "Identity", "Search", "Browser", "Audit"])
    with tabs[0]:
        st.markdown("### Canonical decision")
        st.caption(f"Policy: {selected_row.get('acceptance_policy') or 'product-url-acceptance-v1'}")
        for reason in decision.get("reasons") or []:
            (st.success if passed else st.warning)(str(reason))
        for warning in decision.get("warnings") or []:
            st.warning(str(warning))
        judgment = selected_judgment(events, selected_id)
        if judgment:
            st.dataframe(pd.DataFrame(judgment.get("gates") or []), hide_index=True, use_container_width=True)

    with tabs[1]:
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("No candidate passed structural admission.")

    with tabs[2]:
        interpretation = result.get("interpretation") or {}
        signals = signal_rows(interpretation)
        hypotheses = hypothesis_rows(interpretation)
        if signals:
            st.dataframe(pd.DataFrame(signals), hide_index=True, use_container_width=True)
        if hypotheses:
            st.dataframe(pd.DataFrame(hypotheses), hide_index=True, use_container_width=True)

    with tabs[3]:
        searches = search_rows(result.get("search_observations") or [])
        if searches:
            st.dataframe(pd.DataFrame(searches), hide_index=True, use_container_width=True)

    with tabs[4]:
        browser_rows = []
        for candidate, row in zip(candidates, rows):
            browser = (candidate.get("evidence") or {}).get("browser") or {}
            browser_rows.append(
                {
                    "candidate": candidate.get("candidate_id"),
                    "eligible": row.get("mapping_eligible"),
                    "access": candidate.get("browser_access"),
                    "scrapable": candidate.get("text_extractable"),
                    "final_url": browser.get("final_url"),
                    "visible_text_length": browser.get("visible_text_length"),
                    "error": browser.get("error"),
                    "screenshot": browser.get("screenshot_path"),
                }
            )
        if browser_rows:
            st.dataframe(pd.DataFrame(browser_rows), hide_index=True, use_container_width=True)
        for row in browser_rows:
            path = Path(str(row.get("screenshot") or ""))
            if path.is_file():
                with st.expander(f"Screenshot · {row.get('candidate')}"):
                    st.image(str(path), use_container_width=True)

    with tabs[5]:
        st.caption(TRACE_NOTICE)
        st.dataframe(pd.DataFrame(event_rows(events)), hide_index=True, use_container_width=True)
        st.download_button(
            "Download complete evidence",
            data=json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
            file_name=f"{(result.get('product') or {}).get('row_id', 'product')}_mapping.json",
            mime="application/json",
            use_container_width=True,
        )
        st.download_button(
            "Download candidate gates",
            data=pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{(result.get('product') or {}).get('row_id', 'product')}_candidates.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.caption(f"Artifacts: {result.get('artifact_dir')}")


st.markdown(
    """
    <div class="hero">
      <div class="hero-kicker">Exact Product Mapping</div>
      <div class="hero-title">Map the submitted product to one accepted URL</div>
      <div class="hero-copy">One canonical policy decides acceptance. Manufacturer or publisher first, then retailer fallback. No search snippet, inaccessible page, or unverified candidate can become the final URL.</div>
      <div class="contract-grid">
        <div class="contract-card"><b>Exact identity</b><span>Product, edition, format and variant must agree.</span></div>
        <div class="contract-card"><b>Identifier agreement</b><span>Supplied EAN, GTIN or ISBN must be verified.</span></div>
        <div class="contract-card"><b>Browser accessible</b><span>The final direct product page must render successfully.</span></div>
        <div class="contract-card"><b>Scrapable content</b><span>Rendered product details must be available downstream.</span></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    runtime = health()
    st.sidebar.success("Resolver ready")
    st.sidebar.caption(f"Version {runtime.get('version')} · {runtime.get('runtime_contract')}")
    st.sidebar.caption(f"Policy: {runtime.get('acceptance_policy', 'unknown')}")
    st.sidebar.caption(f"Policy module: {runtime.get('acceptance_policy_module', 'unknown')}")
    browser = runtime.get("browser") or {}
    st.sidebar.caption(f"Browser: {browser.get('status', 'unknown')}")
    profiles = runtime.get("profiles") or {}
except Exception as exc:
    st.sidebar.error("Resolver unavailable")
    st.sidebar.code("./scripts/start.sh --build")
    st.sidebar.exception(exc)
    profiles = {"Standard": {"search_credits": 3, "max_candidates": 16, "browser_candidates": 6, "browser_required": True}}

show_trace = st.sidebar.toggle("Live evidence trace", value=True)
poll_seconds = float(st.sidebar.select_slider("Refresh", options=[0.5, 1.0, 2.0, 3.0], value=1.0, format_func=lambda value: f"{value:g}s"))
st.sidebar.caption(TRACE_NOTICE)

with st.form("resolve"):
    left, right = st.columns(2)
    with left:
        main_text = st.text_area("Product main text", placeholder="MENSCH TÖTE DICH NICHT!", height=120)
        country_code = st.text_input("Country code", value="CH", max_chars=2)
        retailer_name = st.text_input("Requested retailer (optional)")
    with right:
        ean = st.text_input("EAN / GTIN / ISBN", placeholder="9783311706717")
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
            result, events = run_job(payload, show_trace, poll_seconds)
            render_result(result, events)
        except Exception as exc:
            st.exception(exc)
