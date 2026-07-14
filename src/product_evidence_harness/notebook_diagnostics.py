from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


SUPPORTED_FEATURE_STATUSES = {
    "STRUCTURED_FOUND",
    "EXPLICITLY_FOUND",
    "LLM_FOUND",
}


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith(("[", "(", "{")):
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                parsed = None
            if isinstance(parsed, (list, tuple, set)):
                return list(parsed)
        return [item for item in text.split("|") if item]
    return [value]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {"1", "true", "yes", "y", "on"}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(converted) else converted


def _domain(url: str) -> str:
    return urlparse(_text(url)).netloc.lower().removeprefix("www.")


def _scope_from_source_types(value: Any) -> str:
    source_types = _listify(value)
    for item in source_types:
        text = _text(item)
        if text.startswith("scope_"):
            return text.removeprefix("scope_")
    return "unknown"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _short_reason(value: Any, limit: int = 180) -> str:
    text = " | ".join(_text(item) for item in _listify(value) if _text(item))
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _reason_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    for item in _listify(value):
        for part in _text(item).split("|"):
            normalized = part.strip()
            if normalized:
                tokens.append(normalized)
    return tokens


def _status_label(row: pd.Series) -> str:
    if _bool(row.get("strict_selected")):
        return "STRICT_SELECTED"
    if _bool(row.get("review_selected")):
        return "REVIEW_SELECTED"
    if not _bool(row.get("scrape_attempted")):
        return "NOT_SCRAPED"
    if not _bool(row.get("scrape_success")):
        return "SCRAPE_FAILED"
    if not _bool(row.get("browser_openable")) and _bool(row.get("agentic_investigated")):
        return "BROWSER_BLOCKED"
    if not _bool(row.get("identity_accepted")):
        return "IDENTITY_REJECTED"
    if _float(row.get("coverage")) < 1.0:
        return "FEATURE_INCOMPLETE"
    return "ELIGIBLE_NOT_SELECTED"


@dataclass(slots=True)
class SingleProductDiagnostics:
    overview_df: pd.DataFrame
    search_stages_df: pd.DataFrame
    serp_results_df: pd.DataFrame
    results_df: pd.DataFrame
    agentic_df: pd.DataFrame
    feature_evidence_df: pd.DataFrame
    feature_matrix_df: pd.DataFrame
    funnel_df: pd.DataFrame
    domain_summary_df: pd.DataFrame
    stage_quality_df: pd.DataFrame
    rejection_reasons_df: pd.DataFrame
    selection_rca_df: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "overview_df": self.overview_df,
            "search_stages_df": self.search_stages_df,
            "serp_results_df": self.serp_results_df,
            "results_df": self.results_df,
            "agentic_df": self.agentic_df,
            "feature_evidence_df": self.feature_evidence_df,
            "feature_matrix_df": self.feature_matrix_df,
            "funnel_df": self.funnel_df,
            "domain_summary_df": self.domain_summary_df,
            "stage_quality_df": self.stage_quality_df,
            "rejection_reasons_df": self.rejection_reasons_df,
            "selection_rca_df": self.selection_rca_df,
        }


