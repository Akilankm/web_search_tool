from __future__ import annotations

import re
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


def apply_compatibility_patches() -> None:
    QueryBuilder._valid_ean = _searchable_ean  # type: ignore[method-assign]
    LivePageOfflineArtifactBuilder._remove_network_primitives = _remove_network_primitives  # type: ignore[method-assign]
