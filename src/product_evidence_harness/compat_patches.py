from __future__ import annotations

import re
import sys
from dataclasses import replace
from html import escape

from src.product_evidence_harness.gtin import digits_only, normalize_gtin
from src.product_evidence_harness.offline_capture import LivePageOfflineArtifactBuilder
from src.product_evidence_harness.query_builder import QueryBuilder


def _searchable_ean(self: QueryBuilder, task) -> str | None:
    """Keep a supplied GTIN searchable without treating it as validated evidence."""
    normalized = normalize_gtin(task.ean)
    if normalized:
        return normalized
    raw = digits_only(task.ean)
    return raw if len(raw) in {8, 12, 13, 14} else None


def _strict_requested_retailer_search(self: QueryBuilder, task) -> str:
    """Suppress invalid GTINs for retailer-targeted strict retrieval."""
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
    QueryBuilder._valid_ean = _searchable_ean  # type: ignore[method-assign]
    QueryBuilder.requested_retailer_search = _strict_requested_retailer_search  # type: ignore[method-assign]
    LivePageOfflineArtifactBuilder._remove_network_primitives = _remove_network_primitives  # type: ignore[method-assign]
    LivePageOfflineArtifactBuilder._role_directory = _role_directory  # type: ignore[method-assign]

    from src.product_evidence_harness.precision_search_runtime import (
        apply_precision_search_patches,
    )
    from src.product_evidence_harness.precision_browser_runtime import (
        apply_precision_browser_patches,
    )
    from src.product_evidence_harness.precision_hardening import (
        apply_precision_hardening,
    )

    apply_precision_search_patches()
    apply_precision_browser_patches()
    apply_precision_hardening()

    # The historical package uses both ``product_evidence_harness`` and
    # ``src.product_evidence_harness`` imports. Alias the patched modules so both
    # names resolve to the same class objects instead of creating duplicate trees.
    query_module = sys.modules.get("src.product_evidence_harness.query_builder")
    offline_module = sys.modules.get("src.product_evidence_harness.offline_capture")
    if query_module is not None:
        sys.modules.setdefault("product_evidence_harness.query_builder", query_module)
    if offline_module is not None:
        sys.modules.setdefault("product_evidence_harness.offline_capture", offline_module)