def build_single_product_diagnostics(
    result: dict[str, Any],
    *,
    artifact_dir: str | Path | None = None,
) -> SingleProductDiagnostics:
    artifact_root = Path(artifact_dir) if artifact_dir else None
    candidates_path = artifact_root / "candidates.csv" if artifact_root else Path("__missing__")
    feature_path = artifact_root / "feature_evidence.csv" if artifact_root else Path("__missing__")

    search = dict(result.get("search") or {})
    stages = list(search.get("stages") or [])
    search_stages_df = pd.DataFrame(stages)
    if search_stages_df.empty:
        search_stages_df = pd.DataFrame(
            columns=[
                "serp_credit",
                "name",
                "scope",
                "query",
                "language_code",
                "results_returned",
                "new_candidate_urls",
                "candidates_scraped",
            ]
        )

    serp_results_df = pd.DataFrame(search.get("serp_results") or [])
    if not serp_results_df.empty:
        serp_results_df["domain"] = serp_results_df["url"].map(_domain)
        serp_results_df["stage"] = serp_results_df.get("stage", "")
        serp_results_df["position"] = pd.to_numeric(
            serp_results_df.get("position"), errors="coerce"
        )
        serp_results_df["duplicate_url"] = serp_results_df.duplicated("url", keep=False)
    else:
        serp_results_df = pd.DataFrame(
            columns=[
                "serp_credit",
                "stage",
                "scope",
                "query",
                "position",
                "url",
                "domain",
                "title",
                "snippet",
                "search_status",
                "duplicate_url",
            ]
        )

    candidates_df = _read_csv(candidates_path)
    if candidates_df.empty:
        candidate_urls = list(
            dict.fromkeys(
                [
                    *[
                        _text(item.get("url"))
                        for item in result.get("feature_assessments") or []
                    ],
                    *[
                        _text(item.get("requested_url"))
                        for item in result.get("candidate_investigations") or []
                    ],
                    *[
                        _text(item.get("requested_url"))
                        for item in result.get("browser_evidence") or []
                    ],
                ]
            )
        )
        candidates_df = pd.DataFrame({"url": [url for url in candidate_urls if url]})

    for column in (
        "source_types",
        "best_position",
        "confidence",
        "validation_status",
        "identity_status",
        "ean_check",
        "title_check",
        "page_type",
        "scrapable",
        "richness",
        "decision_reasons",
    ):
        if column not in candidates_df:
            candidates_df[column] = ""

    candidates_df["url"] = candidates_df["url"].map(_text)
    candidates_df = candidates_df[candidates_df["url"] != ""].drop_duplicates("url").copy()
    candidates_df["domain"] = candidates_df["url"].map(_domain)
    candidates_df["stage"] = candidates_df["source_types"].map(_scope_from_source_types)
    candidates_df["serp_position"] = pd.to_numeric(
        candidates_df["best_position"], errors="coerce"
    )
    candidates_df["confidence"] = pd.to_numeric(
        candidates_df["confidence"], errors="coerce"
    ).fillna(0.0)
    candidates_df["richness"] = pd.to_numeric(
        candidates_df["richness"], errors="coerce"
    ).fillna(0.0)
    candidates_df["scrape_attempted"] = (
        candidates_df["identity_status"].map(_text).str.upper() != "NOT_SCRAPED"
    )
    candidates_df["scrape_success"] = candidates_df["scrapable"].map(_bool)
    candidates_df["quality_verified"] = (
        candidates_df["validation_status"].map(_text).str.upper() == "VERIFIED"
    )
    candidates_df["decision_reasons_compact"] = candidates_df["decision_reasons"].map(
        _short_reason
    )

    if serp_results_df.empty and not candidates_df.empty:
        serp_results_df = candidates_df[
            ["url", "domain", "stage", "serp_position"]
        ].rename(columns={"serp_position": "position"}).copy()
        serp_results_df.insert(0, "serp_credit", pd.NA)
        serp_results_df["scope"] = serp_results_df["stage"].map(
            lambda value: "global" if value == "global_fallback" else "country"
        )
        serp_results_df["query"] = ""
        serp_results_df["title"] = ""
        serp_results_df["snippet"] = ""
        serp_results_df["search_status"] = "DEDUPLICATED_CANDIDATE"
        serp_results_df["duplicate_url"] = False
        serp_results_df["record_type"] = "deduplicated_candidate"

    investigations = list(result.get("candidate_investigations") or [])
    agentic_df = pd.DataFrame(
        [
            {
                "candidate_id": item.get("candidate_id"),
                "requested_url": item.get("requested_url"),
                "final_url": item.get("final_url"),
                "domain": _domain(item.get("requested_url")),
                "status": item.get("status"),
                "turns_used": item.get("turns_used", 0),
                "actions_executed": item.get("actions_executed", 0),
                "termination_reason": item.get("termination_reason"),
                "llm_assessment": item.get("final_llm_assessment") or {},
                "error": item.get("error"),
            }
            for item in investigations
        ]
    )
    if agentic_df.empty:
        agentic_df = pd.DataFrame(
            columns=[
                "candidate_id",
                "requested_url",
                "final_url",
                "domain",
                "status",
                "turns_used",
                "actions_executed",
                "termination_reason",
                "llm_assessment",
                "error",
            ]
        )

    browser_df = pd.DataFrame(result.get("browser_evidence") or [])
    if browser_df.empty:
        browser_df = pd.DataFrame(
            columns=[
                "requested_url",
                "browser_openable",
                "rendered_product_verified",
                "text_scrapable",
                "multimodal_scrapable",
                "gallery_discovered",
                "direct_images_downloaded",
                "screenshots_captured",
                "blockers",
                "warnings",
                "error",
            ]
        )

    assessments = list(result.get("feature_assessments") or [])
    assessment_df = pd.DataFrame(
        [
            {
                "url": item.get("url"),
                "identity_accepted": item.get("identity_accepted", False),
                "identity_status_assessment": item.get("identity_status"),
                "source_role": item.get("source_role"),
                "coverage": item.get("coverage", 0.0),
                "required_coverage": item.get("required_coverage", 0.0),
                "critical_coverage": item.get("critical_coverage", 0.0),
                "missing_features": item.get("missing_features") or [],
                "conflicting_features": item.get("conflicting_features") or [],
                "assessment_rejection_reasons": item.get("rejection_reasons") or [],
            }
            for item in assessments
        ]
    )
    if assessment_df.empty:
        assessment_df = pd.DataFrame(
            columns=[
                "url",
                "identity_accepted",
                "identity_status_assessment",
                "source_role",
                "coverage",
                "required_coverage",
                "critical_coverage",
                "missing_features",
                "conflicting_features",
                "assessment_rejection_reasons",
            ]
        )

    feature_records: list[dict[str, Any]] = []
    for assessment in assessments:
        for evidence in assessment.get("evidence") or []:
            feature_records.append(
                {
                    "url": assessment.get("url"),
                    "domain": _domain(assessment.get("url")),
                    "identity_accepted": assessment.get("identity_accepted", False),
                    "identity_status": assessment.get("identity_status"),
                    "source_role": assessment.get("source_role"),
                    "feature_id": evidence.get("feature_id"),
                    "feature_name": evidence.get("feature_name"),
                    "value": evidence.get("value"),
                    "status": evidence.get("status"),
                    "supported": evidence.get("status") in SUPPORTED_FEATURE_STATUSES,
                    "confidence": evidence.get("confidence", 0.0),
                    "evidence_location": evidence.get("evidence_location"),
                    "extraction_method": evidence.get("extraction_method"),
                    "evidence_text": evidence.get("evidence_text"),
                }
            )
    feature_evidence_df = pd.DataFrame(feature_records)
    if feature_evidence_df.empty:
        feature_evidence_df = _read_csv(feature_path)
        if not feature_evidence_df.empty:
            feature_evidence_df["domain"] = feature_evidence_df["url"].map(_domain)
            feature_evidence_df["supported"] = feature_evidence_df["status"].isin(
                SUPPORTED_FEATURE_STATUSES
            )
            feature_evidence_df["confidence"] = pd.to_numeric(
                feature_evidence_df["confidence"], errors="coerce"
            ).fillna(0.0)
        else:
            feature_evidence_df = pd.DataFrame(
                columns=[
                    "url",
                    "domain",
                    "identity_accepted",
                    "identity_status",
                    "source_role",
                    "feature_id",
                    "feature_name",
                    "value",
                    "status",
                    "supported",
                    "confidence",
                    "evidence_location",
                    "extraction_method",
                    "evidence_text",
                ]
            )

    results_df = candidates_df.merge(
        agentic_df[
            [
                "requested_url",
                "candidate_id",
                "status",
                "turns_used",
                "actions_executed",
                "termination_reason",
                "error",
            ]
        ].rename(
            columns={
                "requested_url": "url",
                "status": "agentic_status",
                "error": "agentic_error",
            }
        ),
        on="url",
        how="left",
    )
    results_df = results_df.merge(
        browser_df[
            [
                column
                for column in [
                    "requested_url",
                    "browser_openable",
                    "rendered_product_verified",
                    "text_scrapable",
                    "multimodal_scrapable",
                    "gallery_discovered",
                    "direct_images_downloaded",
                    "screenshots_captured",
                    "blockers",
                    "warnings",
                    "error",
                ]
                if column in browser_df.columns
            ]
        ].rename(columns={"requested_url": "url", "error": "browser_error"}),
        on="url",
        how="left",
    )
    results_df = results_df.merge(assessment_df, on="url", how="left")

    for column in (
        "agentic_status",
        "termination_reason",
        "identity_status_assessment",
        "source_role",
    ):
        if column not in results_df:
            results_df[column] = ""
    for column in (
        "browser_openable",
        "rendered_product_verified",
        "text_scrapable",
        "multimodal_scrapable",
        "identity_accepted",
    ):
        if column not in results_df:
            results_df[column] = False
        results_df[column] = results_df[column].map(_bool)
    for column in ("coverage", "required_coverage", "critical_coverage"):
        if column not in results_df:
            results_df[column] = 0.0
        results_df[column] = pd.to_numeric(results_df[column], errors="coerce").fillna(0.0)

    investigated_urls = set(agentic_df.get("requested_url", pd.Series(dtype=str)).dropna())
    evidence_set = dict(result.get("evidence_set") or {})
    primary_url = _text(result.get("primary_url"))
    review_urls = set(_listify(evidence_set.get("selected_urls")))
    results_df["agentic_investigated"] = results_df["url"].isin(investigated_urls)
    results_df["strict_selected"] = results_df["url"] == primary_url
    results_df["review_selected"] = results_df["url"].isin(review_urls)
    results_df["feature_complete"] = results_df["coverage"] >= 1.0
    results_df["final_candidate_status"] = results_df.apply(_status_label, axis=1)
    results_df["missing_features_compact"] = results_df.get(
        "missing_features", pd.Series([[]] * len(results_df))
    ).map(lambda value: ", ".join(map(str, _listify(value))) or "—")
    results_df["conflicts_compact"] = results_df.get(
        "conflicting_features", pd.Series([[]] * len(results_df))
    ).map(lambda value: ", ".join(map(str, _listify(value))) or "—")
    results_df["assessment_rejection_compact"] = results_df.get(
        "assessment_rejection_reasons", pd.Series([[]] * len(results_df))
    ).map(_short_reason)

    results_df = results_df.sort_values(
        ["strict_selected", "review_selected", "quality_verified", "confidence", "coverage"],
        ascending=[False, False, False, False, False],
        kind="stable",
    ).reset_index(drop=True)
    results_df.insert(0, "candidate_rank", range(1, len(results_df) + 1))

    if not feature_evidence_df.empty:
        feature_matrix_df = feature_evidence_df.pivot_table(
            index="url",
            columns="feature_name",
            values="supported",
            aggfunc="max",
            fill_value=False,
        ).astype(int)
    else:
        feature_matrix_df = pd.DataFrame()

    raw_serp_count = int(
        search_stages_df.get("results_returned", pd.Series(dtype=float))
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0)
        .sum()
    )
    unique_serp_count = (
        int(serp_results_df["url"].nunique())
        if not serp_results_df.empty
        else len(results_df)
    )
    scrape_attempted = int(results_df["scrape_attempted"].sum())
    scrape_success = int(results_df["scrape_success"].sum())
    investigated = int(results_df["agentic_investigated"].sum())
    browser_openable = int(results_df["browser_openable"].sum())
    identity_accepted = int(results_df["identity_accepted"].sum())
    feature_complete = int(results_df["feature_complete"].sum())
    selected = int((results_df["strict_selected"] | results_df["review_selected"]).sum())

    funnel_df = pd.DataFrame(
        [
            ("SERP rows returned", raw_serp_count),
            ("Unique candidate URLs", unique_serp_count),
            ("Scrape attempted", scrape_attempted),
            ("Scrape successful", scrape_success),
            ("Agentic investigated", investigated),
            ("Browser openable", browser_openable),
            ("Identity accepted", identity_accepted),
            ("Feature complete", feature_complete),
            ("Selected", selected),
        ],
        columns=["stage", "count"],
    )
    funnel_df["conversion_from_previous"] = (
        funnel_df["count"]
        .div(funnel_df["count"].shift(1).replace(0, pd.NA))
        .fillna(1.0)
    )
    funnel_df["conversion_from_serp"] = (
        funnel_df["count"].div(raw_serp_count or 1)
    )

    domain_summary_df = (
        results_df.groupby("domain", dropna=False)
        .agg(
            candidates=("url", "count"),
            scrape_attempted=("scrape_attempted", "sum"),
            scraped=("scrape_success", "sum"),
            investigated=("agentic_investigated", "sum"),
            identity_accepted=("identity_accepted", "sum"),
            feature_complete=("feature_complete", "sum"),
            selected=("strict_selected", "sum"),
            mean_confidence=("confidence", "mean"),
            mean_coverage=("coverage", "mean"),
        )
        .reset_index()
        .sort_values(
            ["selected", "identity_accepted", "scraped", "mean_confidence"],
            ascending=[False, False, False, False],
            kind="stable",
        )
    )

    if "name" in search_stages_df:
        stage_quality_df = search_stages_df.copy()
        stage_quality_df["result_to_new_candidate_rate"] = (
            pd.to_numeric(stage_quality_df.get("new_candidate_urls"), errors="coerce")
            .fillna(0)
            .div(
                pd.to_numeric(stage_quality_df.get("results_returned"), errors="coerce")
                .replace(0, pd.NA)
            )
            .fillna(0.0)
        )
        stage_quality_df["new_candidate_to_scrape_rate"] = (
            pd.to_numeric(stage_quality_df.get("candidates_scraped"), errors="coerce")
            .fillna(0)
            .div(
                pd.to_numeric(stage_quality_df.get("new_candidate_urls"), errors="coerce")
                .replace(0, pd.NA)
            )
            .fillna(0.0)
        )
    else:
        stage_quality_df = pd.DataFrame()

    reason_rows: list[dict[str, Any]] = []
    for _, row in results_df.iterrows():
        sources = [
            ("candidate", row.get("decision_reasons")),
            ("feature_assessment", row.get("assessment_rejection_reasons")),
            ("browser_blocker", row.get("blockers")),
            ("agentic", row.get("termination_reason")),
            ("browser_error", row.get("browser_error")),
            ("agentic_error", row.get("agentic_error")),
        ]
        for source, value in sources:
            for reason in _reason_tokens(value):
                reason_rows.append(
                    {
                        "url": row["url"],
                        "domain": row["domain"],
                        "source": source,
                        "reason": reason,
                    }
                )
    rejection_detail_df = pd.DataFrame(reason_rows)
    if rejection_detail_df.empty:
        rejection_reasons_df = pd.DataFrame(
            columns=["source", "reason", "candidate_count", "candidate_share"]
        )
    else:
        rejection_reasons_df = (
            rejection_detail_df.groupby(["source", "reason"])
            .agg(candidate_count=("url", "nunique"))
            .reset_index()
            .sort_values("candidate_count", ascending=False, kind="stable")
        )
        rejection_reasons_df["candidate_share"] = rejection_reasons_df[
            "candidate_count"
        ].div(len(results_df) or 1)

    acceptance = dict(result.get("primary_url_acceptance") or {})
    product_match = dict(result.get("product_match") or {})
    selection_rca_df = pd.DataFrame(
        [
            ("Final job status", result.get("job_status")),
            ("Coding ready", result.get("coding_ready")),
            ("Strict primary accepted", acceptance.get("accepted")),
            ("Chosen primary URL", result.get("primary_url") or "NONE"),
            (
                "Supplementary/review URLs",
                " | ".join(map(str, result.get("supplementary_urls") or [])) or "NONE",
            ),
            ("URL decision status", product_match.get("url_decision_status")),
            ("Selection scope", product_match.get("selection_scope")),
            ("Identity status", product_match.get("identity_status")),
            ("Validation status", product_match.get("validation_status")),
            ("Confidence", product_match.get("confidence")),
            ("Evidence status", evidence_set.get("status")),
            ("Evidence coverage", evidence_set.get("total_coverage")),
            (
                "Missing features",
                ", ".join(map(str, evidence_set.get("missing_features") or [])) or "NONE",
            ),
            (
                "Conflicting features",
                ", ".join(map(str, evidence_set.get("conflicting_features") or []))
                or "NONE",
            ),
            (
                "Primary rejection reasons",
                " | ".join(map(str, acceptance.get("reasons") or [])) or "NONE",
            ),
        ],
        columns=["RCA item", "value"],
    )

    product = dict(result.get("product") or {})
    overview_df = pd.DataFrame(
        [
            ("Row ID", product.get("row_id")),
            ("Input product", product.get("main_text")),
            ("Country", product.get("country_code")),
            ("Requested retailer", product.get("retailer_name") or "NOT PROVIDED"),
            ("EAN/GTIN", product.get("ean") or "NOT PROVIDED"),
            ("SerpAPI calls", search.get("serpapi_requests_used")),
            ("SERP rows returned", raw_serp_count),
            ("Unique candidate URLs", unique_serp_count),
            ("Scrape attempted", scrape_attempted),
            ("Scrape successful", scrape_success),
            ("Agentic investigations", investigated),
            ("Identity accepted", identity_accepted),
            ("Feature complete", feature_complete),
            ("Final status", result.get("job_status")),
            ("Coding ready", result.get("coding_ready")),
            ("Primary URL", result.get("primary_url") or "NONE"),
        ],
        columns=["metric", "value"],
    )

    return SingleProductDiagnostics(
        overview_df=overview_df,
        search_stages_df=search_stages_df,
        serp_results_df=serp_results_df,
        results_df=results_df,
        agentic_df=agentic_df,
        feature_evidence_df=feature_evidence_df,
        feature_matrix_df=feature_matrix_df,
        funnel_df=funnel_df,
        domain_summary_df=domain_summary_df,
        stage_quality_df=stage_quality_df,
        rejection_reasons_df=rejection_reasons_df,
        selection_rca_df=selection_rca_df,
    )


