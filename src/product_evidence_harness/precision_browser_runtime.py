from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.product_evidence_harness.candidate_precision import (
    browser_candidate_eligible,
    canonicalize_candidate_url,
    candidate_identity_tokens,
)
from src.product_evidence_harness.candidate_reporting import (
    build_candidate_records,
    write_candidate_records,
)


GENERIC_EVIDENCE_TERMS = {
    "specification",
    "specifications",
    "details",
    "description",
    "information",
    "manufacturer",
    "brand",
    "age",
    "warning",
    "dimensions",
    "technical",
    "show more",
    "gallery",
    "package",
}


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


def _config_from_env(cls):
    return cls(
        max_turns_per_candidate=_bounded_int(
            "PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE", 4, 1, 4
        ),
        max_actions_per_candidate=_bounded_int(
            "PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE", 6, 1, 6
        ),
        max_observation_chars=_bounded_int(
            "PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS", 4000, 1200, 5000
        ),
        max_elements_in_prompt=_bounded_int(
            "PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS", 15, 5, 18
        ),
        max_images_in_prompt=_bounded_int(
            "PRODUCT_HARNESS_AGENTIC_MAX_IMAGES", 8, 2, 10
        ),
        image_detail=os.getenv("PRODUCT_HARNESS_AGENTIC_IMAGE_DETAIL", "high").strip()
        or "high",
    )


def _resolved_feature_ids(history: list[dict[str, Any]]) -> set[str]:
    resolved: set[str] = set()
    for plan in history:
        assessment = plan.get("candidate_assessment") or {}
        resolved.update(str(item) for item in assessment.get("resolved_feature_ids") or [])
    return resolved


def _terms(request, features) -> set[str]:
    terms = set(candidate_identity_tokens(request.product_identity.main_text))
    terms.update(GENERIC_EVIDENCE_TERMS)
    for feature in features:
        terms.update(candidate_identity_tokens(feature.feature_name))
        terms.update(candidate_identity_tokens(feature.description))
    return {term.lower() for term in terms if term}


def _relevant_text(text: str, terms: set[str], limit: int) -> str:
    segments = [
        re.sub(r"\s+", " ", item).strip()
        for item in re.split(r"[\n\r]+|(?<=[.!?])\s+", text or "")
    ]
    segments = [item for item in segments if len(item) >= 20]
    ranked = sorted(
        enumerate(segments),
        key=lambda pair: (
            sum(1 for term in terms if term in pair[1].lower()),
            min(len(pair[1]), 400),
            -pair[0],
        ),
        reverse=True,
    )
    chosen: list[tuple[int, str]] = []
    used = 0
    for index, segment in ranked:
        score = sum(1 for term in terms if term in segment.lower())
        if score == 0 and chosen:
            continue
        segment = segment[:600]
        if used + len(segment) > limit:
            continue
        chosen.append((index, segment))
        used += len(segment)
        if used >= limit:
            break
    if not chosen:
        return re.sub(r"\s+", " ", text or "")[:limit]
    return "\n".join(value for _, value in sorted(chosen))


def _rank_elements(observation, terms: set[str], limit: int) -> list[dict[str, Any]]:
    scored = []
    for position, item in enumerate(observation.interactive_elements):
        payload = item.to_dict()
        evidence = " ".join(
            str(payload.get(key) or "") for key in ("text", "role", "href", "tag")
        ).lower()
        relevance = sum(1 for term in terms if term in evidence)
        if any(term in evidence for term in GENERIC_EVIDENCE_TERMS):
            relevance += 3
        if any(term in evidence for term in ("cart", "checkout", "login", "account")):
            relevance -= 5
        scored.append((relevance, -position, payload))
    return [payload for _, _, payload in sorted(scored, reverse=True)[:limit]]


def _rank_images(observation, terms: set[str], limit: int) -> list[dict[str, Any]]:
    scored = []
    for position, item in enumerate(observation.images):
        payload = item.to_dict()
        alt = str(payload.get("alt") or "").lower()
        relevance = sum(1 for term in terms if term in alt)
        area = int(payload.get("width") or 0) * int(payload.get("height") or 0)
        scored.append((relevance, area, -position, payload))
    return [payload for _, _, _, payload in sorted(scored, reverse=True)[:limit]]


