from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "business-judgement-review-v1"
ARTIFACT_FILENAME = "business_judgement_review.md"


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "on"}


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _compact(value: Any, *, limit: int = 360) -> str:
    if isinstance(value, Mapping):
        parts = [f"{key}={_compact(item, limit=100)}" for key, item in value.items() if item not in (None, "", [], {})]
        text = "; ".join(parts)
    elif isinstance(value, (list, tuple, set)):
        text = "; ".join(_compact(item, limit=120) for item in value if item not in (None, "", [], {}))
    else:
        text = _text(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _markdown(value: Any) -> str:
    return _compact(value, limit=800).replace("|", "\\|").replace("\n", " ") or "—"


def _first(mapping: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = mapping
        found = True
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                found = False
                break
            current = current[part]
        if found and current not in (None, "", [], {}):
            return current
    return None


def _probability(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "not reported"
    if 0.0 <= number <= 1.0:
        return f"{number:.1%}"
    return f"{number:.3f}"


@dataclass(frozen=True, slots=True)
class BusinessJudgementStep:
    sequence_number: int
    decision_stage: str
    business_question: str
    evidence_considered: str
    evidence_sources: tuple[str, ...]
    visual_evidence_used: bool
    visual_evidence_details: str
    agent_judgement: str
    judgement_status: str
    alternatives_considered: str
    alternative_rejected: str
    rejection_reason: str
    business_rule_applied: str
    effect_on_next_action: str
    confidence: str
    final_outcome: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BusinessJudgementReview:
    schema_version: str
    artifact_filename: str
    human_review_status: str
    visual_evidence_summary: dict[str, Any]
    steps: tuple[BusinessJudgementStep, ...]
    markdown: str

    def result_payload(self, artifact_path: Path) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_filename": self.artifact_filename,
            "artifact_path": str(artifact_path),
            "human_review_status": self.human_review_status,
            "judgement_count": len(self.steps),
            "visual_evidence_summary": dict(self.visual_evidence_summary),
            "steps": [step.to_dict() for step in self.steps],
        }


def _visual_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    browser_records = [item for item in _items(result.get("browser_evidence")) if isinstance(item, Mapping)]
    investigations = [item for item in _items(result.get("candidate_investigations")) if isinstance(item, Mapping)]
    assessments = [item for item in _items(result.get("feature_assessments")) if isinstance(item, Mapping)]

    visual_assets = 0
    screenshots = 0
    gallery_pages = 0
    multimodal_candidates: set[str] = set()
    for record in browser_records:
        url = _text(record.get("final_url") or record.get("requested_url"))
        assets = _items(record.get("visual_assets"))
        visual_assets += len(assets)
        screenshots += int(record.get("screenshots_captured") or 0)
        gallery_pages += int(bool(record.get("gallery_discovered")))
        if _bool(record.get("multimodal_scrapable")) and url:
            multimodal_candidates.add(url)

    inspected_images = 0
    screenshot_planning_turns = 0
    for investigation in investigations:
        for plan in _items(investigation.get("plans")):
            if not isinstance(plan, Mapping):
                continue
            action = _text(plan.get("action")).lower()
            if action == "inspect_image":
                inspected_images += 1
            if action in {"inspect_image", "capture_screenshot", "click", "scroll", "finish"}:
                screenshot_planning_turns += 1

    visually_resolved_features: list[str] = []
    selected_url = _text(result.get("primary_url"))
    selected_visual_features: list[str] = []
    for assessment in assessments:
        assessment_url = _text(assessment.get("url"))
        for evidence in _items(assessment.get("evidence")):
            if not isinstance(evidence, Mapping):
                continue
            method = _text(evidence.get("extraction_method")).lower()
            location = _text(evidence.get("evidence_location")).lower()
            if method == "vision_llm" or location.startswith("visual_asset:"):
                feature = _text(evidence.get("feature_name") or evidence.get("feature_id"), "unnamed feature")
                if feature not in visually_resolved_features:
                    visually_resolved_features.append(feature)
                if assessment_url == selected_url and feature not in selected_visual_features:
                    selected_visual_features.append(feature)

    image_influence = "NO_VISUAL_EVIDENCE_RECORDED"
    if selected_visual_features:
        image_influence = "YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE"
    elif screenshot_planning_turns or visual_assets or screenshots:
        image_influence = "VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL"

    return {
        "browser_candidates_with_multimodal_evidence": len(multimodal_candidates),
        "visual_assets_collected": visual_assets,
        "screenshots_captured": screenshots,
        "gallery_pages_detected": gallery_pages,
        "agentic_image_inspection_actions": inspected_images,
        "screenshot_informed_planning_turns": screenshot_planning_turns,
        "features_resolved_visually": visually_resolved_features,
        "selected_url_features_resolved_visually": selected_visual_features,
        "image_influenced_final_decision": image_influence,
        "text_alone_would_have_passed": "UNKNOWN_NOT_COUNTERFACTUALLY_TESTED",
    }


def _identity_step(result: Mapping[str, Any], sequence: int) -> BusinessJudgementStep:
    product = dict(result.get("product") or {})
    identification = dict(result.get("product_identification") or {})
    leading = _first(
        identification,
        "leading_hypothesis",
        "winning_hypothesis",
        "identified_product",
    )
    if isinstance(leading, Mapping):
        identified = _text(
            leading.get("canonical_name")
            or leading.get("product_name")
            or leading.get("name")
            or leading.get("hypothesis_id"),
            "Product identity remains unresolved",
        )
        probability = _probability(
            leading.get("posterior_probability")
            or leading.get("probability")
            or leading.get("confidence")
        )
    else:
        identified = _text(leading, _text(product.get("main_text"), "Product identity remains unresolved"))
        probability = _probability(
            identification.get("leading_probability")
            or identification.get("confidence")
        )
    hypotheses = _items(identification.get("hypotheses"))
    alternatives = [
        _text(item.get("canonical_name") or item.get("name") or item.get("hypothesis_id"))
        for item in hypotheses
        if isinstance(item, Mapping)
    ]
    status = _text(
        identification.get("resolution_status")
        or identification.get("status"),
        "INTERPRETED",
    )
    return BusinessJudgementStep(
        sequence_number=sequence,
        decision_stage="INPUT_INTERPRETATION",
        business_question="What real-world product does the submitted input most likely represent?",
        evidence_considered=_compact(
            {
                "main_text": product.get("main_text"),
                "ean": product.get("ean"),
                "country_code": product.get("country_code"),
                "retailer_name": product.get("retailer_name"),
                "language_code": product.get("language_code"),
            }
        ),
        evidence_sources=("submitted product input", "offline product interpretation"),
        visual_evidence_used=False,
        visual_evidence_details="No web image is treated as evidence before the initial product interpretation.",
        agent_judgement=identified,
        judgement_status=status,
        alternatives_considered=_compact(alternatives) or "No alternative hypotheses were exposed in the result.",
        alternative_rejected="Lower-ranked product hypotheses",
        rejection_reason="The leading interpretation had the strongest support from the submitted identifiers and text.",
        business_rule_applied="Model knowledge is only a prior; the input is converted into explicit identity hypotheses before paid search.",
        effect_on_next_action="Use the leading identity and unresolved distinctions to plan authoritative product-page searches.",
        confidence=probability,
        final_outcome="SEARCH_IDENTITY_ESTABLISHED" if "UNRESOLVED" not in status.upper() else "IDENTITY_REVIEW_REQUIRED",
    )


def _uncertainty_step(result: Mapping[str, Any], sequence: int) -> BusinessJudgementStep:
    identification = dict(result.get("product_identification") or {})
    uncertainties = _first(identification, "uncertainties", "critical_unknowns", "unresolved_fields")
    metrics = identification.get("metrics") if isinstance(identification.get("metrics"), Mapping) else {}
    uncertainty_text = _compact(uncertainties) or "No decision-critical uncertainty was explicitly reported."
    return BusinessJudgementStep(
        sequence_number=sequence,
        decision_stage="UNCERTAINTY_ASSESSMENT",
        business_question="Which product distinctions still require web evidence before a URL can be accepted?",
        evidence_considered=_compact(
            {
                "uncertainties": uncertainties,
                "posterior_margin": metrics.get("posterior_margin"),
                "ambiguity_entropy": metrics.get("ambiguity_entropy"),
                "search_readiness": metrics.get("search_readiness"),
            }
        ),
        evidence_sources=("product identification state",),
        visual_evidence_used=False,
        visual_evidence_details="Images are not yet used; this step defines what later visual or textual evidence must resolve.",
        agent_judgement=uncertainty_text,
        judgement_status="RESOLVED" if not uncertainties else "EVIDENCE_REQUIRED",
        alternatives_considered="Possible sibling variants, product forms, pack configurations, editions, models, or market versions.",
        alternative_rejected="Prematurely treating an unresolved interpretation as an exact product.",
        rejection_reason="Exact URL selection requires the unresolved identity dimensions to be verified from direct-page evidence.",
        business_rule_applied="Do not promote a candidate while a decision-critical product distinction remains unresolved or conflicting.",
        effect_on_next_action="Search and browser investigation must target the highest-impact unresolved distinctions.",
        confidence=_probability(metrics.get("search_readiness")),
        final_outcome="SEARCH_EVIDENCE_REQUIREMENTS_DEFINED",
    )


def _search_steps(result: Mapping[str, Any], start: int) -> list[BusinessJudgementStep]:
    search = dict(result.get("search") or {})
    stages = [item for item in _items(search.get("stages")) if isinstance(item, Mapping)]
    if not stages:
        stages = [
            {"name": name, "serp_credit": index}
            for index, name in enumerate(_items(search.get("search_stage_order")), start=1)
        ]
    if not stages:
        stages = [
            {"name": "manufacturer_primary", "serp_credit": 1},
            {"name": "requested_retailer_country_or_country_alternative", "serp_credit": 2},
            {"name": "global_fallback", "serp_credit": 3},
        ]

    descriptions = {
        "manufacturer_primary": (
            "Does an exact official manufacturer or brand page exist?",
            "Search official manufacturer product truth before commercial sources.",
        ),
        "requested_retailer_country": (
            "Does the requested retailer provide an exact local product page?",
            "Retain requested-retailer market context after the manufacturer opportunity is evaluated.",
        ),
        "country_alternative": (
            "Does another retailer in the requested country provide an exact product page?",
            "Preserve local-market evidence when no retailer was supplied or the requested source is inadequate.",
        ),
        "global_fallback": (
            "Is a qualified exact product page available globally?",
            "Relax country scope without relaxing exact-product, feature, browser, or durability requirements.",
        ),
    }
    steps: list[BusinessJudgementStep] = []
    for offset, stage in enumerate(stages):
        name = _text(stage.get("name") or stage.get("market_stage") or stage.get("stage"), "unknown_stage")
        question, rule = descriptions.get(
            name,
            ("What source route should be searched next?", "Use the current bounded search stage without weakening exact-product requirements."),
        )
        results_count = stage.get("results_returned") or stage.get("result_count") or 0
        new_urls = stage.get("new_candidate_urls") or stage.get("candidate_count") or 0
        qualified = stage.get("candidates_qualified") or stage.get("qualified_candidates") or 0
        working = _bool(stage.get("working_url_found"))
        judgement = (
            f"Stage returned {results_count} result occurrences, {new_urls} new candidate URLs, "
            f"and {qualified} qualified candidates."
        )
        outcome = "WORKING_URL_FOUND" if working else "CONTINUE_OR_EVALUATE_CANDIDATES"
        steps.append(
            BusinessJudgementStep(
                sequence_number=start + offset,
                decision_stage=f"SEARCH_{name.upper()}",
                business_question=question,
                evidence_considered=_compact(
                    {
                        "query": stage.get("query"),
                        "engine": stage.get("engine"),
                        "scope": stage.get("scope"),
                        "results_returned": results_count,
                        "new_candidate_urls": new_urls,
                        "qualified_candidates": qualified,
                        "working_url_found": stage.get("working_url_found"),
                        "reason": stage.get("reason"),
                    }
                ),
                evidence_sources=(f"SerpAPI credit {stage.get('serp_credit') or offset + 1}", name),
                visual_evidence_used=False,
                visual_evidence_details="Search-result images or snippets are discovery signals only and are not sufficient for final acceptance.",
                agent_judgement=judgement,
                judgement_status=_text(stage.get("status"), "EXECUTED"),
                alternatives_considered="Other search engines, source tiers, and broader market scopes allowed by the bounded planner.",
                alternative_rejected="Repeating an already exhausted or lower-authority route without new discriminative evidence.",
                rejection_reason=_text(stage.get("reason"), "The next action is determined by candidate quality and unresolved evidence."),
                business_rule_applied=rule,
                effect_on_next_action=(
                    "Proceed to strict candidate validation."
                    if working
                    else "Evaluate returned candidates and use the next bounded credit if no candidate passes."
                ),
                confidence="not applicable",
                final_outcome=outcome,
            )
        )
    return steps


def _candidate_steps(result: Mapping[str, Any], start: int, visual: Mapping[str, Any]) -> list[BusinessJudgementStep]:
    investigations = [item for item in _items(result.get("candidate_investigations")) if isinstance(item, Mapping)]
    assessments = {
        _text(item.get("url")): item
        for item in _items(result.get("feature_assessments"))
        if isinstance(item, Mapping) and _text(item.get("url"))
    }
    primary_url = _text(result.get("primary_url"))
    manufacturer_url = _text(result.get("manufacturer_url"))
    retailer_url = _text(result.get("retailer_url"))
    important = {url for url in (primary_url, manufacturer_url, retailer_url) if url}

    ordered: list[Mapping[str, Any]] = []
    for item in investigations:
        url = _text(item.get("final_url") or item.get("requested_url"))
        if url in important:
            ordered.append(item)
    for item in investigations:
        if item not in ordered:
            ordered.append(item)
    ordered = ordered[:6]

    steps: list[BusinessJudgementStep] = []
    for offset, item in enumerate(ordered):
        url = _text(item.get("final_url") or item.get("requested_url"), "unknown candidate")
        assessment = assessments.get(url) or assessments.get(_text(item.get("requested_url"))) or {}
        llm_assessment = item.get("final_llm_assessment") if isinstance(item.get("final_llm_assessment"), Mapping) else {}
        evidence = [record for record in _items(assessment.get("evidence")) if isinstance(record, Mapping)]
        visual_features = [
            _text(record.get("feature_name") or record.get("feature_id"))
            for record in evidence
            if _text(record.get("extraction_method")).lower() == "vision_llm"
            or _text(record.get("evidence_location")).lower().startswith("visual_asset:")
        ]
        visual_used = bool(visual_features) or any(
            _text(plan.get("action")).lower() in {"inspect_image", "capture_screenshot"}
            for plan in _items(item.get("plans"))
            if isinstance(plan, Mapping)
        )
        same_product = llm_assessment.get("same_product")
        same_variant = llm_assessment.get("same_variant")
        product_page = llm_assessment.get("product_page")
        identity = _text(assessment.get("identity_status"), "not reported")
        coverage = assessment.get("coverage")
        missing = _items(assessment.get("missing_features"))
        conflicts = _items(assessment.get("conflicting_features"))
        accepted = bool(
            _bool(assessment.get("identity_accepted"))
            and not missing
            and not conflicts
            and same_product is not False
            and same_variant is not False
            and product_page is not False
        )
        judgement = (
            f"identity={identity}; same_product={same_product}; same_variant={same_variant}; "
            f"product_page={product_page}; coverage={coverage}; missing={_compact(missing) or 'none'}; "
            f"conflicts={_compact(conflicts) or 'none'}"
        )
        rejected_reason = ""
        if not accepted:
            rejected_reason = _compact(
                {
                    "termination_reason": item.get("termination_reason"),
                    "missing_features": missing,
                    "conflicting_features": conflicts,
                    "assessment_rejection_reasons": assessment.get("rejection_reasons"),
                    "error": item.get("error"),
                }
            )
        steps.append(
            BusinessJudgementStep(
                sequence_number=start + offset,
                decision_stage="CANDIDATE_BROWSER_AND_FEATURE_JUDGEMENT",
                business_question=f"Is this candidate the exact, usable and evidence-complete product page: {url}?",
                evidence_considered=_compact(
                    {
                        "browser_status": item.get("status"),
                        "turns_used": item.get("turns_used"),
                        "actions_executed": item.get("actions_executed"),
                        "candidate_assessment": llm_assessment,
                        "identity_status": identity,
                        "feature_coverage": coverage,
                        "missing_features": missing,
                        "conflicting_features": conflicts,
                    }
                ),
                evidence_sources=(url, f"candidate investigation {item.get('candidate_id') or offset + 1}"),
                visual_evidence_used=visual_used,
                visual_evidence_details=(
                    f"Visual features: {_compact(visual_features)}"
                    if visual_features
                    else "Rendered screenshots may have informed browser planning; no selected feature was explicitly attributed to vision for this candidate."
                ),
                agent_judgement=judgement,
                judgement_status="ELIGIBLE_FOR_FINAL_GATES" if accepted else "REJECTED_OR_INCOMPLETE",
                alternatives_considered="Other manufacturer, retailer, country and global candidate product pages.",
                alternative_rejected=url if not accepted else "None at this stage",
                rejection_reason=rejected_reason or "Candidate remained eligible for strict final gates.",
                business_rule_applied="A URL must be an individual rendered product page, match the exact product and variant, and contain all requested feature evidence.",
                effect_on_next_action=(
                    "Retain this candidate for strict acceptance and authority ranking."
                    if accepted
                    else "Do not promote this candidate; continue evaluating stronger alternatives."
                ),
                confidence=_probability(llm_assessment.get("confidence")),
                final_outcome="CANDIDATE_RETAINED" if accepted else "CANDIDATE_NOT_PRIMARY_ELIGIBLE",
            )
        )

    if not steps:
        steps.append(
            BusinessJudgementStep(
                sequence_number=start,
                decision_stage="CANDIDATE_VALIDATION_SUMMARY",
                business_question="Did any candidate receive rendered browser and feature validation?",
                evidence_considered=_compact(
                    {
                        "browser_evidence_records": len(_items(result.get("browser_evidence"))),
                        "feature_assessments": len(_items(result.get("feature_assessments"))),
                    }
                ),
                evidence_sources=("browser_evidence", "feature_assessments"),
                visual_evidence_used=bool(visual.get("visual_assets_collected") or visual.get("screenshots_captured")),
                visual_evidence_details=_compact(visual),
                agent_judgement="No candidate-level investigation record was exposed in the final result.",
                judgement_status="INSUFFICIENT_TRACE",
                alternatives_considered="Available direct product-page candidates.",
                alternative_rejected="No candidate-specific decision can be reconstructed from the exposed result.",
                rejection_reason="Candidate investigation records were absent.",
                business_rule_applied="Human comparison must be based only on observable recorded evidence.",
                effect_on_next_action="Treat the run as requiring trace review even if a URL was delivered.",
                confidence="not reported",
                final_outcome="TRACE_REVIEW_REQUIRED",
            )
        )
    return steps


def _strict_gate_step(result: Mapping[str, Any], sequence: int) -> BusinessJudgementStep:
    acceptance = dict(result.get("primary_url_acceptance") or {})
    gates = {
        "browser_openable": acceptance.get("browser_openable"),
        "text_scrapable": acceptance.get("text_scrapable"),
        "rendered_product_verified": acceptance.get("rendered_product_verified"),
        "exact_product_verified": acceptance.get("exact_product_verified"),
        "full_feature_coverage": acceptance.get("full_feature_coverage"),
        "durable_url": acceptance.get("durable_url"),
    }
    failed = [name for name, value in gates.items() if not _bool(value)]
    accepted = _bool(acceptance.get("accepted"))
    return BusinessJudgementStep(
        sequence_number=sequence,
        decision_stage="STRICT_PRIMARY_URL_GATES",
        business_question="Does the strongest candidate pass every non-negotiable production gate?",
        evidence_considered=_compact({**gates, "reasons": acceptance.get("reasons"), "scope": acceptance.get("scope")}),
        evidence_sources=("primary_url_acceptance.json", _text(acceptance.get("primary_url") or result.get("primary_url"), "selected candidate")),
        visual_evidence_used=_bool(acceptance.get("rendered_product_verified")),
        visual_evidence_details="Rendered browser verification is mandatory; feature evidence may include explicit vision-derived observations.",
        agent_judgement="All strict gates passed." if accepted else f"Strict acceptance failed: {_compact(failed or acceptance.get('reasons'))}",
        judgement_status="PASSED" if accepted else "FAILED_OR_REVIEW_REQUIRED",
        alternatives_considered="All candidates that survived identity, browser and feature validation.",
        alternative_rejected="Candidates failing any mandatory gate.",
        rejection_reason=_compact(acceptance.get("reasons")) or "No gate rejection was reported.",
        business_rule_applied="Authority never overrides identity, rendered-page, feature, scrapability, or URL-durability safety.",
        effect_on_next_action="Apply source authority ranking." if accepted else "Deliver the best real review URL or fail when no safe direct URL exists.",
        confidence="deterministic gate",
        final_outcome="STRICT_PRIMARY_ELIGIBLE" if accepted else "STRICT_PRIMARY_NOT_ELIGIBLE",
    )


def _authority_step(result: Mapping[str, Any], sequence: int) -> BusinessJudgementStep:
    selection = dict(result.get("source_selection") or {})
    primary_url = _text(result.get("primary_url"), "No primary URL")
    role = _text(result.get("primary_url_role") or selection.get("primary_url_role"), "UNKNOWN")
    manufacturer_url = _text(result.get("manufacturer_url"), "No qualified manufacturer URL")
    retailer_url = _text(result.get("retailer_url"), "No qualified retailer URL")
    return BusinessJudgementStep(
        sequence_number=sequence,
        decision_stage="SOURCE_AUTHORITY_SELECTION",
        business_question="Among candidates that passed the mandatory gates, which source should represent product truth?",
        evidence_considered=_compact(
            {
                "primary_url": primary_url,
                "primary_url_role": role,
                "manufacturer_url": manufacturer_url,
                "retailer_url": retailer_url,
                "source_tier_name": selection.get("source_tier_name") or selection.get("selected_source_tier_name"),
                "selection_reason": selection.get("selection_reason"),
            }
        ),
        evidence_sources=("source_selection.json", primary_url),
        visual_evidence_used=bool((result.get("business_judgement_review") or {}).get("visual_evidence_summary")),
        visual_evidence_details="Visual evidence affects eligibility before authority ranking; manufacturer authority is applied only after those gates pass.",
        agent_judgement=f"Selected {role}: {primary_url}",
        judgement_status="SELECTED" if result.get("primary_url") else "NO_PRIMARY_URL",
        alternatives_considered=f"Official manufacturer: {manufacturer_url}; retailer/commercial reference: {retailer_url}",
        alternative_rejected=(
            retailer_url if role == "OFFICIAL_MANUFACTURER" else manufacturer_url
        ),
        rejection_reason=_text(selection.get("selection_reason"), "Authority selection reason was not reported."),
        business_rule_applied="A qualified official manufacturer page outranks a qualified retailer page; retailer becomes primary when no manufacturer page passes every gate.",
        effect_on_next_action="Expose the primary URL and preserve qualified manufacturer and retailer references separately.",
        confidence="deterministic authority policy",
        final_outcome=_text(selection.get("selection_reason"), "SOURCE_SELECTED"),
    )


def _delivery_step(result: Mapping[str, Any], sequence: int) -> BusinessJudgementStep:
    delivery = dict(result.get("url_delivery") or {})
    status = _text(result.get("job_status"), "UNKNOWN")
    primary_url = _text(result.get("primary_url"), "No URL delivered")
    return BusinessJudgementStep(
        sequence_number=sequence,
        decision_stage="FINAL_DELIVERY",
        business_question="What URL and review status should be delivered to the human coder?",
        evidence_considered=_compact(
            {
                "job_status": status,
                "primary_url": primary_url,
                "primary_url_role": result.get("primary_url_role"),
                "delivered": delivery.get("delivered"),
                "strictly_verified": delivery.get("strictly_verified"),
                "delivery_status": delivery.get("status"),
            }
        ),
        evidence_sources=("mandatory_url_delivery.json", "orchestrated_result.json", primary_url),
        visual_evidence_used=bool(_items(result.get("browser_evidence"))),
        visual_evidence_details="See the visual evidence impact section for whether images merely supported investigation or materially completed the selected URL's feature gate.",
        agent_judgement=f"{status}: {primary_url}",
        judgement_status=status,
        alternatives_considered="Strictly verified primary URL, best available review URL, or explicit failure when no safe direct product URL exists.",
        alternative_rejected="Empty successful output and fabricated or indirect search-result URLs.",
        rejection_reason=_text((result.get("product_match") or {}).get("match_reason"), "No additional delivery rejection reason."),
        business_rule_applied="Every completed or review-required run must deliver a real direct product URL; no URL means explicit failure.",
        effect_on_next_action="Human coder compares this recorded judgment sequence with their own sequence and reports the first divergence.",
        confidence="strictly verified" if _bool(delivery.get("strictly_verified")) else "human review required",
        final_outcome=status,
    )


def build_business_judgement_review(result: Mapping[str, Any]) -> BusinessJudgementReview:
    visual = _visual_summary(result)
    steps: list[BusinessJudgementStep] = []
    steps.append(_identity_step(result, len(steps) + 1))
    steps.append(_uncertainty_step(result, len(steps) + 1))
    search_steps = _search_steps(result, len(steps) + 1)
    steps.extend(search_steps)
    candidate_steps = _candidate_steps(result, len(steps) + 1, visual)
    steps.extend(candidate_steps)
    steps.append(_strict_gate_step(result, len(steps) + 1))
    steps.append(_authority_step(result, len(steps) + 1))
    steps.append(_delivery_step(result, len(steps) + 1))

    markdown = _render_markdown(result, steps, visual)
    return BusinessJudgementReview(
        schema_version=SCHEMA_VERSION,
        artifact_filename=ARTIFACT_FILENAME,
        human_review_status="PENDING_HUMAN_COMPARISON",
        visual_evidence_summary=visual,
        steps=tuple(steps),
        markdown=markdown,
    )


def write_business_judgement_review(result: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    review = build_business_judgement_review(result)
    artifact_root.mkdir(parents=True, exist_ok=True)
    path = artifact_root / ARTIFACT_FILENAME
    path.write_text(review.markdown, encoding="utf-8")
    payload = review.result_payload(path)
    result["business_judgement_review"] = payload
    return payload


def _render_markdown(
    result: Mapping[str, Any],
    steps: Iterable[BusinessJudgementStep],
    visual: Mapping[str, Any],
) -> str:
    product = dict(result.get("product") or {})
    selection = dict(result.get("source_selection") or {})
    delivery = dict(result.get("url_delivery") or {})
    lines = [
        "# Business Judgment Review — Product URL Identification",
        "",
        "> Purpose: compare the agent's observable sequence of business judgments with the sequence a human coder would make from the same input and evidence.",
        "> This artifact records evidence, rules, judgments and actions. It does not expose hidden chain-of-thought.",
        "",
        "## Review metadata",
        "",
        f"- **Schema:** `{SCHEMA_VERSION}`",
        f"- **Row ID:** `{_markdown(product.get('row_id'))}`",
        f"- **Job status:** `{_markdown(result.get('job_status'))}`",
        f"- **Human review status:** `PENDING_HUMAN_COMPARISON`",
        f"- **Primary URL:** {_markdown(result.get('primary_url'))}",
        f"- **Primary role:** `{_markdown(result.get('primary_url_role'))}`",
        f"- **Manufacturer URL:** {_markdown(result.get('manufacturer_url'))}",
        f"- **Retailer URL:** {_markdown(result.get('retailer_url'))}",
        f"- **Selection reason:** `{_markdown(selection.get('selection_reason'))}`",
        f"- **Strictly verified:** `{_markdown(delivery.get('strictly_verified'))}`",
        "",
        "## Submitted input",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    for field in ("row_id", "main_text", "country_code", "retailer_name", "ean", "language_code"):
        lines.append(f"| `{field}` | {_markdown(product.get(field))} |")

    lines.extend(
        [
            "",
            "## Executive decision",
            "",
            f"The agent selected **{_markdown(result.get('primary_url_role'))}** as the primary product-truth source: {_markdown(result.get('primary_url'))}.",
            "",
            "The manufacturer is preferred only after exact identity, rendered browser verification, text scrapability, requested-feature completeness and URL durability pass. A retailer is a controlled fallback when the manufacturer page fails any mandatory gate.",
            "",
            "## Sequence of business judgments",
            "",
            "| Step | Business question | Evidence considered | Agent judgment | Rule applied | Effect on next action | Visual evidence | Outcome |",
            "|---:|---|---|---|---|---|---|---|",
        ]
    )
    step_list = list(steps)
    for step in step_list:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(step.sequence_number),
                    _markdown(step.business_question),
                    _markdown(step.evidence_considered),
                    _markdown(step.agent_judgement),
                    _markdown(step.business_rule_applied),
                    _markdown(step.effect_on_next_action),
                    "Yes" if step.visual_evidence_used else "No",
                    _markdown(step.final_outcome),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Detailed judgment records", ""])
    for step in step_list:
        lines.extend(
            [
                f"### {step.sequence_number}. {step.decision_stage}",
                "",
                f"- **Business question:** {step.business_question}",
                f"- **Evidence considered:** {step.evidence_considered or 'Not reported'}",
                f"- **Evidence sources:** {_compact(step.evidence_sources) or 'Not reported'}",
                f"- **Visual evidence used:** {'Yes' if step.visual_evidence_used else 'No'}",
                f"- **Visual evidence details:** {step.visual_evidence_details}",
                f"- **Agent judgment:** {step.agent_judgement}",
                f"- **Judgment status:** `{step.judgement_status}`",
                f"- **Alternatives considered:** {step.alternatives_considered}",
                f"- **Alternative rejected:** {step.alternative_rejected}",
                f"- **Rejection reason:** {step.rejection_reason}",
                f"- **Business rule applied:** {step.business_rule_applied}",
                f"- **Effect on next action:** {step.effect_on_next_action}",
                f"- **Confidence:** {step.confidence}",
                f"- **Outcome:** `{step.final_outcome}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Visual evidence impact",
            "",
            "| Measure | Recorded value |",
            "|---|---|",
        ]
    )
    for key, value in visual.items():
        lines.append(f"| `{key}` | {_markdown(value)} |")
    lines.extend(
        [
            "",
            "### Interpretation",
            "",
            "- `YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE` means vision-derived evidence was recorded for the selected URL and contributed to the evidence used by the strict feature gate.",
            "- `VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL` means screenshots or images informed investigation, but the final record does not prove that images changed the selected URL.",
            "- `text_alone_would_have_passed` is intentionally reported as `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` unless the system runs an explicit text-only counterfactual.",
            "",
            "## Human coder comparison form",
            "",
            "The human coder should review the input and evidence independently, then compare their judgment sequence with the numbered sequence above.",
            "",
            "### Overall comparison",
            "",
            "- [ ] **IDENTICAL** — same business judgments, same order, and same final URL role/outcome",
            "- [ ] **PARTIALLY IDENTICAL** — same final URL, but one or more judgments or ordering differ",
            "- [ ] **NOT IDENTICAL** — materially different judgment sequence or final URL",
            "",
            "### Reviewer response",
            "",
            "- **Reviewer name:**",
            "- **Review date:**",
            "- **Human-selected primary URL:**",
            "- **Human-selected primary role:**",
            "- **Is the final URL identical?** `YES / NO`",
            "- **Is the business judgment sequence identical?** `YES / PARTIAL / NO`",
            "- **First divergent step number:**",
            "- **Agent judgment at divergence:**",
            "- **Human judgment at divergence:**",
            "- **Evidence the agent missed or overweighted:**",
            "- **Was image evidence interpreted correctly?** `YES / PARTIAL / NO / NOT USED`",
            "- **Recommended business-rule or system change:**",
            "- **Additional comments:**",
            "",
            "## Supporting artifacts",
            "",
            "- `product_belief.json` — product hypotheses, uncertainties and belief updates",
            "- `adaptive_search_trace.json` — bounded search decisions",
            "- `candidates.csv` — canonical candidate ledger",
            "- `primary_url_acceptance.json` — strict gate decision",
            "- `source_selection.json` — manufacturer-versus-retailer authority decision",
            "- `mandatory_url_delivery.json` — final delivery decision",
            "- `single_product_diagnostics.xlsx` — complete engineering diagnostics",
            "",
        ]
    )
    return "\n".join(lines)
