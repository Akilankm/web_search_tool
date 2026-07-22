from __future__ import annotations

import os
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st

API_URL = str(os.getenv("PRODUCT_URL_API_URL") or "http://127.0.0.1:8788").rstrip("/")
TERMINAL = {"COMPLETED", "REVIEW_REQUIRED", "FAILED", "TECHNICAL_FAILURE"}

st.set_page_config(page_title="Product URL Resolver", page_icon="◈", layout="wide")
st.title("Product URL Resolver")
st.caption("Auditable exact-product identification and direct product URL delivery")


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


try:
    runtime = health()
    st.sidebar.success("Runtime ready")
    st.sidebar.caption(f"Version {runtime.get('version')} · {runtime.get('runtime_contract')}")
    st.sidebar.caption(f"Browser: {(runtime.get('browser') or {}).get('status', 'unknown')}")
    profiles = runtime.get("profiles") or {}
except Exception as exc:
    st.sidebar.error("Runtime unavailable")
    st.sidebar.code("./scripts/start.sh --build")
    st.sidebar.exception(exc)
    profiles = {"Standard": {"search_credits": 3, "max_candidates": 12, "browser_candidates": 3}}

with st.form("resolve"):
    left, right = st.columns(2)
    with left:
        main_text = st.text_area("Main text", placeholder="PKM ME04 WACHSENDES CHAOS BOOSTER", height=100)
        country_code = st.text_input("Country code", value="CH", max_chars=2)
        retailer_name = st.text_input("Retailer name (optional)")
    with right:
        ean = st.text_input("EAN / GTIN (optional)")
        language_code = st.text_input("Language code (optional)")
        feature_set = st.text_input("Feature set", value="toy")
        profile_name = st.selectbox("Execution profile", list(profiles) or ["Standard"], index=min(1, max(0, len(profiles) - 1)))
    submitted = st.form_submit_button("Resolve product URL", type="primary", use_container_width=True)

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
            job = api("POST", "/v1/jobs", payload)
            progress = st.progress(0.05)
            status_box = st.empty()
            stage_fraction = {"INTERPRET": 0.15, "SEARCH": 0.35, "ACQUIRE": 0.58, "BROWSER": 0.75, "DELIVER": 0.90, "COMPLETE": 1.0, "FAILED": 1.0}
            deadline = time.time() + 1800
            while time.time() < deadline:
                job = api("GET", f"/v1/jobs/{job['job_id']}")
                progress.progress(stage_fraction.get(str(job.get("stage")), 0.08))
                status_box.info(f"{job.get('stage')} · {job.get('message')}")
                if job.get("status") in TERMINAL:
                    break
                time.sleep(2)
            result = api("GET", f"/v1/jobs/{job['job_id']}/result")
            progress.progress(1.0)
            decision = result.get("decision") or {}
            status = decision.get("status")
            selected_url = decision.get("selected_url")
            if status == "VERIFIED":
                st.success("Verified direct product URL")
            elif status == "REVIEW_REQUIRED":
                st.warning("Direct product URL delivered for review")
            else:
                st.error(str(status or "Resolution failed"))
            if selected_url:
                st.link_button("Open selected product", selected_url, use_container_width=True)
                st.code(selected_url)
            metrics = st.columns(4)
            metrics[0].metric("Status", str(status or "UNKNOWN").replace("_", " ").title())
            metrics[1].metric("Identity confidence", f"{float(decision.get('confidence') or 0):.1%}")
            metrics[2].metric("Candidates", len(result.get("candidates") or []))
            metrics[3].metric("Elapsed", f"{int(result.get('elapsed_ms') or 0) / 1000:.1f}s")
            st.markdown("### Decision")
            for reason in decision.get("reasons") or []:
                st.markdown(f"- {reason}")
            for warning in decision.get("warnings") or []:
                st.warning(warning)
            with st.expander("Review details", expanded=False):
                candidates = result.get("candidates") or []
                if candidates:
                    rows = [{
                        "Candidate": item.get("candidate_id"),
                        "Identity": item.get("identity_match"),
                        "Confidence": item.get("identity_confidence"),
                        "Direct page": item.get("direct_product_page"),
                        "Browser": item.get("browser_access"),
                        "Coding": item.get("coding_evidence_complete"),
                        "Source": item.get("source_role"),
                        "URL": item.get("url"),
                    } for item in candidates]
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                st.markdown("#### Interpretation")
                st.json(result.get("interpretation") or {}, expanded=False)
                st.markdown("#### Stage trace")
                st.json(result.get("events") or [], expanded=False)
                st.caption(f"Artifacts: {result.get('artifact_dir')}")
        except Exception as exc:
            st.exception(exc)
