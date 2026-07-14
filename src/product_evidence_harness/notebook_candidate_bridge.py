from __future__ import annotations


def _wrap_candidate_records(original):
    def build(*args, **kwargs):
        records = original(*args, **kwargs)
        for record in records:
            technical_scrapable = bool(record.get("scrapable"))
            quality_accepted = bool(record.get("scrape_accepted"))
            record["technical_scrapable"] = technical_scrapable
            # The existing notebook derives scrape_success from `scrapable`.
            # Preserve the stable UI while correcting its meaning to evidence
            # quality; raw technical acquisition remains independently visible.
            record["scrapable"] = quality_accepted
            record["scrape_success"] = quality_accepted
            record["scrape_attempted"] = bool(
                record.get("full_scrape_attempted")
            )
            record["agentic_investigated"] = bool(
                record.get("browser_admitted")
                and str(record.get("browser_outcome") or "NOT_RUN") != "NOT_RUN"
            )
            record["final_candidate_status"] = record.get("final_status")
            record["decision_reasons_compact"] = record.get("decision_reasons")
        return records

    return build


def apply_notebook_candidate_bridge() -> None:
    from src.product_evidence_harness import candidate_reporting
    from src.product_evidence_harness import precision_browser_runtime

    if getattr(candidate_reporting, "_notebook_candidate_bridge_applied", False):
        return
    wrapped = _wrap_candidate_records(candidate_reporting.build_candidate_records)
    candidate_reporting.build_candidate_records = wrapped
    # precision_browser_runtime imported the function directly before this bridge.
    precision_browser_runtime.build_candidate_records = wrapped
    candidate_reporting._notebook_candidate_bridge_applied = True
