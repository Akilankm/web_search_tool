from __future__ import annotations

import re
import sys
from dataclasses import replace
from html import escape

from src.product_evidence_harness.gtin import digits_only, normalize_gtin
from src.product_evidence_harness.offline_capture import LivePageOfflineArtifactBuilder
from src.product_evidence_harness.query_builder import QueryBuilder


_PATCHED = False


def compatibility_patches_applied() -> bool:
    return _PATCHED


def _searchable_ean(self: QueryBuilder, task) -> str | None:
    normalized = normalize_gtin(task.ean)
    if normalized:
        return normalized
    raw = digits_only(task.ean)
    return raw if len(raw) in {8, 12, 13, 14} else None


def _strict_requested_retailer_search(self: QueryBuilder, task) -> str:
    if task.ean and normalize_gtin(task.ean) is None:
        task = replace(task, ean=None)
    return self.country_language_search(task, language_index=0, include_retailer=True)


def _remove_network_primitives(self: LivePageOfflineArtifactBuilder, html: str) -> str:
    output = html or ""
    output = re.sub(
        r"(<form\b[^>]*?)\saction=['\"][^'\"]+['\"]",
        lambda match: f'{match.group(1)} data-offline-action-disabled="true"',
        output,
        flags=re.I | re.S,
    )
    if self.config.disable_scripts:
        output = re.sub(
            r"<script\b([^>]*)\bsrc=['\"]([^'\"]+)['\"]([^>]*)>\s*</script>",
            lambda match: (
                '<script type="application/json" data-offline-disabled="external-script" '
                f'data-offline-src="{escape(match.group(2), quote=True)}"></script>'
            ),
            output,
            flags=re.I | re.S,
        )
        output = re.sub(
            r"<script\b(?![^>]*(?:application/ld\+json|data-offline-disabled=))([^>]*)>.*?</script>",
            '<script type="application/json" data-offline-disabled="inline-script"></script>',
            output,
            flags=re.I | re.S,
        )
    return output


def _role_directory(self: LivePageOfflineArtifactBuilder, role: str) -> str:
    role_l = (role or "").lower()
    if role_l in {"link.href", "link.stylesheet"} or "css" in role_l or "stylesheet" in role_l:
        return "css"
    if any(key in role_l for key in ["img", "image", "srcset", "poster", "source"]):
        return "images"
    if "icon" in role_l:
        return "images"
    if "font" in role_l:
        return "fonts"
    return "other"


