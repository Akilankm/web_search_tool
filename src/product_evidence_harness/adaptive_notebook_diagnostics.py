from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from rich.console import Console
from rich.table import Table


@dataclass(slots=True)
class AdaptiveSearchDiagnostics:
    search_actions_df: pd.DataFrame
    search_engine_summary_df: pd.DataFrame
    search_handles_df: pd.DataFrame
    search_decision_rca_df: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "search_actions_df": self.search_actions_df,
            "search_engine_summary_df": self.search_engine_summary_df,
            "search_handles_df": self.search_handles_df,
            "search_decision_rca_df": self.search_decision_rca_df,
        }


def build_adaptive_search_diagnostics(
    result: dict[str, Any],
) -> AdaptiveSearchDiagnostics:
    search = dict(result.get("search") or {})
    stages = list(search.get("stages") or search.get("actions") or [])
    search_actions_df = pd.DataFrame(stages)
    expected_action_columns = [
        "serp_credit",
        "engine",
        "purpose",
        "planner_source",
        "scope",
        "query",
        "page_token_used",
        "image_used",
        "reason",
        "status",
        "raw_results_seen",
        "results_returned",
        "handles_discovered",
        "new_candidate_urls",
        "candidates_qualified",
        "candidates_scraped",
        "scrape_budget_remaining",
        "working_url_found",
        "current_best_url",
        "current_best_confidence",
        "early_stop",
        "error",
    ]
    for column in expected_action_columns:
        if column not in search_actions_df:
            search_actions_df[column] = None
    if not search_actions_df.empty:
        for column in (
            "serp_credit",
            "raw_results_seen",
            "results_returned",
            "handles_discovered",
            "new_candidate_urls",
            "candidates_qualified",
            "candidates_scraped",
            "scrape_budget_remaining",
        ):
            search_actions_df[column] = pd.to_numeric(
                search_actions_df[column], errors="coerce"
            ).fillna(0).astype(int)
        search_actions_df["current_best_confidence"] = pd.to_numeric(
            search_actions_df["current_best_confidence"], errors="coerce"
        ).fillna(0.0)
        for column in (
            "page_token_used",
            "image_used",
            "working_url_found",
            "early_stop",
        ):
            search_actions_df[column] = search_actions_df[column].map(_bool)
        search_actions_df = search_actions_df.sort_values("serp_credit").reset_index(
            drop=True
        )

    handles = list(search.get("handles") or [])
    search_handles_df = pd.DataFrame(handles)
    for column in ("kind", "value", "source_engine", "title", "metadata"):
        if column not in search_handles_df:
            search_handles_df[column] = None
    if not search_handles_df.empty:
        search_handles_df.insert(
            0, "handle_id", range(1, len(search_handles_df) + 1)
        )
        search_handles_df["usable_for_followup"] = search_handles_df["kind"].isin(
            {"immersive_product_page_token", "image_url", "asin", "product_id"}
        )
        search_handles_df["display_value"] = search_handles_df.apply(
            lambda row: _display_handle(row.get("kind"), row.get("value")), axis=1
        )

    if search_actions_df.empty:
        search_engine_summary_df = pd.DataFrame(
            columns=[
                "engine",
                "credits_used",
                "results_returned",
                "handles_discovered",
                "new_candidate_urls",
                "candidates_qualified",
                "candidates_scraped",
                "working_url_hits",
                "mean_best_confidence",
            ]
        )
    else:
        summary = (
            search_actions_df.groupby("engine", dropna=False)
            .agg(
                credits_used=("serp_credit", "count"),
                results_returned=("results_returned", "sum"),
                handles_discovered=("handles_discovered", "sum"),
                new_candidate_urls=("new_candidate_urls", "sum"),
                candidates_qualified=("candidates_qualified", "sum"),
                candidates_scraped=("candidates_scraped", "sum"),
                working_url_hits=("working_url_found", "sum"),
                mean_best_confidence=("current_best_confidence", "mean"),
            )
            .reset_index()
        )
        summary["candidate_yield_per_credit"] = summary["new_candidate_urls"] / summary[
            "credits_used"
        ].clip(lower=1)
        summary["qualified_rate"] = summary["candidates_qualified"] / summary[
            "new_candidate_urls"
        ].replace(0, pd.NA)
        summary["scrape_to_working_rate"] = summary["working_url_hits"] / summary[
            "candidates_scraped"
        ].replace(0, pd.NA)
        search_engine_summary_df = summary.sort_values(
            ["working_url_hits", "candidates_qualified", "new_candidate_urls"],
            ascending=False,
        ).reset_index(drop=True)

    search_decision_rca_df = pd.DataFrame(
        [
            {
                "metric": "Search policy",
                "value": search.get("policy") or "UNKNOWN",
            },
            {
                "metric": "Adaptive contract enforced",
                "value": bool(search.get("adaptive_search_contract_enforced")),
            },
            {
                "metric": "Credits used",
                "value": search.get("serpapi_requests_used", 0),
            },
            {
                "metric": "Credit limit",
                "value": search.get("serpapi_request_limit")
                or search.get("maximum_serpapi_credits")
                or 3,
            },
            {
                "metric": "Engine sequence",
                "value": " → ".join(search.get("engine_sequence") or []),
            },
            {
                "metric": "Planner calls",
                "value": search.get("planner_calls", 0),
            },
            {
                "metric": "Planner fallbacks",
                "value": search.get("planner_fallbacks", 0),
            },
            {
                "metric": "Working URL found during search",
                "value": bool(search.get("working_url_found_during_search")),
            },
            {
                "metric": "Search stop reason",
                "value": search.get("stop_reason") or "UNKNOWN",
            },
            {
                "metric": "Follow-up handles discovered",
                "value": len(handles),
            },
        ]
    )

    return AdaptiveSearchDiagnostics(
        search_actions_df=search_actions_df,
        search_engine_summary_df=search_engine_summary_df,
        search_handles_df=search_handles_df,
        search_decision_rca_df=search_decision_rca_df,
    )