def display_compact(
    df: pd.DataFrame,
    *,
    title: str,
    columns: Iterable[str] | None = None,
    max_rows: int = 25,
    precision: int = 3,
) -> None:
    from IPython.display import display

    frame = df.copy()
    if columns is not None:
        frame = frame[[column for column in columns if column in frame.columns]]
    if len(frame) > max_rows:
        frame = frame.head(max_rows)
    with pd.option_context(
        "display.max_colwidth",
        60,
        "display.max_columns",
        40,
        "display.width",
        180,
    ):
        styled = (
            frame.style
            .set_caption(title)
            .format(precision=precision, na_rep="—")
            .set_properties(**{"font-size": "11px"})
            .set_table_styles(
                [
                    {
                        "selector": "caption",
                        "props": [
                            ("font-size", "14px"),
                            ("font-weight", "bold"),
                            ("text-align", "left"),
                        ],
                    },
                    {
                        "selector": "th",
                        "props": [
                            ("font-size", "11px"),
                            ("text-align", "left"),
                            ("white-space", "nowrap"),
                        ],
                    },
                ]
            )
        )
        display(styled)


def display_rich_summary(diagnostics: SingleProductDiagnostics) -> None:
    console = Console()
    overview = Table(title="Single-product diagnostic summary", show_lines=True)
    overview.add_column("Metric", style="bold")
    overview.add_column("Value")
    for row in diagnostics.overview_df.itertuples(index=False):
        overview.add_row(_text(row.metric), _text(row.value))
    console.print(overview)

    selected = diagnostics.results_df[
        diagnostics.results_df["strict_selected"]
        | diagnostics.results_df["review_selected"]
    ]
    if selected.empty:
        console.print(
            Panel(
                "No URL passed final selection. Use selection_rca_df and "
                "rejection_reasons_df for the exact blocking gates.",
                title="Final decision",
            )
        )
    else:
        console.print(
            Panel(
                "\n".join(
                    f"{row.final_candidate_status}: {row.url}"
                    for row in selected.itertuples(index=False)
                ),
                title="Final decision",
            )
        )


