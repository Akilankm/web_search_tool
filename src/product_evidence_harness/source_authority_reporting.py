from __future__ import annotations

import re
from collections import defaultdict


def _marker(source_types: str, prefix: str) -> str:
    for item in str(source_types or "").split("|"):
        if item.startswith(prefix):
            return item.removeprefix(prefix)
    return ""


def _tier(source_types: str) -> tuple[int, str]:
    value = _marker(source_types, "source_tier_")
    match = re.match(r"(\d{2})_(.+)", value)
    return (int(match.group(1)), match.group(2)) if match else (8, "UNKNOWN")


def apply_source_authority_reporting_patch() -> None:
    from src.product_evidence_harness import candidate_reporting
    from src.product_evidence_harness import precision_browser_runtime

    if getattr(candidate_reporting, "_source_authority_reporting_applied", False):
        return
    original = candidate_reporting.build_candidate_records

    def build(*args, **kwargs):
        records = original(*args, **kwargs)
        by_tier = defaultdict(list)
        for record in records:
            tier, tier_name = _tier(record.get("source_types") or "")
            role = _marker(record.get("source_types") or "", "source_role_") or "UNKNOWN"
            alignment = _marker(record.get("source_types") or "", "country_alignment_") or "UNKNOWN"
            market = _marker(record.get("source_types") or "", "marketplace_")
            record.update(
                {
                    "source_tier": tier,
                    "source_tier_name": tier_name,
                    "source_role": role,
                    "country_alignment": alignment,
                    "requested_retailer_match": role == "REQUESTED_RETAILER",
                    "manufacturer_match": role == "MANUFACTURER",
                    "major_country_retailer": role == "MAJOR_COUNTRY_RETAILER",
                    "marketplace": market,
                    "source_priority_reason": _reason(tier_name, market),
                }
            )
            by_tier[tier].append(record)

        viable_tiers = {
            int(record["source_tier"])
            for record in records
            if record.get("scrape_accepted")
            and str(record.get("identity_status")) in {"VERIFIED", "PROBABLE"}
        }
        for record in records:
            tier = int(record["source_tier"])
            record["higher_priority_tier_exhausted"] = not any(
                stronger < tier for stronger in viable_tiers
            )
            tier_records = by_tier[tier]
            best = max(
                tier_records,
                key=lambda item: (
                    bool(item.get("selected")),
                    bool(item.get("scrape_accepted")),
                    float(item.get("confidence") or 0.0),
                ),
            )
            record["selected_within_tier"] = record is best

        return sorted(
            records,
            key=lambda item: (
                bool(item.get("selected")),
                -int(item.get("source_tier", 8)),
                bool(item.get("scrape_accepted")),
                float(item.get("confidence") or 0.0),
            ),
            reverse=True,
        )

    candidate_reporting.build_candidate_records = build
    precision_browser_runtime.build_candidate_records = build
    candidate_reporting._source_authority_reporting_applied = True


def _reason(tier_name: str, marketplace: str) -> str:
    if tier_name.startswith("REQUESTED_RETAILER"):
        return "Explicit retailer input has first priority"
    if tier_name == "LOCAL_MANUFACTURER":
        return "Local/regional manufacturer website"
    if tier_name == "GLOBAL_MANUFACTURER":
        return "Global manufacturer website"
    if tier_name == "MAJOR_COUNTRY_RETAILER":
        return "Major retailer in requested country"
    if tier_name == "OTHER_LOCAL_WEBSITE":
        return "Other local product website"
    if tier_name == "OTHER_GLOBAL_WEBSITE":
        return "Other global exact-product website"
    if tier_name == "MARKETPLACE_LAST_RESORT":
        return f"{marketplace or 'Marketplace'} retained only as last resort"
    return "Source authority could not be classified"
