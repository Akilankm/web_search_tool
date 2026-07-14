from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse


def _classify_candidate_url(url: str) -> str:
    from src.product_evidence_harness import candidate_precision as precision

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = (parsed.path or "/").lower()
    suffix_match = re.search(r"(\.[a-z0-9]{2,5})$", path)
    suffix = suffix_match.group(1) if suffix_match else ""
    if suffix in precision.BLOCKED_EXTENSIONS:
        return "DOCUMENT_OR_MEDIA"
    if any(
        host == item or host.endswith("." + item)
        for item in precision.SOCIAL_DOMAINS
    ):
        return "SOCIAL_OR_COMMUNITY"
    if path in {"", "/"}:
        return "HOMEPAGE"

    segments = [segment for segment in path.split("/") if segment]
    query_names = {key.lower() for key, _ in parse_qsl(parsed.query)}
    if (
        any(segment in precision.SEARCH_SEGMENTS for segment in segments)
        or "q" in query_names
        or "query" in query_names
    ):
        return "SEARCH_RESULTS"

    final = segments[-1] if segments else ""
    product_identifier = bool(
        (len(final) >= 4 and any(char.isdigit() for char in final))
        or (len(final) >= 12 and ("-" in final or "_" in final))
    )
    if any(segment in precision.CATEGORY_SEGMENTS for segment in segments):
        if len(segments) >= 2 and product_identifier:
            return "PRODUCT_DETAIL_LIKELY"
        return "CATEGORY_OR_COLLECTION"
    if any(segment in precision.PRODUCT_SEGMENTS for segment in segments):
        return "PRODUCT_DETAIL_LIKELY"
    if any(name in query_names for name in precision.IDENTITY_QUERY_NAMES):
        return "PRODUCT_DETAIL_LIKELY"
    if len(segments) >= 2 and product_identifier:
        return "PRODUCT_DETAIL_LIKELY"
    return "UNKNOWN"


def _content_utility(scrape, verification, *, feature_evidence_count: int = 0):
    from src.product_evidence_harness.candidate_precision import ContentUtility

    if scrape is None:
        return ContentUtility(
            False, False, False, False, 0, 0.0, False, "NOT_SCRAPED"
        )
    fetch_success = bool(scrape.success and scrape.reachable)
    content_extracted = bool(
        scrape.word_count >= 20 or scrape.markdown_chars >= 400
    )
    page_type = str(getattr(verification, "page_type_check", "") or "")
    probable_product_page = bool(
        (scrape.looks_like_product_page or page_type == "PRODUCT_DETAIL")
        and not scrape.looks_like_homepage
        and not scrape.is_soft_404
    )
    identity_status = str(
        getattr(verification, "identity_status", "UNVERIFIED") or "UNVERIFIED"
    )
    identity_sufficient = identity_status in {"VERIFIED", "PROBABLE"}
    score = (
        0.15 * float(fetch_success)
        + 0.15 * float(content_extracted)
        + 0.25 * float(probable_product_page)
        + 0.30 * float(identity_sufficient)
        + 0.10 * min(1.0, max(0.0, scrape.richness_score))
        + 0.05 * min(1.0, max(0, feature_evidence_count) / 3)
    )
    accepted = bool(
        fetch_success
        and content_extracted
        and probable_product_page
        and identity_status != "MISMATCH"
        and score >= 0.48
    )
    if not fetch_success:
        reason = "SCRAPE_FAILED"
    elif not content_extracted:
        reason = "SCRAPE_LOW_CONTENT"
    elif not probable_product_page:
        reason = "PROBE_REJECTED_NON_PRODUCT"
    elif identity_status == "MISMATCH":
        reason = "IDENTITY_REJECTED"
    elif not accepted:
        reason = "SCRAPE_LOW_UTILITY"
    else:
        reason = "SCRAPE_ACCEPTED"
    return ContentUtility(
        fetch_success=fetch_success,
        content_extracted=content_extracted,
        probable_product_page=probable_product_page,
        identity_evidence_sufficient=identity_sufficient,
        feature_evidence_count=max(0, int(feature_evidence_count)),
        content_utility_score=round(score, 4),
        scrape_accepted=accepted,
        reason=reason,
    )