def plot_funnel(diagnostics: SingleProductDiagnostics) -> None:
    frame = diagnostics.funnel_df
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=frame, x="count", y="stage", ax=ax)
    ax.set_title("Candidate conversion funnel")
    ax.set_xlabel("Count")
    ax.set_ylabel("")
    for container in ax.containers:
        ax.bar_label(container, fmt="%g", padding=3)
    plt.tight_layout()
    plt.show()


def plot_stage_yield(diagnostics: SingleProductDiagnostics) -> None:
    frame = diagnostics.search_stages_df.copy()
    if frame.empty:
        return
    long = frame.melt(
        id_vars=[column for column in ["serp_credit", "name"] if column in frame],
        value_vars=[
            column
            for column in ["results_returned", "new_candidate_urls", "candidates_scraped"]
            if column in frame
        ],
        var_name="metric",
        value_name="count",
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=long, x="name", y="count", hue="metric", ax=ax)
    ax.set_title("SERP stage yield")
    ax.set_xlabel("Search stage")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=20)
    plt.tight_layout()
    plt.show()


def plot_candidate_outcomes(diagnostics: SingleProductDiagnostics) -> None:
    frame = (
        diagnostics.results_df["final_candidate_status"]
        .value_counts(dropna=False)
        .rename_axis("status")
        .reset_index(name="count")
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(data=frame, x="count", y="status", ax=ax)
    ax.set_title("Per-candidate final outcome")
    ax.set_xlabel("Candidates")
    ax.set_ylabel("")
    for container in ax.containers:
        ax.bar_label(container, fmt="%g", padding=3)
    plt.tight_layout()
    plt.show()


def plot_confidence_distribution(diagnostics: SingleProductDiagnostics) -> None:
    frame = diagnostics.results_df
    if frame.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.histplot(data=frame, x="confidence", bins=10, kde=True, ax=ax)
    ax.set_title("Candidate confidence distribution")
    ax.set_xlabel("Final confidence")
    plt.tight_layout()
    plt.show()


def plot_confidence_vs_coverage(diagnostics: SingleProductDiagnostics) -> None:
    frame = diagnostics.results_df
    if frame.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.scatterplot(
        data=frame,
        x="confidence",
        y="coverage",
        hue="final_candidate_status",
        size="richness",
        sizes=(40, 250),
        ax=ax,
    )
    ax.set_title("Candidate confidence vs feature coverage")
    ax.set_xlabel("Final confidence")
    ax.set_ylabel("Feature coverage")
    ax.set_ylim(-0.05, 1.05)
    plt.tight_layout()
    plt.show()


def plot_domain_quality(diagnostics: SingleProductDiagnostics, *, top_n: int = 15) -> None:
    frame = diagnostics.domain_summary_df.head(top_n).copy()
    if frame.empty:
        return
    fig, ax = plt.subplots(figsize=(10, max(5, len(frame) * 0.35)))
    sns.barplot(data=frame, x="candidates", y="domain", ax=ax)
    ax.set_title(f"Candidate volume by domain (top {top_n})")
    ax.set_xlabel("Candidate URLs")
    ax.set_ylabel("")
    plt.tight_layout()
    plt.show()


def plot_rejection_reasons(
    diagnostics: SingleProductDiagnostics,
    *,
    top_n: int = 15,
) -> None:
    frame = diagnostics.rejection_reasons_df.head(top_n).copy()
    if frame.empty:
        return
    fig, ax = plt.subplots(figsize=(10, max(5, len(frame) * 0.35)))
    sns.barplot(data=frame, x="candidate_count", y="reason", hue="source", ax=ax)
    ax.set_title(f"Most frequent rejection/blocking reasons (top {top_n})")
    ax.set_xlabel("Affected candidates")
    ax.set_ylabel("")
    plt.tight_layout()
    plt.show()


def plot_feature_heatmap(diagnostics: SingleProductDiagnostics) -> None:
    frame = diagnostics.feature_matrix_df
    if frame.empty:
        return
    height = max(4, min(18, 0.35 * len(frame) + 2))
    width = max(8, min(22, 1.2 * len(frame.columns) + 5))
    fig, ax = plt.subplots(figsize=(width, height))
    sns.heatmap(frame, annot=True, fmt="d", cbar=False, linewidths=0.5, ax=ax)
    ax.set_title("URL × requested-feature support matrix")
    ax.set_xlabel("Requested feature")
    ax.set_ylabel("Candidate URL")
    plt.tight_layout()
    plt.show()


def plot_all_diagnostics(diagnostics: SingleProductDiagnostics) -> None:
    plot_funnel(diagnostics)
    plot_stage_yield(diagnostics)
    plot_candidate_outcomes(diagnostics)
    plot_confidence_distribution(diagnostics)
    plot_confidence_vs_coverage(diagnostics)
    plot_domain_quality(diagnostics)
    plot_rejection_reasons(diagnostics)
    plot_feature_heatmap(diagnostics)
