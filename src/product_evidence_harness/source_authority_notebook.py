from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from rich.table import Table


def _tier(signals: Any) -> str:
    values = signals if isinstance(signals, (list, tuple)) else [signals]
    for value in values:
        if str(value).startswith("SOURCE_TIER:"):
            return str(value).split(":", 1)[1]
    return "UNKNOWN"


def apply_source_authority_notebook_patch() -> None:
    from src.product_evidence_harness import adaptive_notebook_diagnostics as module

    if getattr(module, "_source_authority_notebook_applied", False):
        return
    original_build = module.build_adaptive_search_diagnostics
    original_display = module.display_adaptive_search_summary
    original_export = module.export_adaptive_search_tables
    original_plot = module.plot_engine_credit_allocation

    def build(result):
        diagnostics = original_build(result)
        actions = diagnostics.search_actions_df
        if "target_source_tier" not in actions:
            actions["target_source_tier"] = actions.get(
                "expected_signals", pd.Series(dtype=object)
            ).map(_tier)
        search = dict(result.get("search") or {})
        hierarchy = list(
            search.get("source_authority_path")
            or (
                [
                    "LOCAL_MANUFACTURER",
                    "GLOBAL_MANUFACTURER",
                    "REQUESTED_RETAILER_LOCAL",
                    "REQUESTED_RETAILER_GLOBAL",
                    "MAJOR_COUNTRY_RETAILER",
                    "OTHER_LOCAL_WEBSITE",
                    "OTHER_GLOBAL_WEBSITE",
                    "MARKETPLACE_LAST_RESORT",
                ]
                if (result.get("product") or {}).get("retailer_name")
                else [
                    "LOCAL_MANUFACTURER",
                    "GLOBAL_MANUFACTURER",
                    "MAJOR_COUNTRY_RETAILER",
                    "OTHER_LOCAL_WEBSITE",
                    "OTHER_GLOBAL_WEBSITE",
                    "MARKETPLACE_LAST_RESORT",
                ]
            )
        )
        extra = pd.DataFrame(
            [
                {"metric": "Source hierarchy", "value": " → ".join(hierarchy)},
                {
                    "metric": "Primary URL role",
                    "value": result.get("primary_url_role") or "UNKNOWN",
                },
                {
                    "metric": "Manufacturer URL",
                    "value": result.get("manufacturer_url") or "NOT_AVAILABLE",
                },
                {
                    "metric": "Retailer URL",
                    "value": result.get("retailer_url") or "NOT_AVAILABLE",
                },
                {
                    "metric": "Manufacturer-first policy",
                    "value": bool(search.get("manufacturer_first_primary_url")),
                },
                {"metric": "Amazon/eBay last resort", "value": True},
                {
                    "metric": "Source-tier targets",
                    "value": " → ".join(
                        actions.get(
                            "target_source_tier", pd.Series(dtype=str)
                        ).astype(str)
                    ),
                },
                {
                    "metric": "Hierarchy selection enforced",
                    "value": bool(
                        search.get("source_authority_hierarchy_enforced", True)
                    ),
                },
            ]
        )
        diagnostics.search_decision_rca_df = pd.concat(
            [diagnostics.search_decision_rca_df, extra], ignore_index=True
        )
        return diagnostics

    def display(diagnostics, *, console=None):
        original_display(diagnostics, console=console)
        console = console or module.Console()
        frame = diagnostics.search_actions_df
        table = Table(title="Manufacturer-first source-authority route", show_lines=True)
        table.add_column("Credit")
        table.add_column("Target source tier")
        table.add_column("Engine")
        table.add_column("Outcome")
        for row in frame.to_dict("records"):
            table.add_row(
                str(row.get("serp_credit") or ""),
                str(row.get("target_source_tier") or "UNKNOWN"),
                str(row.get("engine") or ""),
                "working URL" if row.get("working_url_found") else "continue",
            )
        console.print(table)

    def export(diagnostics, workbook_path):
        path = original_export(diagnostics, workbook_path)
        actions = diagnostics.search_actions_df
        hierarchy = actions[
            [
                column
                for column in (
                    "serp_credit",
                    "target_source_tier",
                    "engine",
                    "purpose",
                    "results_returned",
                    "new_candidate_urls",
                    "candidates_qualified",
                    "candidates_scraped",
                    "working_url_found",
                    "reason",
                )
                if column in actions
            ]
        ]
        with pd.ExcelWriter(
            path, engine="openpyxl", mode="a", if_sheet_exists="replace"
        ) as writer:
            hierarchy.to_excel(writer, sheet_name="source_hierarchy", index=False)
        return path

    def plot(diagnostics):
        original_plot(diagnostics)
        frame = diagnostics.search_actions_df
        if frame.empty or "target_source_tier" not in frame:
            return
        figure, axis = plt.subplots(figsize=(11, 5))
        axis.bar(frame["serp_credit"].astype(str), [1] * len(frame))
        axis.set_title("Source-authority tier targeted by each SerpAPI credit")
        axis.set_xlabel("SerpAPI credit")
        axis.set_ylabel("Target")
        axis.set_yticks([])
        for index, row in frame.reset_index(drop=True).iterrows():
            axis.text(
                index,
                0.5,
                str(row["target_source_tier"]),
                ha="center",
                va="center",
                rotation=20,
            )
        figure.tight_layout()
        plt.show()

    module.build_adaptive_search_diagnostics = build
    module.display_adaptive_search_summary = display
    module.export_adaptive_search_tables = export
    module.plot_engine_credit_allocation = plot
    module._source_authority_notebook_applied = True
