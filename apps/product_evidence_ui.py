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

from product_evidence_harness.executive_summary import build_executive_summary  # noqa: E402
from product_evidence_harness.runtime_controls import default_runtime_controls  # noqa: E402


AGENT_URL = os.getenv("PRODUCT_AGENT_URL", "http://127.0.0.1:8788").rstrip("/")
EXPECTED_RUNTIME = "belief-url-resolution-v11-url-delivery-first"
TERMINAL_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}
MAX_POLL_SECONDS = 30 * 60
DEFAULT_FEATURE_SET = os.getenv("PRODUCT_UI_FEATURE_SET", "toy_features")

EXECUTION_PROFILES: dict[str, dict[str, int]] = {
    "Focused": {
        "serpapi_credits": 2,
        "full_scrapes": 3,
        "scrapes_per_domain": 1,
        "planner_candidates": 6,
        "agentic_candidates": 2,
        "browser_turns_per_candidate": 3,
        "browser_actions_per_candidate": 4,
        "images_in_reasoning": 6,
    },
    "Standard": default_runtime_controls(),
    "Extended": {
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

PROGRESS_STAGES = (
    ("UNDERSTAND", "Understand"),
    ("SEARCH", "Search"),
    ("VERIFY", "Verify"),
    ("DELIVER", "Deliver URL"),
)

st.set_page_config(
    page_title="Product URL Finder",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def api_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    response = requests.request(method, f"{AGENT_URL}{path}", json=payload, timeout=timeout)
    if not response.ok:
        raise RuntimeError(
            f"Agent API returned HTTP {response.status_code}: {response.text[:4000]}"
        )
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Agent API returned a non-object JSON response")
    return data


@st.cache_data(ttl=5, show_spinner=False)
def runtime_health() -> dict[str, Any]:
    return api_json("GET", "/health", timeout=15)


def clean_optional(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def compact(value: Any, limit: int = 260) -> str:
    if value in (None, "", [], {}, ()):
        return "—"
    text = (
        json.dumps(value, ensure_ascii=False, default=str)
        if isinstance(value, (dict, list, tuple))
        else str(value)
    )
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def percentage(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return "Not available"
    if number != number:
        return "Not available"
    if number > 1:
        number /= 100.0
    return f"{max(0.0, min(1.0, number)):.1%}"


def readable(value: Any) -> str:
    return str(value or "Not available").replace("_", " ").strip().title()


def yes_no(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Not assessed"


def runtime_sidebar() -> dict[str, Any] | None:
    st.sidebar.header("System status")
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
        st.sidebar.success("Ready")
    elif health.get("status") == "healthy":
        st.sidebar.warning("Agent rebuild required")
        st.sidebar.code("./scripts/azureml_startup.sh --clean-build")
    else:
        st.sidebar.error(f"Runtime: {health.get('status') or 'unknown'}")
    st.sidebar.caption(f"Evidence browser: {browser.get('status') or 'unknown'}")
    st.sidebar.caption(f"Runtime: {contract}")
    return health


def progress_key(stage: str, status: str) -> str:
    value = f"{stage} {status}".upper()
    if any(token in value for token in ("VALIDATING_INPUT", "PRODUCT_UNDERSTANDING")):
        return "UNDERSTAND"
    if any(token in value for token in ("SEARCH", "DISCOVER", "SCRAP")):
        return "SEARCH"
    if any(token in value for token in ("BROWSER", "REASON", "IDENT", "VALIDAT")):
        return "VERIFY"
    if any(token in value for token in ("WRITING", "COMPLETED", "REVIEW")):
        return "DELIVER"
    return "UNDERSTAND"


def progress_fraction(key: str) -> float:
    return {"UNDERSTAND": 0.15, "SEARCH": 0.45, "VERIFY": 0.75, "DELIVER": 0.95}.get(key, 0.05)


def render_progress(active: str | None = None, complete: bool = False) -> None:
    columns = st.columns(len(PROGRESS_STAGES))
    keys = [key for key, _ in PROGRESS_STAGES]
    active_index = keys.index(active) if active in keys else -1
    for index, (key, label) in enumerate(PROGRESS_STAGES):
        marker = "✓" if complete or index < active_index else "●" if key == active else "○"
        with columns[index]:
            st.caption(f"{marker} {label}")


def summary_for(result: Mapping[str, Any]) -> dict[str, Any]:
    existing = result.get("executive_summary")
    return dict(existing) if isinstance(existing, Mapping) else build_executive_summary(result)


def render_status(summary: Mapping[str, Any]) -> None:
    status = str(summary.get("overall_status") or "UNKNOWN")
    headline = str(summary.get("headline") or "URL result unavailable")
    if status == "URL_DELIVERED_VERIFIED":
        st.success(f"**{headline}**")
    elif status == "URL_DELIVERED_REVIEW_REQUIRED":
        st.warning(f"**{headline}**")
    else:
        st.error(f"**{headline}**")


def render_primary_metrics(summary: Mapping[str, Any]) -> None:
    pillars = dict(summary.get("pillars") or {})
    source = dict(pillars.get("source") or {})
    evidence = dict(pillars.get("evidence") or {})
    identity = dict(pillars.get("identity") or {})
    usability = dict(pillars.get("usability") or {})

    columns = st.columns(4)
    with columns[0]:
        st.metric("Source", readable(source.get("status")))
        st.caption(f"{readable(source.get('source_role'))} · {readable(source.get('source_tier'))}")
    with columns[1]:
        st.metric("Evidence", readable(evidence.get("status")))
        st.caption(
            f"{evidence.get('atomic_evidence_items', 0)} evidence items · "
            f"{percentage(evidence.get('required_coverage'))} coverage"
        )
    with columns[2]:
        st.metric("Identity", readable(identity.get("status")))
        st.caption(
            f"{percentage(identity.get('confidence'))} confidence · "
            f"{identity.get('unresolved_items', 0)} unresolved"
        )
    with columns[3]:
        st.metric("Usability", readable(usability.get("status")))
        st.caption(
            f"{usability.get('passed_checks', 0)} / {usability.get('assessed_checks', 0) or 6} checks passed"
        )


def render_usability(summary: Mapping[str, Any]) -> None:
    usability = dict((summary.get("pillars") or {}).get("usability") or {})
    rows = [
        {"Check": item.get("label"), "Result": readable(item.get("status"))}
        for item in usability.get("checks") or []
        if isinstance(item, Mapping)
    ]
    if rows:
        st.subheader("URL usability")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_candidate_table(summary: Mapping[str, Any]) -> None:
    rows = []
    for item in summary.get("candidate_summary") or []:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "Decision": item.get("decision"),
                "Identity": readable(item.get("identity_status")),
                "Coverage": percentage(item.get("coverage")),
                "Openable": yes_no(item.get("browser_openable")),
                "Extractable": yes_no(item.get("text_scrapable")),
                "Reusable": yes_no(item.get("durable_url")),
                "URL": item.get("url"),
                "Reason": compact(item.get("reason"), 300),
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_search_details(result: Mapping[str, Any]) -> None:
    rows = []
    for index, item in enumerate((result.get("search") or {}).get("stages") or [], start=1):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "Step": index,
                "Route": readable(item.get("name") or item.get("stage") or item.get("market_stage")),
                "Engine": item.get("engine"),
                "Results": item.get("results_returned") or item.get("raw_results_seen") or 0,
                "Qualified": item.get("candidates_qualified") or 0,
                "Extracted": item.get("candidates_scraped") or 0,
                "Query": compact(item.get("query"), 220),
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No search-stage trace was returned.")


def render_identity_details(result: Mapping[str, Any]) -> None:
    identity = dict(result.get("product_identification") or {})
    hypothesis = identity.get("leading_hypothesis") or identity.get("selected_hypothesis") or {}
    st.json(hypothesis or identity, expanded=False)


def render_evidence_details(result: Mapping[str, Any]) -> None:
    identity = dict(result.get("product_identification") or {})
    rows = []
    for item in identity.get("evidence_ledger") or []:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "Field": item.get("field"),
                "Value": item.get("value"),
                "Support": readable(item.get("polarity")),
                "Reliability": percentage(item.get("source_reliability")),
                "Confidence": percentage(item.get("extraction_confidence")),
                "Source": item.get("source_url"),
            }
        )
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No atomic evidence ledger was returned.")


def render_audit_details(result: Mapping[str, Any]) -> None:
    steps = [
        item
        for item in (result.get("business_judgement_review") or {}).get("steps") or []
        if isinstance(item, Mapping)
    ]
    if not steps:
        st.info("No structured decision audit was returned.")
        return
    for item in steps:
        with st.expander(
            f"Step {item.get('sequence_number') or '—'} · {readable(item.get('decision_stage'))}"
        ):
            st.markdown(f"**Evidence:** {compact(item.get('evidence_considered'), 800)}")
            st.markdown(f"**Rule:** {compact(item.get('business_rule_applied'), 600)}")
            st.markdown(f"**Decision:** {compact(item.get('agent_judgement'), 600)}")
            st.markdown(f"**Effect:** {compact(item.get('effect_on_next_action'), 600)}")


def render_artifacts(result: Mapping[str, Any], elapsed_seconds: float | None) -> None:
    if elapsed_seconds is not None:
        st.metric("Elapsed", f"{elapsed_seconds:.1f}s")
    row_id = str((result.get("product") or {}).get("row_id") or "").strip()
    root = PROJECT_ROOT / "data" / "artifacts" / row_id if row_id else None
    if root and root.is_dir():
        files = sorted(path for path in root.rglob("*") if path.is_file())
        st.caption(str(root))
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Artifact": str(path.relative_to(root)),
                        "Size KB": round(path.stat().st_size / 1024, 2),
                    }
                    for path in files
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("Artifact directory is not available to this process.")
    with st.expander("Technical result JSON"):
        st.json(result, expanded=False)


def render_review_details(
    result: Mapping[str, Any],
    summary: Mapping[str, Any],
    elapsed_seconds: float | None,
) -> None:
    with st.expander("Review details", expanded=False):
        candidate_tab, evidence_tab, search_tab, identity_tab, audit_tab, artifact_tab = st.tabs(
            ["Candidates", "Evidence", "Search", "Identity", "Decision audit", "Artifacts"]
        )
        with candidate_tab:
            render_candidate_table(summary)
        with evidence_tab:
            render_evidence_details(result)
        with search_tab:
            render_search_details(result)
        with identity_tab:
            render_identity_details(result)
        with audit_tab:
            render_audit_details(result)
        with artifact_tab:
            render_artifacts(result, elapsed_seconds)


def render_result(result: dict[str, Any], elapsed_seconds: float | None = None) -> None:
    summary = summary_for(result)
    selected_url = clean_optional(summary.get("selected_url"))

    st.divider()
    render_progress("DELIVER", complete=True)
    render_status(summary)

    if selected_url:
        st.link_button(
            "Open product URL",
            selected_url,
            type="primary",
            use_container_width=True,
        )
        st.code(selected_url, language=None)
        st.caption(
            f"Source: {readable(summary.get('source_role'))} · "
            f"Identity: {readable(summary.get('identity_status'))} · "
            f"Confidence: {percentage(summary.get('identity_confidence'))}"
        )
    else:
        st.error(
            "The required product URL was not delivered. This run is not a successful output and requires escalation."
        )

    render_primary_metrics(summary)

    st.subheader("Justification")
    st.write(summary.get("conclusion") or "No conclusion was returned.")

    if selected_url:
        render_usability(summary)
        reasons = [str(item) for item in summary.get("decision_reasons") or [] if str(item).strip()]
        if reasons:
            with st.expander("Why this URL was selected", expanded=False):
                for item in reasons:
                    st.markdown(f"- {item}")
    else:
        with st.expander("URL delivery failure diagnostics", expanded=False):
            work = dict(summary.get("work_completed") or {})
            st.write(
                f"Search actions: {work.get('search_actions_used', 0)} / "
                f"{work.get('search_action_limit', 0)} · "
                f"Results reviewed: {work.get('results_seen', 0)} · "
                f"Candidate URLs: {work.get('candidate_urls_seen', 0)}"
            )
            for item in summary.get("next_actions") or []:
                st.markdown(f"- {item}")

    render_review_details(result, summary, elapsed_seconds)


def friendly_error(exc: Exception) -> tuple[str, str]:
    detail = f"{type(exc).__name__}: {exc}"
    if "STALE_AGENT_IMAGE" in detail or "runtime_contract" in detail.lower():
        return (
            "The running agent is incompatible with this application.",
            "Run ./scripts/azureml_startup.sh --clean-build and reopen the application.",
        )
    return (
        "The product URL run failed.",
        "Open the technical detail below and inspect the generated failure artifact.",
    )


st.title("Product URL Finder")
st.markdown(
    "Return the strongest usable **product URL** with supporting Source, Evidence, Identity and Usability validation."
)

health = runtime_sidebar()

if "run_row_id" not in st.session_state:
    st.session_state.run_row_id = (
        f"RUN-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    )

with st.form("product_url_form", clear_on_submit=False):
    main_text = st.text_area(
        "Product text *",
        placeholder="Paste the product description, title or source text",
        height=100,
    )
    country_col, retailer_col, ean_col = st.columns(3)
    with country_col:
        country_code = st.text_input("Country code *", value="CH", max_chars=2)
    with retailer_col:
        retailer_name = st.text_input("Retailer", placeholder="Optional")
    with ean_col:
        ean = st.text_input("EAN / GTIN", placeholder="Optional")

    with st.expander("Advanced settings", expanded=False):
        profile_col, language_col = st.columns(2)
        with profile_col:
            execution_profile = st.selectbox("Search depth", tuple(EXECUTION_PROFILES), index=1)
        with language_col:
            language_code = st.text_input("Language", placeholder="Optional, e.g. de")

    submitted = st.form_submit_button(
        "Find product URL",
        type="primary",
        use_container_width=True,
        disabled=health is None
        or str((health or {}).get("runtime_contract_version")) != EXPECTED_RUNTIME,
    )

if submitted:
    row_id = st.session_state.run_row_id
    if not main_text.strip():
        st.error("Product text is required.")
    elif len(country_code.strip()) != 2 or not country_code.strip().isalpha():
        st.error("Country code must contain exactly two letters.")
    else:
        payload = {
            "product": {
                "row_id": row_id,
                "main_text": main_text.strip(),
                "country_code": country_code.strip().upper(),
                "retailer_name": clean_optional(retailer_name),
                "ean": clean_optional(ean),
                "language_code": clean_optional(language_code.lower()),
            },
            "feature_set": DEFAULT_FEATURE_SET,
            "runtime_options": EXECUTION_PROFILES[execution_profile],
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
                    raise TimeoutError("The run exceeded the 30-minute polling limit")
                status_payload = api_json("GET", f"/v1/jobs/{job_id}", timeout=20)
                signature = (
                    status_payload.get("status"),
                    status_payload.get("stage"),
                    status_payload.get("message"),
                )
                if signature != last_signature:
                    stage = str(status_payload.get("stage") or "")
                    state = str(status_payload.get("status") or "")
                    key = progress_key(stage, state)
                    status_box.info(
                        f"{dict(PROGRESS_STAGES).get(key, 'Working')} · "
                        f"{status_payload.get('message') or 'Processing'}"
                    )
                    with flow_box.container():
                        render_progress(key)
                    progress_bar.progress(
                        progress_fraction(key),
                        text=dict(PROGRESS_STAGES).get(key, "Working"),
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
            st.session_state.run_result = result
            st.session_state.run_elapsed_seconds = elapsed
            st.session_state.run_job_id = job_id
            st.session_state.run_row_id = (
                f"RUN-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            )
            progress_bar.progress(1.0, text="Product URL ready")
            status_box.empty()
            flow_box.empty()
        except Exception as exc:
            elapsed = time.monotonic() - started
            progress_bar.empty()
            status_box.empty()
            flow_box.empty()
            title, action = friendly_error(exc)
            st.error(f"{title} {action}")
            with st.expander("Technical error detail", expanded=True):
                st.code(f"{type(exc).__name__}: {exc}")
                st.caption(f"Elapsed before failure: {elapsed:.1f}s")

if "run_result" in st.session_state:
    render_result(
        st.session_state.run_result,
        st.session_state.get("run_elapsed_seconds"),
    )
else:
    st.caption("Output: product URL, source, evidence, identity confidence and usability status.")