def _compact_prompt(self, request, schema, observation, history) -> str:
    resolved = _resolved_feature_ids(history)
    unresolved = [
        feature for feature in schema.features if feature.feature_id not in resolved
    ]
    relevant_terms = _terms(request, unresolved or schema.features)
    feature_payload = [
        {
            "feature_id": feature.feature_id,
            "feature_name": feature.feature_name,
            "description": feature.description[:240],
            "allowed_values": list(feature.allowed_values)[:20],
            "criticality": feature.criticality.value,
        }
        for feature in unresolved
    ]
    recent_plans = []
    for plan in history[-2:]:
        recent_plans.append(
            {
                "action": plan.get("action"),
                "reason": str(plan.get("reason") or "")[:180],
                "termination_reason": plan.get("termination_reason"),
                "candidate_assessment": plan.get("candidate_assessment") or {},
            }
        )
    payload = {
        "objective": "Resolve only the remaining identity or feature questions. Stop as soon as the candidate is wrong, blocked, complete, or no safe action can add evidence.",
        "context_policy": {
            "mode": "incremental_relevance_filtered",
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
        "unresolved_features": feature_payload,
        "new_relevant_observation": {
            "visible_text": _relevant_text(
                observation.visible_text,
                relevant_terms,
                self.config.max_observation_chars,
            ),
            "interactive_elements": _rank_elements(
                observation,
                relevant_terms,
                self.config.max_elements_in_prompt,
            ),
            "images": _rank_images(
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


def _wrap_plan(original):
    def plan(self, request, schema, observation, history):
        value = original(self, request, schema, observation, history)
        assessment = value.get("candidate_assessment") or {}
        if assessment.get("same_product") is False or assessment.get("same_variant") is False:
            value.update(
                {
                    "action": "finish",
                    "termination_reason": "IDENTITY_OR_VARIANT_REJECTED",
                    "reason": "The observed page is not the requested product or variant.",
                }
            )
            return value
        if assessment.get("product_page") is False:
            value.update(
                {
                    "action": "finish",
                    "termination_reason": "NON_PRODUCT_PAGE",
                    "reason": "The observed page is not an individual product detail page.",
                }
            )
            return value
        resolved = _resolved_feature_ids([*history, value])
        requested = {feature.feature_id for feature in schema.features}
        if requested and requested.issubset(resolved):
            value.update(
                {
                    "action": "finish",
                    "termination_reason": "ALL_REQUESTED_FEATURES_RESOLVED",
                    "reason": "Every requested feature has grounded evidence.",
                }
            )
        return value

    return plan


def _precision_browser_urls(self, base):
    limit = min(
        3,
        max(1, _bounded_int("PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES", 3, 1, 90)),
    )
    assessments = {item.url: item for item in base.feature_assessments}
    cards_by_url = {card.candidate.url: card for card in base.state.scorecards}
    preferred = [
        base.product_match.product_url,
        base.product_match.best_available_url,
        *[card.candidate.url for card in base.state.scorecards],
    ]
    ordered = list(dict.fromkeys(url for url in preferred if url))
    decisions: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    for url in ordered:
        card = cards_by_url.get(url)
        if card is None:
            continue
        assessment = assessments.get(url)
        admitted, reason = browser_candidate_eligible(
            card,
            coverage=assessment.coverage if assessment else None,
            missing_features=assessment.missing_features if assessment else (),
        )
        canonical = canonicalize_candidate_url(url) or url
        decisions[canonical] = {"admitted": admitted, "reason": reason}
        if admitted:
            eligible.append(url)

    selected: list[str] = []
    seen_domains: set[str] = set()
    for url in eligible:
        domain = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if domain in seen_domains:
            continue
        selected.append(url)
        seen_domains.add(domain)
        if len(selected) >= limit:
            break
    for url in eligible:
        if len(selected) >= limit:
            break
        if url not in selected:
            selected.append(url)
    selected_set = {canonicalize_candidate_url(url) or url for url in selected}
    for canonical, decision in decisions.items():
        if decision["admitted"] and canonical not in selected_set:
            decision["admitted"] = False
            decision["reason"] = "BROWSER_QUALIFIED_NOT_SELECTED_BUDGET"
        elif canonical in selected_set:
            decision["reason"] = "BROWSER_ADMITTED_HIGH_POTENTIAL_UNRESOLVED"
    self._last_browser_admissions = decisions
    return tuple(selected)


def _wrap_orchestrator_run(original):
    def run(self, payload, *, progress=None):
        result = original(self, payload, progress=progress)
        root = Path(str(result.get("artifact_dir") or ""))
        state_path = root / "candidate_state.json"
        if not state_path.is_file():
            return result
        candidate_state = json.loads(state_path.read_text(encoding="utf-8"))
        result.setdefault("search", {})["serp_results"] = candidate_state.get(
            "serp_results", []
        )
        records = build_candidate_records(
            result,
            candidate_state,
            getattr(self, "_last_browser_admissions", {}),
        )
        result["candidate_records"] = records
        result.setdefault("search", {})["precision_policy"] = {
            "canonical_url_identity": True,
            "maximum_full_scrapes": _bounded_int(
                "PRODUCT_HARNESS_MAX_FULL_SCRAPES", 6, 1, 12
            ),
            "maximum_scrapes_per_domain": _bounded_int(
                "PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN", 2, 1, 4
            ),
            "minimum_preflight_score": os.getenv(
                "PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE", "0.28"
            ),
        }
        result.setdefault("agentic_browser", {})["admission_decisions"] = [
            {"canonical_url": url, **decision}
            for url, decision in getattr(self, "_last_browser_admissions", {}).items()
        ]
        result["agentic_browser"]["context_policy"] = {
            "mode": "incremental_relevance_filtered",
            "hard_max_candidates": 3,
            "hard_max_turns_per_candidate": 4,
            "hard_max_actions_per_candidate": 6,
            "maximum_observation_characters": 5000,
            "maximum_elements": 18,
            "maximum_images": 10,
        }
        write_candidate_records(root, records)
        temp = root / "orchestrated_result.json.tmp"
        temp.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        temp.replace(root / "orchestrated_result.json")
        return result

    return run


def apply_precision_browser_patches() -> None:
    from src.product_evidence_harness.agent_service.strict_orchestrator import (
        StrictProductEvidenceOrchestrator,
    )
    from src.product_evidence_harness.llm.agentic_browser import (
        AgenticBrowserConfig,
        AgenticBrowserInvestigator,
    )

    if getattr(AgenticBrowserInvestigator, "_precision_runtime_applied", False):
        return
    AgenticBrowserConfig.from_env = classmethod(_config_from_env)
    AgenticBrowserInvestigator._prompt = _compact_prompt
    AgenticBrowserInvestigator._plan = _wrap_plan(AgenticBrowserInvestigator._plan)
    StrictProductEvidenceOrchestrator._browser_urls = _precision_browser_urls
    StrictProductEvidenceOrchestrator.run = _wrap_orchestrator_run(
        StrictProductEvidenceOrchestrator.run
    )
    AgenticBrowserInvestigator._precision_runtime_applied = True