def display_adaptive_search_summary(
    diagnostics: AdaptiveSearchDiagnostics,
    *,
    console: Console | None = None,
) -> None:
    console = console or Console()
    table = Table(title="Adaptive three-credit search RCA", show_lines=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    for row in diagnostics.search_decision_rca_df.to_dict("records"):
        table.add_row(str(row["metric"]), str(row["value"]))
    console.print(table)


def plot_engine_credit_allocation(
    diagnostics: AdaptiveSearchDiagnostics,
) -> None:
    frame = diagnostics.search_engine_summary_df
    if frame.empty:
        return
    figure, axis = plt.subplots(figsize=(9, 5))
    sns.barplot(data=frame, x="engine", y="credits_used", ax=axis)
    axis.set_title("SerpAPI credit allocation by engine")
    axis.set_xlabel("Engine")
    axis.set_ylabel("Credits used")
    axis.tick_params(axis="x", rotation=30)
    figure.tight_layout()
    plt.show()


def plot_engine_candidate_yield(
    diagnostics: AdaptiveSearchDiagnostics,
) -> None:
    frame = diagnostics.search_engine_summary_df
    if frame.empty:
        return
    melted = frame.melt(
        id_vars="engine",
        value_vars=[
            "results_returned",
            "new_candidate_urls",
            "candidates_qualified",
            "candidates_scraped",
        ],
        var_name="metric",
        value_name="count",
    )
    figure, axis = plt.subplots(figsize=(11, 6))
    sns.barplot(data=melted, x="engine", y="count", hue="metric", ax=axis)
    axis.set_title("Search-engine yield from response to scrape")
    axis.set_xlabel("Engine")
    axis.set_ylabel("Count")
    axis.tick_params(axis="x", rotation=30)
    figure.tight_layout()
    plt.show()


def plot_credit_progression(
    diagnostics: AdaptiveSearchDiagnostics,
) -> None:
    frame = diagnostics.search_actions_df
    if frame.empty:
        return
    figure, axis = plt.subplots(figsize=(9, 5))
    sns.lineplot(
        data=frame,
        x="serp_credit",
        y="current_best_confidence",
        marker="o",
        ax=axis,
    )
    axis.set_title("Best validated candidate confidence after each SerpAPI credit")
    axis.set_xlabel("Credit")
    axis.set_ylabel("Current best confidence")
    axis.set_ylim(0, 1.05)
    axis.set_xticks(frame["serp_credit"].tolist())
    figure.tight_layout()
    plt.show()


def export_adaptive_search_tables(
    diagnostics: AdaptiveSearchDiagnostics,
    workbook_path: str | Path,
) -> Path:
    path = Path(workbook_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if path.is_file() else "w"
    kwargs: dict[str, Any] = {"engine": "openpyxl", "mode": mode}
    if mode == "a":
        kwargs["if_sheet_exists"] = "replace"
    with pd.ExcelWriter(path, **kwargs) as writer:
        sheet_names = {
            "search_actions_df": "adaptive_actions",
            "search_engine_summary_df": "engine_summary",
            "search_handles_df": "search_handles",
            "search_decision_rca_df": "search_rca",
        }
        for name, frame in diagnostics.tables().items():
            frame.to_excel(writer, sheet_name=sheet_names[name], index=False)
    return path


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _display_handle(kind: Any, value: Any) -> str:
    text = str(value or "")
    if str(kind) == "immersive_product_page_token" and len(text) > 32:
        return text[:16] + "…" + text[-8:]
    if len(text) > 120:
        return text[:117] + "…"
    return text