def apply_compatibility_patches() -> None:
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    QueryBuilder._valid_ean = _searchable_ean  # type: ignore[method-assign]
    QueryBuilder.requested_retailer_search = _strict_requested_retailer_search  # type: ignore[method-assign]
    LivePageOfflineArtifactBuilder._remove_network_primitives = _remove_network_primitives  # type: ignore[method-assign]
    LivePageOfflineArtifactBuilder._role_directory = _role_directory  # type: ignore[method-assign]

    from src.product_evidence_harness.precision_search_runtime import apply_precision_search_patches
    from src.product_evidence_harness.precision_browser_runtime import apply_precision_browser_patches
    from src.product_evidence_harness.precision_hardening import apply_precision_hardening
    from src.product_evidence_harness.precision_selection_hardening import apply_precision_selection_hardening
    from src.product_evidence_harness.precision_terminal_hardening import apply_precision_terminal_hardening
    from src.product_evidence_harness.notebook_candidate_bridge import apply_notebook_candidate_bridge
    from src.product_evidence_harness.adaptive_search_runtime import apply_adaptive_search_runtime_patch
    from src.product_evidence_harness.adaptive_injected_client_compat import capture_pre_adaptive_run, install_injected_client_compatibility
    from src.product_evidence_harness.source_authority_runtime import apply_source_authority_patches
    from src.product_evidence_harness.source_authority_reporting import apply_source_authority_reporting_patch
    from src.product_evidence_harness.source_authority_compatibility import apply_source_authority_compatibility
    from src.product_evidence_harness.mandatory_url_policy import apply_mandatory_product_url_policy
    from src.product_evidence_harness.mandatory_url_identity_safety import apply_mandatory_url_identity_safety
    from src.product_evidence_harness.belief_runtime import apply_belief_driven_resolution_patch
    from src.product_evidence_harness.belief_compatibility import apply_belief_compatibility_patch
    from src.product_evidence_harness.agentic_fallback_runtime import apply_agentic_browser_fallback_patch
    from src.product_evidence_harness.manufacturer_primary_runtime import apply_manufacturer_primary_policy
    from src.product_evidence_harness.manufacturer_primary_hardening import apply_manufacturer_primary_hardening
    from src.product_evidence_harness.manufacturer_search_planner_hardening import apply_manufacturer_search_planner_hardening
    from src.product_evidence_harness.structured_no_url_outcome import apply_structured_no_url_outcome_patch
    from src.product_evidence_harness.runtime_contract_runtime import apply_runtime_contract_patch
    from src.product_evidence_harness.business_judgement_runtime import apply_business_judgement_review_patch
    from src.product_evidence_harness.artifact_diagnostics_runtime import apply_artifact_diagnostics_runtime_patch
    from src.product_evidence_harness.runtime_controls_runtime import apply_runtime_controls_patch
    from src.product_evidence_harness.null_numeric_runtime import apply_null_numeric_runtime_patch
    from src.product_evidence_harness.executive_summary_runtime import apply_executive_summary_patch
    from src.product_evidence_harness.url_delivery_recovery import apply_url_delivery_recovery_patch
    from src.product_evidence_harness.url_delivery_summary_runtime import apply_url_delivery_summary_patch

    apply_precision_search_patches()
    apply_precision_browser_patches()
    apply_precision_hardening()
    apply_precision_selection_hardening()
    apply_precision_terminal_hardening()
    apply_notebook_candidate_bridge()
    capture_pre_adaptive_run()
    apply_adaptive_search_runtime_patch()
    apply_null_numeric_runtime_patch()
    apply_source_authority_patches()
    apply_source_authority_reporting_patch()
    install_injected_client_compatibility()
    apply_mandatory_product_url_policy()
    apply_url_delivery_recovery_patch()
    apply_mandatory_url_identity_safety()
    apply_agentic_browser_fallback_patch()
    apply_artifact_diagnostics_runtime_patch()

    aliases = {
        "query_builder": "src.product_evidence_harness.query_builder",
        "offline_capture": "src.product_evidence_harness.offline_capture",
        "candidate_store": "src.product_evidence_harness.candidate_store",
        "candidate_precision": "src.product_evidence_harness.candidate_precision",
        "candidate_reporting": "src.product_evidence_harness.candidate_reporting",
        "ranker": "src.product_evidence_harness.ranker",
        "selector": "src.product_evidence_harness.selector",
        "three_stage_environment": "src.product_evidence_harness.three_stage_environment",
        "adaptive_search": "src.product_evidence_harness.adaptive_search",
        "adaptive_search_runtime": "src.product_evidence_harness.adaptive_search_runtime",
        "adaptive_injected_client_compat": "src.product_evidence_harness.adaptive_injected_client_compat",
        "source_authority": "src.product_evidence_harness.source_authority",
        "source_authority_runtime": "src.product_evidence_harness.source_authority_runtime",
        "source_authority_reporting": "src.product_evidence_harness.source_authority_reporting",
        "source_authority_compatibility": "src.product_evidence_harness.source_authority_compatibility",
        "mandatory_url_policy": "src.product_evidence_harness.mandatory_url_policy",
        "mandatory_url_identity_safety": "src.product_evidence_harness.mandatory_url_identity_safety",
        "belief": "src.product_evidence_harness.belief",
        "belief_runtime": "src.product_evidence_harness.belief_runtime",
        "belief_compatibility": "src.product_evidence_harness.belief_compatibility",
        "agentic_fallback_runtime": "src.product_evidence_harness.agentic_fallback_runtime",
        "manufacturer_primary_runtime": "src.product_evidence_harness.manufacturer_primary_runtime",
        "manufacturer_primary_hardening": "src.product_evidence_harness.manufacturer_primary_hardening",
        "manufacturer_search_planner_hardening": "src.product_evidence_harness.manufacturer_search_planner_hardening",
        "structured_no_url_outcome": "src.product_evidence_harness.structured_no_url_outcome",
        "runtime_contract": "src.product_evidence_harness.runtime_contract",
        "runtime_contract_runtime": "src.product_evidence_harness.runtime_contract_runtime",
        "business_judgement_artifact": "src.product_evidence_harness.business_judgement_artifact",
        "business_judgement_runtime": "src.product_evidence_harness.business_judgement_runtime",
        "artifact_diagnostics": "src.product_evidence_harness.artifact_diagnostics",
        "artifact_diagnostics_runtime": "src.product_evidence_harness.artifact_diagnostics_runtime",
        "runtime_controls": "src.product_evidence_harness.runtime_controls",
        "runtime_controls_runtime": "src.product_evidence_harness.runtime_controls_runtime",
        "null_numeric_runtime": "src.product_evidence_harness.null_numeric_runtime",
        "executive_summary": "src.product_evidence_harness.executive_summary",
        "executive_summary_runtime": "src.product_evidence_harness.executive_summary_runtime",
        "url_delivery_recovery": "src.product_evidence_harness.url_delivery_recovery",
        "url_delivery_summary_runtime": "src.product_evidence_harness.url_delivery_summary_runtime",
    }
    for short_name, source_name in aliases.items():
        module = sys.modules.get(source_name)
        if module is not None:
            sys.modules[f"product_evidence_harness.{short_name}"] = module

    apply_source_authority_compatibility()
    apply_belief_driven_resolution_patch()
    apply_belief_compatibility_patch()
    apply_manufacturer_search_planner_hardening()
    apply_manufacturer_primary_policy()
    apply_manufacturer_primary_hardening()
    apply_structured_no_url_outcome_patch()
    apply_runtime_contract_patch()
    apply_business_judgement_review_patch()
    apply_runtime_controls_patch()
    apply_executive_summary_patch()
    apply_url_delivery_summary_patch()
