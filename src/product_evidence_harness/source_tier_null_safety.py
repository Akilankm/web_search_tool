from __future__ import annotations

from typing import Any, Mapping

from src.product_evidence_harness.contracts import ProductQuery, URLCandidate
from src.product_evidence_harness.numeric_safety import safe_int
from src.product_evidence_harness.source_authority import SourceAuthorityPolicy, SourceTier


_PATCHED = False


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _tier_from_name(value: Any) -> int | None:
    name = str(value or "").strip().upper()
    member = SourceTier.__members__.get(name)
    return int(member) if member is not None else None


def _null_safe_primary_role(
    result: dict[str, Any],
    product: ProductQuery,
) -> tuple[str, int, str]:
    """Resolve source metadata without allowing an optional null tier to fail output writing."""

    acceptance = _mapping(result.get("primary_url_acceptance"))
    role = str(acceptance.get("source_role") or "UNKNOWN").strip().upper()
    tier_name = str(
        acceptance.get("source_tier_name") or SourceTier.UNKNOWN.name
    ).strip().upper()

    named_tier = _tier_from_name(tier_name)
    tier = safe_int(
        acceptance.get("source_tier"),
        named_tier if named_tier is not None else int(SourceTier.UNKNOWN),
        minimum=int(SourceTier.LOCAL_MANUFACTURER),
        maximum=int(SourceTier.UNKNOWN),
        field_name="primary_url_acceptance.source_tier",
    )

    primary_url = str(result.get("primary_url") or "").strip()
    metadata_incomplete = (
        role == "UNKNOWN"
        or tier == int(SourceTier.UNKNOWN)
        or tier_name not in SourceTier.__members__
    )
    if primary_url and metadata_incomplete:
        decision = SourceAuthorityPolicy().classify(
            product,
            URLCandidate(url=primary_url, title=product.main_text),
        )
        if role == "UNKNOWN":
            role = decision.source_role
        if tier == int(SourceTier.UNKNOWN):
            tier = safe_int(
                decision.source_tier,
                int(SourceTier.UNKNOWN),
                minimum=int(SourceTier.LOCAL_MANUFACTURER),
                maximum=int(SourceTier.UNKNOWN),
                field_name="classified_source_tier",
            )
        if tier_name not in SourceTier.__members__:
            tier_name = decision.source_tier_name

    if tier_name not in SourceTier.__members__:
        try:
            tier_name = SourceTier(tier).name
        except ValueError:
            tier = int(SourceTier.UNKNOWN)
            tier_name = SourceTier.UNKNOWN.name

    return role, tier, tier_name


def apply_source_tier_null_safety_patch() -> None:
    """Install the terminal source-tier normalization boundary."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness import manufacturer_primary_runtime

    manufacturer_primary_runtime._primary_role = _null_safe_primary_role
