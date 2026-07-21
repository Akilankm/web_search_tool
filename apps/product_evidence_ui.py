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

from product_evidence_harness.numeric_safety import safe_int  # noqa: E402
from product_evidence_harness.runtime_controls import (  # noqa: E402
    RUNTIME_CONTROL_SPECS,
    default_runtime_controls,
)

AGENT_URL = os.getenv("PRODUCT_AGENT_URL", "http://127.0.0.1:8788").rstrip("/")
EXPECTED_RUNTIME = "belief-url-resolution-v9-product-evidence-ui"
TERMINAL_STATUSES = {"COMPLETED", "REVIEW_REQUIRED", "FAILED"}
MAX_POLL_SECONDS = 30 * 60

EXECUTION_PROFILES: dict[str, dict[str, int]] = {
    "Latency Optimized": {
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
    "Coverage Optimized": {
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
    ("INPUT", "Input", "Validate product and market context"),
    ("INTERPRET", "Interpret", "Extract identity claims and ambiguity"),
    ("DISCOVER", "Discover", "Collect evidence from relevant sources"),
    ("COMPARE", "Compare", "Evaluate competing product hypotheses"),
    ("RESOLVE", "Resolve", "Select the strongest product identity"),
    ("VALIDATE", "Validate", "Check evidence consistency and gaps"),
    ("REPORT", "Report", "Persist identification and audit artifacts"),
)

STAGE_TO_FLOW = {
    "VALIDATING_INPUT": "INPUT",
    "PRODUCT_UNDERSTANDING": "INTERPRET",
    "SEARCHING": "DISCOVER",
    "ADAPTIVE_SEARCH": "DISCOVER",
    "SCRAPING": "COMPARE",
    "REQUESTING_BROWSER_EVIDENCE": "COMPARE",
    "AGENTIC_BROWSER_INVESTIGATION": "COMPARE",
    "RUNNING_MULTIMODAL_REASONING": "RESOLVE",
    "VALIDATING_PRIMARY_URL": "VALIDATE",
    "WRITING_OUTPUTS": "REPORT",
    "COMPLETED": "REPORT",
    "REVIEW_REQUIRED": "REPORT",
    "FAILED": "REPORT",
}

STAGE_PROGRESS = {
    "VALIDATING_INPUT": 0.05,
    "PRODUCT_UNDERSTANDING": 0.16,
    "SEARCHING": 0.27,
    "ADAPTIVE_SEARCH": 0.37,
    "SCRAPING": 0.49,
    "REQUESTING_BROWSER_EVIDENCE": 0.59,
    "AGENTIC_BROWSER_INVESTIGATION": 0.69,
    "RUNNING_MULTIMODAL_REASONING": 0.79,
    "VALIDATING_PRIMARY_URL": 0.88,
    "WRITING_OUTPUTS": 0.96,
    "COMPLETED": 1.0,
    "REVIEW_REQUIRED": 1.0,
    "FAILED": 1.0,
}

st.set_page_config(
    page_title="Product Identification Platform",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
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
    return text if len(text) <= limit else text[: limit - 1] + "…"


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number == number else None


def percentage(value: Any) -> str:
    number = safe_float(value)
    if number is None:
        return "—"
    if number <= 1:
        number *= 100
    return f"{max(0.0, min(100.0, number)):.1f}%"


def stage_progress(stage: str, status: str) -> float:
    upper = (stage or status or "").upper()
    return next((value for key, value in STAGE_PROGRESS.items() if key in upper), 0.10)


def flow_key(stage: str, status: str = "") -> str:
    upper = (stage or status or "").upper()
    return next((value for key, value in STAGE_TO_FLOW.items() if key in upper), "INPUT")


def render_workflow(active: str | None = None, terminal: bool = False) -> None:
    keys = [item[0] for item in WORKFLOW]
    active_index = keys.index(active) if active in keys else -1
    columns = st.columns(len(WORKFLOW))
    for index, (key, title, detail) in enumerate(WORKFLOW):
        if terminal or index < active_index:
            state = "✓"
        elif key == active:
            state = "●"
        else:
            state = "○"
        with columns[index]:
            st.markdown(f"**{state} {title}**")
            st.caption(detail)


def initialize_control_state(profile: str) -> None:
    profile_values = EXECUTION_PROFILES[profile]
    profile_changed = st.session_state.get("active_execution_profile") != profile
    for spec in RUNTIME_CONTROL_SPECS:
        key = f"control_{spec.key}"
        fallback = profile_values.get(spec.key, spec.default)
        current = st.session_state.get(key)
        normalized = safe_int(
            current,
            fallback,
            minimum=spec.minimum,
            maximum=spec.maximum,
            field_name=key,
        )
        if profile_changed or current is None or normalized != current:
            st.session_state[key] = fallback if profile_changed else normalized
    st.session_state["active_execution_profile"] = profile


def runtime_controls() -> dict[str, int]:
    st.sidebar.subheader("Runtime controls")
    profile = st.sidebar.selectbox("Execution profile", tuple(EXECUTION_PROFILES), index=1)
    initialize_control_state(profile)
    controls: dict[str, int] = {}
    for spec in RUNTIME_CONTROL_SPECS:
        key = f"control_{spec.key}"
        fallback = EXECUTION_PROFILES[profile].get(spec.key, spec.default)
        raw = st.sidebar.number_input(
            spec.label,
            min_value=spec.minimum,
            max_value=spec.maximum,
            value=safe_int(
                st.session_state.get(key),
                fallback,
                minimum=spec.minimum,
                maximum=spec.maximum,
                field_name=key,
            ),
            step=1,
            key=key,
            help=spec.help_text,
        )
        controls[spec.key] = safe_int(
            raw,
            fallback,
            minimum=spec.minimum,
            maximum=spec.maximum,
            field_name=key,
        )
    st.sidebar.caption(
        "Controls change evidence depth for one job. Product-identity rules remain fixed."
    )
    return controls


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
        st.sidebar.warning(f"Incompatible runtime: {contract}")
    else:
        st.sidebar.error(f"Runtime: {health.get('status') or 'unknown'}")
    st.sidebar.caption(f"Agent · {AGENT_URL}")
    st.sidebar.caption(f"Evidence browser · {browser.get('status') or 'unknown'}")
    st.sidebar.caption(f"Contract · {contract}")
    return health


def identity_components(result: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    identity = dict(result.get("product_identification") or {})
    hypothesis = identity.get("leading_hypothesis") or identity.get("selected_hypothesis") or {}
    return identity, dict(hypothesis) if isinstance(hypothesis, Mapping) else {}


def identity_field_map(identity: Mapping[str, Any], hypothesis: Mapping[str, Any]) -> dict[str, Any]:
    attributes = dict(hypothesis.get("attributes") or {})
    aliases = {
        "Brand": ("brand",),
        "Manufacturer": ("manufacturer", "toy_manufacturer"),
        "Model / series": ("model", "model_number", "series", "product_line"),
        "Product form": ("product_form", "form", "format"),
        "Variant": ("variant", "edition", "flavour", "color"),
        "Size": ("size", "dimensions"),
        "Quantity / pack": ("quantity", "pack", "pack_size", "pack_configuration"),
    }
    values: dict[str, Any] = {}
    for label, keys in aliases.items():
        for key in keys:
            if attributes.get(key) not in (None, "", [], {}):
                values[label] = attributes[key]
                break
    for claim in identity.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        field = str(claim.get("field") or "").strip().lower().replace("_", " ")
        for label, keys in aliases.items():
            if label in values:
                continue
            if field in {key.replace("_", " ") for key in keys}:
                values[label] = claim.get("value")
    return values


def unresolved_items(identity: Mapping[str, Any]) -> list[str]:
    items: list[str] = []
    for uncertainty in identity.get("uncertainties") or []:
        if isinstance(uncertainty, Mapping):
            items.append(
                f"{compact(uncertainty.get('field'), 80)}: "
                f"{compact(uncertainty.get('candidate_values'), 180)}"
            )
        elif uncertainty:
            items.append(str(uncertainty))
    items.extend(str(item) for item in identity.get("unknowns") or [] if item)
    return items


def render_identity_status(status: str, name: str) -> None:
    if status == "EXACT":
        st.success(f"Product identified: {name}")
    elif status == "PROBABLE":
        st.warning(f"Probable product identification: {name}")
    elif status in {"AMBIGUOUS", "CONFLICTING", "INSUFFICIENT_EVIDENCE"}:
        st.warning(f"Product identification requires review: {name}")
    else:
        st.info(f"Product identification status: {status} · {name}")


def render_source_checks(acceptance: Mapping[str, Any]) -> None:
    checks = (
        ("browser_openable", "Rendered evidence"),
        ("text_scrapable", "Text evidence"),
        ("rendered_product_verified", "Product-page evidence"),
        ("exact_product_verified", "Identity support"),
        ("full_feature_coverage", "Feature evidence"),
        ("durable_url", "Reusable source"),
    )
    visible = [(key, label) for key, label in checks if key in acceptance]
    if not visible:
        st.info("No source-quality assessment was recorded. Product identity is evaluated separately.")
        return
    columns = st.columns(len(visible))
    for column, (key, label) in zip(columns, visible):
        value = acceptance.get(key)
        state = "VERIFIED" if value is True else "NOT VERIFIED" if value is False else "NOT ASSESSED"
        with column:
            st.metric(label, state)


def render_search_route(search: Mapping[str, Any]) -> None:
    stages = [item for item in search.get("stages") or [] if isinstance(item, Mapping)]
    if not stages:
        st.info("No stage-level evidence-discovery trace was returned.")
        return
    for index, item in enumerate(stages, start=1):
        title = item.get("name") or item.get("stage") or item.get("market_stage") or "search"
        st.markdown(
            f"**{index}. {str(title).replace('_', ' ').title()}** · "
            f"engine `{item.get('engine') or '—'}` · results **{item.get('results_returned') or item.get('result_count') or 0}**  \n"
            f"Query: `{compact(item.get('query'), 220)}`  \n"
            f"Decision: {compact(item.get('reason'), 300)}"
        )


def render_judgment_sequence(result: Mapping[str, Any]) -> None:
    review = dict(result.get("business_judgement_review") or {})
    steps = [item for item in review.get("steps") or [] if isinstance(item, Mapping)]
    if not steps:
        st.info("No structured business judgment sequence was returned.")
        return
    st.caption(
        "Observable evidence → explicit rule → product judgment → next action. "
        "This is an audit representation, not hidden chain-of-thought."
    )
    for item in steps:
        with st.expander(
            f"Step {compact(item.get('sequence_number'), 20)} · "
            f"{compact(item.get('decision_stage'), 100)}",
            expanded=False,
        ):
            st.markdown(f"**Question:** {compact(item.get('business_question'), 400)}")
            st.markdown(f"**Evidence:** {compact(item.get('evidence_considered'), 700)}")
            st.markdown(f"**Rule:** {compact(item.get('business_rule_applied'), 500)}")
            st.markdown(f"**Judgment:** {compact(item.get('agent_judgement'), 500)}")
            st.markdown(f"**Next action:** {compact(item.get('effect_on_next_action'), 500)}")


def render_claims(identity: Mapping[str, Any]) -> None:
    rows = [
        {
            "Field": item.get("field"),
            "Value": item.get("value"),
            "Status": item.get("status"),
            "Confidence": percentage(item.get("confidence")),
            "Source tokens": compact(item.get("source_tokens"), 180),
        }
        for item in identity.get("claims") or []
        if isinstance(item, Mapping)
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No structured identity claims were returned.")


def render_evidence(identity: Mapping[str, Any]) -> None:
    rows = [
        {
            "Field": item.get("field"),
            "Value": item.get("value"),
            "Polarity": item.get("polarity"),
            "Source": item.get("source_url"),
            "Reliability": percentage(item.get("source_reliability")),
            "Extraction confidence": percentage(item.get("extraction_confidence")),
            "Excerpt": compact(item.get("excerpt"), 220),
        }
        for item in identity.get("evidence_ledger") or []
        if isinstance(item, Mapping)
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No atomic evidence ledger was returned.")


def render_hypotheses(identity: Mapping[str, Any], leading_id: str | None) -> None:
    rows = [
        {
            "Selected": item.get("hypothesis_id") == leading_id,
            "Product hypothesis": item.get("canonical_name"),
            "Category": item.get("category"),
            "Posterior": percentage(item.get("posterior_probability")),
            "Assumptions": compact(item.get("assumptions"), 260),
            "Contradictions": len(item.get("contradicting_evidence_ids") or []),
        }
        for item in identity.get("hypotheses") or []
        if isinstance(item, Mapping)
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No alternative product hypotheses were returned.")


def source_link(label: str, url: str | None) -> None:
    if url:
        st.link_button(label, url, use_container_width=True)
    else:
        st.button(label, disabled=True, use_container_width=True)


def host_artifact_dir(result: Mapping[str, Any]) -> Path | None:
    row_id = str((result.get("product") or {}).get("row_id") or "").strip()
    return PROJECT_ROOT / "data" / "artifacts" / row_id if row_id else None


def render_result(result: dict[str, Any], elapsed_seconds: float | None = None) -> None:
    job_status = str(result.get("job_status") or "UNKNOWN").upper()
    identity, hypothesis = identity_components(result)
    resolution = str(identity.get("resolution_status") or "UNKNOWN").upper()
    product_name = str(
        hypothesis.get("canonical_name")
        or identity.get("canonical_name")
        or identity.get("product_name")
        or "Product not resolved"
    )
    confidence = next(
        (
            safe_float(hypothesis.get(key))
            for key in ("posterior_probability", "confidence", "score")
            if safe_float(hypothesis.get(key)) is not None
        ),
        None,
    )
    claims = [item for item in identity.get("claims") or [] if isinstance(item, Mapping)]
    evidence = [item for item in identity.get("evidence_ledger") or [] if isinstance(item, Mapping)]
    hypotheses = [item for item in identity.get("hypotheses") or [] if isinstance(item, Mapping)]
    unresolved = unresolved_items(identity)
    fields = identity_field_map(identity, hypothesis)

    st.divider()
    render_workflow("REPORT", terminal=True)
    if job_status == "FAILED":
        st.error("Technical execution failure. No product identity was fabricated.")
    else:
        render_identity_status(resolution, product_name)

    st.header(product_name)
    st.caption(
        f"Identification status: {resolution} · Confidence: {percentage(confidence)} · "
        "Source URLs are supporting evidence only."
    )

    summary_columns = st.columns(6)
    values = (
        ("Resolution", resolution),
        ("Confidence", percentage(confidence)),
        ("Identity claims", len(claims)),
        ("Evidence items", len(evidence)),
        ("Hypotheses", len(hypotheses)),
        ("Unresolved", len(unresolved)),
    )
    for column, (label, value) in zip(summary_columns, values):
        with column:
            st.metric(label, value)

    if fields:
        field_columns = st.columns(min(4, len(fields)))
        for index, (label, value) in enumerate(fields.items()):
            with field_columns[index % len(field_columns)]:
                st.metric(label, compact(value, 90))

    identity_tab, evidence_tab, alternatives_tab, sources_tab, audit_tab, artifacts_tab = st.tabs(
        [
            "Product identity",
            "Evidence basis",
            "Alternative hypotheses",
            "Source evidence",
            "Decision audit",
            "Artifacts",
        ]
    )

    with identity_tab:
        left, right = st.columns([1.2, 1])
        with left:
            st.subheader("Selected product hypothesis")
            st.json(hypothesis or identity, expanded=True)
        with right:
            st.subheader("Resolution diagnostics")
            metrics = dict(identity.get("metrics") or {})
            if metrics:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {"Metric": key.replace("_", " ").title(), "Value": value}
                            for key, value in metrics.items()
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
            if unresolved:
                st.subheader("Unresolved distinctions")
                for item in unresolved:
                    st.markdown(f"- {item}")
            else:
                st.success("No unresolved identity distinctions were recorded.")

    with evidence_tab:
        st.subheader("Identity claims")
        render_claims(identity)
        st.subheader("Atomic evidence ledger")
        render_evidence(identity)

    with alternatives_tab:
        st.caption(
            "These are competing product identities—not competing URLs. Posterior evidence determines whether the result is exact, probable, ambiguous or conflicting."
        )
        render_hypotheses(identity, str(hypothesis.get("hypothesis_id") or "") or None)

    with sources_tab:
        st.info(
            "A URL is an evidence location. Missing or unusable URLs do not automatically invalidate a product hypothesis."
        )
        links = st.columns(3)
        with links[0]:
            source_link("Primary evidence source", result.get("primary_url"))
        with links[1]:
            source_link("Manufacturer evidence", result.get("manufacturer_url"))
        with links[2]:
            source_link("Retailer evidence", result.get("retailer_url"))

        acceptance = dict(result.get("primary_url_acceptance") or {})
        st.subheader("Source-quality assessment")
        render_source_checks(acceptance)
        st.subheader("Evidence discovery route")
        render_search_route(dict(result.get("search") or {}))

        assessments = [
            item for item in result.get("feature_assessments") or [] if isinstance(item, Mapping)
        ]
        if assessments:
            st.subheader("Candidate source evidence")
            for item in assessments:
                with st.expander(compact(item.get("url"), 180)):
                    st.markdown(f"**Identity evidence:** {compact(item.get('identity_status'))}")
                    st.markdown(f"**Feature evidence:** {compact(item.get('coverage'))}")
                    st.markdown(f"**Missing:** {compact(item.get('missing_features'))}")
                    st.markdown(f"**Conflicts:** {compact(item.get('conflicting_features'))}")
                    st.markdown(f"**Not retained because:** {compact(item.get('rejection_reasons'), 700)}")

    with audit_tab:
        render_judgment_sequence(result)

    with artifacts_tab:
        if elapsed_seconds is not None:
            st.metric("Elapsed", f"{elapsed_seconds:.1f}s")
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
        else:
            st.warning("Artifact directory is not available to this process.")
        with st.expander("Technical result JSON"):
            st.json(result, expanded=False)


def friendly_error(exc: Exception) -> tuple[str, str]:
    detail = f"{type(exc).__name__}: {exc}"
    if "STALE_AGENT_IMAGE" in detail or "runtime_contract" in detail.lower():
        return (
            "The running agent is incompatible with this application.",
            "Run ./scripts/azureml_startup.sh --clean-build and reopen the application.",
        )
    return (
        "The product-identification run could not complete.",
        "Open the technical detail below. No product identity was fabricated.",
    )


st.title("Product Identification Platform")
st.markdown(
    "Identify the intended product from incomplete source text. "
    "**Web pages and URLs are supporting evidence—not the product result.**"
)

health = runtime_sidebar()
controls = runtime_controls()
render_workflow()

if "run_row_id" not in st.session_state:
    st.session_state.run_row_id = (
        f"RUN-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
    )

with st.form("product_identification_form", clear_on_submit=False):
    st.subheader("Product input")
    main_text = st.text_area(
        "Main product text *",
        placeholder="Paste the incomplete product description",
        height=95,
    )
    first, second, third = st.columns(3)
    with first:
        country_code = st.text_input("Country code *", value="CH", max_chars=2)
        retailer_name = st.text_input("Retailer", placeholder="Optional context")
    with second:
        ean = st.text_input("EAN / GTIN", placeholder="Optional identity evidence")
        language_code = st.text_input("Language", placeholder="Optional, e.g. de")
    with third:
        row_id = st.text_input("Run ID", value=st.session_state.run_row_id)
        feature_set = st.text_input("Feature set", value="toy_features")

    submitted = st.form_submit_button(
        "Identify product",
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
        st.session_state.run_row_id = row_id.strip()
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
            "runtime_options": controls,
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
            st.session_state.run_result = result
            st.session_state.run_elapsed_seconds = elapsed
            st.session_state.run_job_id = job_id
            progress_bar.progress(1.0, text="Product identification ready")
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
    st.caption(
        "Primary output: identified product, confidence, alternatives and unresolved distinctions. "
        "Supporting output: evidence sources and artifacts."
    )