def _compact(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        return values
    if isinstance(values, dict):
        return json.dumps(values, ensure_ascii=False, sort_keys=True)
    if isinstance(values, Iterable):
        return "|".join(
            str(item) for item in values if str(item).strip()
        )
    return str(values)


def _reporting_utility(scrape: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    fetch_success = bool(scrape.get("success") and scrape.get("reachable"))
    content_extracted = bool(
        int(scrape.get("word_count") or 0) >= 20
        or int(scrape.get("markdown_chars") or 0) >= 400
    )
    page_type = str(verification.get("page_type_check") or "")
    probable_product = bool(
        (scrape.get("looks_like_product_page") or page_type == "PRODUCT_DETAIL")
        and not scrape.get("looks_like_homepage")
        and not scrape.get("is_soft_404")
    )
    identity_status = str(verification.get("identity_status") or "UNVERIFIED")
    identity_sufficient = identity_status in {"VERIFIED", "PROBABLE"}
    richness = min(1.0, max(0.0, float(scrape.get("richness_score") or 0.0)))
    score = (
        0.15 * float(fetch_success)
        + 0.15 * float(content_extracted)
        + 0.25 * float(probable_product)
        + 0.30 * float(identity_sufficient)
        + 0.15 * richness
    )
    accepted = bool(
        fetch_success
        and content_extracted
        and probable_product
        and identity_status != "MISMATCH"
        and score >= 0.48
    )
    return {
        "fetch_success": fetch_success,
        "content_extracted": content_extracted,
        "product_page_likelihood": round(
            0.45 * float(probable_product)
            + 0.25 * float(bool(scrape.get("page_product_name")))
            + 0.15 * float(bool(scrape.get("has_price")))
            + 0.15 * richness,
            4,
        ),
        "content_utility_score": round(score, 4),
        "scrape_accepted": accepted,
    }


def _segment_set(text: str) -> set[str]:
    return {
        re.sub(r"\s+", " ", item).strip()
        for item in re.split(r"[\n\r]+|(?<=[.!?])\s+", text or "")
        if len(re.sub(r"\s+", " ", item).strip()) >= 20
    }


def _delta_text(self, observation) -> str:
    previous_by_session = getattr(self, "_precision_previous_text", {})
    previous = previous_by_session.get(observation.session_id, "")
    current_segments = _segment_set(observation.visible_text)
    previous_segments = _segment_set(previous)
    delta_segments = current_segments - previous_segments
    previous_by_session[observation.session_id] = observation.visible_text
    self._precision_previous_text = previous_by_session
    source = "\n".join(sorted(delta_segments))
    return source or observation.visible_text


def _rank_elements(observation, terms: set[str], limit: int) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for position, item in enumerate(observation.interactive_elements):
        payload = item.to_dict()
        evidence = " ".join(
            str(payload.get(key) or "")
            for key in ("text", "role", "href", "tag")
        ).lower()
        relevance = sum(1 for term in terms if term in evidence)
        if any(term in evidence for term in (
            "specification", "details", "description", "manufacturer",
            "brand", "age", "warning", "dimensions", "show more", "gallery",
        )):
            relevance += 3
        if any(term in evidence for term in ("cart", "checkout", "login", "account")):
            relevance -= 5
        scored.append((relevance, -position, payload))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [payload for _, _, payload in scored[:limit]]


def _compact_prompt(self, request, schema, observation, history) -> str:
    from src.product_evidence_harness import precision_browser_runtime as runtime

    resolved = runtime._resolved_feature_ids(history)
    unresolved = [
        feature for feature in schema.features if feature.feature_id not in resolved
    ]
    relevant_terms = runtime._terms(request, unresolved or schema.features)
    delta = _delta_text(self, observation)
    recent_plans = [
        {
            "action": plan.get("action"),
            "reason": str(plan.get("reason") or "")[:180],
            "termination_reason": plan.get("termination_reason"),
            "candidate_assessment": plan.get("candidate_assessment") or {},
        }
        for plan in history[-2:]
    ]
    payload = {
        "objective": "Resolve only remaining identity or feature questions. Stop when wrong, blocked, complete, or no safe action can add evidence.",
        "context_policy": {
            "mode": "incremental_delta_relevance_filtered",
            "resolved_feature_ids": sorted(resolved),
            "unresolved_feature_ids": [feature.feature_id for feature in unresolved],
            "visible_text_limit": self.config.max_observation_chars,
            "element_limit": self.config.max_elements_in_prompt,
            "image_limit": self.config.max_images_in_prompt,
        },
        "product_identity": request.product_identity.to_dict(),
        "candidate": {
            "candidate_id": request.candidate_id,
            "requested_url": request.url,
            "current_url": observation.url,
            "title": observation.title,
            "visible_product_name": observation.visible_product_name,
        },
        "unresolved_features": [
            {
                "feature_id": feature.feature_id,
                "feature_name": feature.feature_name,
                "description": feature.description[:240],
                "allowed_values": list(feature.allowed_values)[:20],
                "criticality": feature.criticality.value,
            }
            for feature in unresolved
        ],
        "new_relevant_observation": {
            "visible_text": runtime._relevant_text(
                delta,
                relevant_terms,
                self.config.max_observation_chars,
            ),
            "interactive_elements": _rank_elements(
                observation,
                relevant_terms,
                self.config.max_elements_in_prompt,
            ),
            "images": runtime._rank_images(
                observation,
                relevant_terms,
                self.config.max_images_in_prompt,
            ),
            "blockers": list(observation.blockers),
            "warnings": list(observation.warnings),
            "action_count": observation.action_count,
            "maximum_actions": observation.maximum_actions,
        },
        "recent_action_summaries": recent_plans,
        "allowed_actions": {
            "click": "Click one observed relevant E### element.",
            "scroll": "Scroll up, down, top, or bottom.",
            "inspect_image": "Inspect one observed relevant I### image.",
            "capture_screenshot": "Preserve the current viewport.",
            "finish": "Stop when wrong, blocked, complete, or no action can improve evidence.",
        },
        "output_schema": {
            "action": "click|scroll|inspect_image|capture_screenshot|finish",
            "element_id": "observed E### or I### when required, otherwise null",
            "direction": "up|down|top|bottom when scrolling, otherwise null",
            "reason": "brief evidence-seeking rationale",
            "termination_reason": "required when action=finish",
            "candidate_assessment": {
                "same_product": "true|false|null",
                "same_variant": "true|false|null",
                "product_page": "true|false|null",
                "resolved_feature_ids": ["feature_id"],
                "missing_feature_ids": ["feature_id"],
                "conflicting_feature_ids": ["feature_id"],
                "evidence_summary": ["brief grounded observation"],
                "confidence": "0..1",
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _wrap_plan_with_precheck(original):
    def plan(self, request, schema, observation, history):
        from src.product_evidence_harness import precision_browser_runtime as runtime

        requested = {feature.feature_id for feature in schema.features}
        resolved = runtime._resolved_feature_ids(history)
        if requested and requested.issubset(resolved):
            return {
                "action": "finish",
                "element_id": None,
                "direction": None,
                "reason": "Every requested feature is already resolved.",
                "termination_reason": "ALL_REQUESTED_FEATURES_RESOLVED",
                "candidate_assessment": history[-1].get("candidate_assessment", {})
                if history else {},
            }
        return original(self, request, schema, observation, history)

    return plan


def _wrap_investigate_cleanup(original):
    def investigate(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        dossier = result[1] if isinstance(result, tuple) and len(result) > 1 else None
        session_id = getattr(dossier, "session_id", None)
        previous = getattr(self, "_precision_previous_text", {})
        if session_id:
            previous.pop(session_id, None)
        self._precision_previous_text = previous
        return result

    return investigate


def _wrap_result_limits(original):
    def run(self, payload, *, progress=None):
        result = original(self, payload, progress=progress)
        agentic = result.setdefault("agentic_browser", {})
        agentic["max_candidates"] = 3
        agentic["max_turns_per_candidate"] = min(
            4, int(agentic.get("max_turns_per_candidate") or 4)
        )
        agentic["max_actions_per_candidate"] = min(
            6, int(agentic.get("max_actions_per_candidate") or 6)
        )
        agentic.setdefault("context_policy", {})["mode"] = (
            "incremental_delta_relevance_filtered"
        )
        root = Path(str(result.get("artifact_dir") or ""))
        if root.is_dir():
            temp = root / "orchestrated_result.json.tmp"
            temp.write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
                encoding="utf-8",
            )
            temp.replace(root / "orchestrated_result.json")
        return result

    return run


def apply_precision_hardening() -> None:
    from src.product_evidence_harness import candidate_precision, candidate_reporting
    from src.product_evidence_harness import candidate_store
    from src.product_evidence_harness.agent_service.strict_orchestrator import (
        StrictProductEvidenceOrchestrator,
    )
    from src.product_evidence_harness.llm.agentic_browser import (
        AgenticBrowserInvestigator,
    )

    if getattr(AgenticBrowserInvestigator, "_precision_hardening_applied", False):
        return
    candidate_precision.classify_candidate_url = _classify_candidate_url
    candidate_store.classify_candidate_url = _classify_candidate_url
    candidate_precision.CandidatePrecisionGate.content_utility = staticmethod(
        _content_utility
    )
    candidate_reporting._compact = _compact
    candidate_reporting._utility = _reporting_utility
    AgenticBrowserInvestigator._prompt = _compact_prompt
    AgenticBrowserInvestigator._plan = _wrap_plan_with_precheck(
        AgenticBrowserInvestigator._plan
    )
    AgenticBrowserInvestigator.investigate = _wrap_investigate_cleanup(
        AgenticBrowserInvestigator.investigate
    )
    StrictProductEvidenceOrchestrator.run = _wrap_result_limits(
        StrictProductEvidenceOrchestrator.run
    )
    AgenticBrowserInvestigator._precision_hardening_applied = True
