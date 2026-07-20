from __future__ import annotations

import html
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs
from plotly.io import to_html

from .artifact_diagnostics import ArtifactDiagnostics


@dataclass(slots=True)
class InteractiveArtifactDashboard:
    """Interactive, table-free diagnostic workspace for one product artifact."""

    diagnostics: ArtifactDiagnostics
    figures: dict[str, go.Figure]
    output_path: Path
    html: str


@dataclass(frozen=True, slots=True)
class _DashboardSection:
    key: str
    title: str
    description: str
    figure: go.Figure


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    return text or default


def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and _text(value):
            return value
    return default


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return default if isinstance(value, float) and math.isnan(value) else float(value)
    raw = str(value).strip().replace(",", "")
    if not raw:
        return default
    percent = raw.endswith("%")
    raw = raw.rstrip("%")
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return parsed / 100.0 if percent else parsed


def _bounded_ratio(value: Any) -> float:
    parsed = _number(value, 0.0)
    if parsed > 1.0 and parsed <= 100.0:
        parsed /= 100.0
    return min(1.0, max(0.0, parsed))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _text(value).lower() in {
        "1",
        "true",
        "yes",
        "y",
        "accepted",
        "selected",
        "pass",
        "passed",
    }


def _safe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return frame.fillna("").to_dict(orient="records")


def _short_url(value: Any, limit: int = 78) -> str:
    text = _text(value, "not available")
    if len(text) <= limit:
        return text
    parsed = urlparse(text)
    compact = f"{parsed.netloc}{parsed.path}" if parsed.netloc else text
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _domain(value: Any) -> str:
    parsed = urlparse(_text(value))
    return parsed.netloc.lower() or "unknown-source"


def _hover_lines(pairs: Iterable[tuple[str, Any]]) -> str:
    lines = []
    for label, value in pairs:
        text = _text(value)
        if text:
            lines.append(f"<b>{html.escape(label)}:</b> {html.escape(text)}")
    return "<br>".join(lines)


def _figure_layout(fig: go.Figure, *, title: str, height: int) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0.02, "xanchor": "left"},
        template="plotly_white",
        height=height,
        margin={"l": 28, "r": 28, "t": 72, "b": 30},
        hoverlabel={"align": "left"},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    return fig


def build_interactive_decision_map(diagnostics: ArtifactDiagnostics) -> go.Figure:
    nodes = _safe_records(diagnostics.mindmap_nodes_df)
    edges = _safe_records(diagnostics.mindmap_edges_df)
    if not nodes:
        raise ValueError("No decision-map nodes were reconstructed from the artifact")

    depths: dict[int, list[dict[str, Any]]] = {}
    for row in nodes:
        depth = int(_number(row.get("depth"), 0))
        depths.setdefault(depth, []).append(row)
    for rows in depths.values():
        rows.sort(key=lambda item: _number(item.get("order"), 0))

    positions: dict[str, tuple[float, float]] = {}
    max_depth = max(depths) if depths else 0
    for depth, rows in depths.items():
        count = max(len(rows), 1)
        for index, row in enumerate(rows):
            node_id = str(row.get("node_id"))
            x = depth / max(max_depth, 1)
            y = 1.0 - ((index + 1) / (count + 1))
            if node_id == "root":
                x, y = 0.02, 0.5
            positions[node_id] = (x, y)

    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in edges:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if source not in positions or target not in positions:
            continue
        x0, y0 = positions[source]
        x1, y1 = positions[target]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            hoverinfo="skip",
            line={"width": 1.2},
            showlegend=False,
        )
    )

    groups = sorted({_text(row.get("group"), "other") for row in nodes})
    for group in groups:
        rows = [row for row in nodes if _text(row.get("group"), "other") == group]
        x = [positions[str(row.get("node_id"))][0] for row in rows]
        y = [positions[str(row.get("node_id"))][1] for row in rows]
        labels = [
            _text(row.get("label"), str(row.get("node_id"))).split("\n", 1)[0]
            for row in rows
        ]
        hover = [
            _hover_lines(
                [
                    ("Stage", group.replace("_", " ").title()),
                    ("Recorded detail", _text(row.get("label")).replace("\n", " · ")),
                    ("Node", row.get("node_id")),
                ]
            )
            for row in rows
        ]
        sizes = [
            34
            if str(row.get("node_id")) == "root"
            else (25 if group == "judgment_step" else 29)
            for row in rows
        ]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="markers+text",
                name=group.replace("_", " ").title(),
                text=labels,
                textposition="top center",
                customdata=hover,
                hovertemplate="%{customdata}<extra></extra>",
                marker={"size": sizes, "line": {"width": 1}},
            )
        )

    fig.update_xaxes(visible=False, fixedrange=False)
    fig.update_yaxes(visible=False, fixedrange=False)
    fig.update_layout(
        dragmode="pan",
        annotations=[
            {
                "text": "Hover for full recorded detail · drag to pan · use the toolbar to zoom/reset · click legend items to isolate stages",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.08,
                "showarrow": False,
                "xanchor": "left",
            }
        ],
    )
    return _figure_layout(fig, title="Interactive observable agent decision map", height=760)


def build_interactive_judgement_timeline(diagnostics: ArtifactDiagnostics) -> go.Figure:
    records = _safe_records(diagnostics.business_judgement_steps_df)
    if not records:
        return _figure_layout(
            go.Figure().add_annotation(
                text="No structured business judgments were recorded",
                showarrow=False,
            ),
            title="Chronological business judgment timeline",
            height=460,
        )

    statuses = []
    for row in records:
        status = (
            _text(_first(row, "judgement_status", "status"), "recorded")
            .replace("_", " ")
            .title()
        )
        if status not in statuses:
            statuses.append(status)

    fig = go.Figure()
    for status in statuses:
        subset = [
            row
            for row in records
            if _text(_first(row, "judgement_status", "status"), "recorded")
            .replace("_", " ")
            .title()
            == status
        ]
        x = [
            int(_number(_first(row, "sequence_number"), index + 1))
            for index, row in enumerate(subset)
        ]
        y = [0] * len(subset)
        labels = [
            _text(_first(row, "decision_stage", "stage"), f"Step {index + 1}")
            for index, row in enumerate(subset)
        ]
        confidence = [_bounded_ratio(_first(row, "confidence")) for row in subset]
        hover = [
            _hover_lines(
                [
                    ("Business question", _first(row, "business_question")),
                    ("Evidence considered", _first(row, "evidence_considered")),
                    ("Evidence sources", _first(row, "evidence_sources")),
                    ("Agent judgment", _first(row, "agent_judgement", "judgment")),
                    ("Rule applied", _first(row, "business_rule_applied")),
                    ("Next action", _first(row, "effect_on_next_action")),
                    ("Alternative rejected", _first(row, "alternative_rejected")),
                    ("Rejection reason", _first(row, "rejection_reason")),
                    (
                        "Visual evidence",
                        _first(row, "visual_evidence_details", "visual_evidence_used"),
                    ),
                    ("Confidence", _first(row, "confidence")),
                    ("Final outcome", _first(row, "final_outcome")),
                ]
            )
            for row in subset
        ]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="markers+text",
                name=status,
                text=labels,
                textposition="top center",
                customdata=hover,
                hovertemplate="<b>Step %{x}</b><br>%{customdata}<extra></extra>",
                marker={
                    "size": [22 + 18 * value for value in confidence],
                    "line": {"width": 1},
                },
            )
        )

    full_x = [
        int(_number(_first(row, "sequence_number"), index + 1))
        for index, row in enumerate(records)
    ]
    fig.add_trace(
        go.Scatter(
            x=full_x,
            y=[0] * len(full_x),
            mode="lines",
            line={"width": 2},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.update_yaxes(visible=False, range=[-0.7, 0.7])
    fig.update_xaxes(title="Recorded judgment sequence", dtick=1, fixedrange=False)
    fig.update_layout(
        dragmode="pan",
        annotations=[
            {
                "text": "Marker size follows recorded confidence. Hover each step to inspect evidence, rule, rejected alternative and next action.",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.2,
                "showarrow": False,
                "xanchor": "left",
            }
        ],
    )
    return _figure_layout(fig, title="Chronological business judgment timeline", height=580)


def _candidate_decision(row: Mapping[str, Any], primary_url: str) -> str:
    url = _text(row.get("url"))
    if url and url == primary_url:
        return "Selected primary"
    if any(
        _truthy(row.get(key))
        for key in ("strict_selected", "review_selected", "selected")
    ):
        return "Selected alternative"
    if any(
        _truthy(row.get(key))
        for key in ("identity_accepted", "browser_openable", "scrapable")
    ):
        return "Eligible / investigated"
    return "Rejected / unresolved"


def build_interactive_candidate_explorer(diagnostics: ArtifactDiagnostics) -> go.Figure:
    records = _safe_records(diagnostics.candidates_df)
    if not records:
        return _figure_layout(
            go.Figure().add_annotation(text="No candidate records were found", showarrow=False),
            title="Candidate URL explorer",
            height=520,
        )

    primary_url = _text(diagnostics.result.get("primary_url"))
    decisions = []
    for row in records:
        decision = _candidate_decision(row, primary_url)
        if decision not in decisions:
            decisions.append(decision)

    fig = go.Figure()
    for decision in decisions:
        subset = [
            row for row in records if _candidate_decision(row, primary_url) == decision
        ]
        coverage = [
            _bounded_ratio(
                _first(row, "coverage", "feature_coverage", "coverage_ratio")
            )
            for row in subset
        ]
        confidence = [
            _bounded_ratio(
                _first(row, "confidence", "score", "final_score", "identity_confidence")
            )
            for row in subset
        ]
        evidence_count = [
            max(
                1,
                int(
                    _number(
                        _first(
                            row,
                            "evidence_count",
                            "feature_evidence_count",
                            "supporting_evidence_count",
                        ),
                        1,
                    )
                ),
            )
            for row in subset
        ]
        hover = [
            _hover_lines(
                [
                    ("URL", row.get("url")),
                    ("Source role", _first(row, "source_role", "source_tier_name")),
                    ("Identity", _first(row, "identity_status", "identity_accepted")),
                    ("Browser openable", row.get("browser_openable")),
                    ("Scrapable", row.get("scrapable")),
                    (
                        "Coverage",
                        _first(row, "coverage", "feature_coverage", "coverage_ratio"),
                    ),
                    (
                        "Confidence",
                        _first(row, "confidence", "score", "final_score"),
                    ),
                    (
                        "Decision reasons",
                        _first(row, "decision_reasons", "selection_reason"),
                    ),
                    (
                        "Rejection reasons",
                        _first(row, "rejection_reasons", "rejection_reason"),
                    ),
                    ("Missing features", row.get("missing_features")),
                ]
            )
            for row in subset
        ]
        fig.add_trace(
            go.Scatter(
                x=coverage,
                y=confidence,
                mode="markers",
                name=decision,
                text=[_short_url(row.get("url"), 60) for row in subset],
                customdata=hover,
                hovertemplate="<b>%{text}</b><br>%{customdata}<extra></extra>",
                marker={
                    "size": [16 + min(24, count * 3) for count in evidence_count],
                    "opacity": 0.82,
                    "line": {"width": 1},
                },
            )
        )

    trace_count = len(fig.data)
    all_visible = [True] * trace_count
    buttons = [
        {
            "label": "All candidates",
            "method": "update",
            "args": [{"visible": all_visible}],
        }
    ]
    for index, decision in enumerate(decisions):
        visible = [False] * trace_count
        visible[index] = True
        buttons.append(
            {"label": decision, "method": "update", "args": [{"visible": visible}]}
        )

    fig.update_layout(
        updatemenus=[
            {
                "buttons": buttons,
                "direction": "down",
                "showactive": True,
                "x": 0,
                "xanchor": "left",
                "y": 1.14,
                "yanchor": "top",
            }
        ],
        dragmode="select",
    )
    fig.update_xaxes(
        title="Requested-feature coverage",
        range=[-0.03, 1.03],
        tickformat=".0%",
    )
    fig.update_yaxes(
        title="Recorded candidate confidence",
        range=[-0.03, 1.03],
        tickformat=".0%",
    )
    return _figure_layout(fig, title="Candidate URL explorer", height=650)


def build_interactive_evidence_explorer(diagnostics: ArtifactDiagnostics) -> go.Figure:
    records = _safe_records(diagnostics.feature_evidence_df)
    if not records:
        return _figure_layout(
            go.Figure().add_annotation(
                text="No feature-evidence records were found",
                showarrow=False,
            ),
            title="Evidence explorer",
            height=540,
        )

    root_id = "evidence-root"
    ids = [root_id]
    labels = ["All recorded evidence"]
    parents = [""]
    values = [max(len(records), 1)]
    hover = [f"{len(records)} feature-evidence records"]

    methods: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        method = _text(
            _first(row, "extraction_method", "method", "evidence_type"),
            "unspecified method",
        )
        methods.setdefault(method, []).append(row)

    for method_index, (method, method_rows) in enumerate(sorted(methods.items())):
        method_id = f"method-{method_index}"
        ids.append(method_id)
        labels.append(method)
        parents.append(root_id)
        values.append(len(method_rows))
        hover.append(f"{len(method_rows)} records extracted via {html.escape(method)}")

        sources: dict[str, list[dict[str, Any]]] = {}
        for row in method_rows:
            source = _text(_first(row, "source_role"), "") or _domain(row.get("url"))
            sources.setdefault(source, []).append(row)

        for source_index, (source, source_rows) in enumerate(sorted(sources.items())):
            source_id = f"{method_id}-source-{source_index}"
            ids.append(source_id)
            labels.append(source)
            parents.append(method_id)
            values.append(len(source_rows))
            hover.append(f"{len(source_rows)} records from {html.escape(source)}")

            for feature_index, row in enumerate(source_rows):
                feature_id = f"{source_id}-feature-{feature_index}"
                feature_name = _text(
                    _first(row, "feature_name", "feature_id"),
                    "unnamed feature",
                )
                ids.append(feature_id)
                labels.append(feature_name)
                parents.append(source_id)
                values.append(1)
                hover.append(
                    _hover_lines(
                        [
                            ("Feature", feature_name),
                            ("Value", row.get("value")),
                            ("Status", row.get("status")),
                            ("Confidence", row.get("confidence")),
                            (
                                "Evidence",
                                _first(row, "evidence_text", "evidence_location"),
                            ),
                            ("URL", row.get("url")),
                        ]
                    )
                )

    fig = go.Figure(
        go.Sunburst(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            customdata=hover,
            hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
            maxdepth=4,
        )
    )
    fig.update_layout(
        annotations=[
            {
                "text": "Click a segment to zoom into evidence method → source → feature. Click the center to move back up.",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.06,
                "showarrow": False,
                "xanchor": "left",
            }
        ]
    )
    return _figure_layout(fig, title="Interactive evidence explorer", height=700)


def build_interactive_artifact_map(diagnostics: ArtifactDiagnostics) -> go.Figure:
    records = _safe_records(diagnostics.artifact_inventory_df)
    if not records:
        return _figure_layout(
            go.Figure().add_annotation(text="No artifact inventory was found", showarrow=False),
            title="Generated artifact map",
            height=500,
        )

    labels = ["Product artifact"]
    parents = [""]
    ids = ["artifact-root"]
    values = [
        sum(max(1, int(_number(row.get("size_bytes"), 1))) for row in records)
    ]
    customdata = [
        f"{len(records)} files in {html.escape(str(diagnostics.artifact_dir))}"
    ]

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        suffix = _text(row.get("suffix"), "no extension") or "no extension"
        groups.setdefault(suffix, []).append(row)

    for group_index, (suffix, group_rows) in enumerate(sorted(groups.items())):
        group_id = f"artifact-group-{group_index}"
        group_size = sum(
            max(1, int(_number(row.get("size_bytes"), 1))) for row in group_rows
        )
        ids.append(group_id)
        labels.append(suffix)
        parents.append("artifact-root")
        values.append(group_size)
        customdata.append(f"{len(group_rows)} files · {group_size:,} bytes")
        for file_index, row in enumerate(group_rows):
            file_id = f"{group_id}-file-{file_index}"
            ids.append(file_id)
            labels.append(_text(row.get("file_name"), "unknown file"))
            parents.append(group_id)
            values.append(max(1, int(_number(row.get("size_bytes"), 1))))
            customdata.append(
                _hover_lines(
                    [
                        ("Purpose", row.get("purpose")),
                        (
                            "Size",
                            f"{int(_number(row.get('size_bytes'), 0)):,} bytes",
                        ),
                        ("Contract artifact", row.get("present_in_contract")),
                        ("Path", row.get("path")),
                    ]
                )
            )

    fig = go.Figure(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            customdata=customdata,
            hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
            root={"color": "lightgrey"},
        )
    )
    fig.update_layout(
        annotations=[
            {
                "text": "Tile area follows file size. Click a group to zoom; hover a file to understand its purpose and path.",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.05,
                "showarrow": False,
                "xanchor": "left",
            }
        ]
    )
    return _figure_layout(fig, title="Generated artifact map", height=650)


def _overview_cards(diagnostics: ArtifactDiagnostics) -> str:
    overview = (
        diagnostics.overview_df.iloc[0].to_dict()
        if not diagnostics.overview_df.empty
        else {}
    )
    cards = [
        ("Status", _text(overview.get("job_status"), "unknown")),
        ("Primary role", _text(overview.get("primary_url_role"), "unknown")),
        ("Candidates", _text(overview.get("candidate_rows"), "0")),
        ("Judgments", _text(overview.get("business_judgement_count"), "0")),
        ("Evidence records", _text(overview.get("feature_evidence_rows"), "0")),
        (
            "Visual impact",
            _text(overview.get("image_influenced_final_decision"), "not recorded"),
        ),
    ]
    card_html = "".join(
        f'<div class="diag-card"><div class="diag-card-label">{html.escape(label)}</div>'
        f'<div class="diag-card-value">{html.escape(value)}</div></div>'
        for label, value in cards
    )
    primary = _text(overview.get("primary_url"), "not delivered")
    reason = _text(overview.get("selection_reason"), "not recorded")
    product = _text(overview.get("identified_product"), "unresolved product")
    return (
        f'<div class="diag-product"><strong>{html.escape(product)}</strong>'
        f'<span>{html.escape(primary)}</span><small>{html.escape(reason)}</small></div>'
        f'<div class="diag-cards">{card_html}</div>'
    )


def _dashboard_html(
    diagnostics: ArtifactDiagnostics,
    sections: list[_DashboardSection],
) -> str:
    plotly_js = get_plotlyjs()
    tab_buttons = []
    tab_panels = []
    config = {
        "responsive": True,
        "displaylogo": False,
        "scrollZoom": True,
        "modeBarButtonsToRemove": ["lasso2d"],
    }
    for index, section in enumerate(sections):
        active = " active" if index == 0 else ""
        tab_buttons.append(
            f'<button class="diag-tab-button{active}" '
            f'onclick="openDiagTab(event, \'{section.key}\')">'
            f"{html.escape(section.title)}</button>"
        )
        figure_html = to_html(
            section.figure,
            include_plotlyjs=False,
            full_html=False,
            config=config,
        )
        tab_panels.append(
            f'<section id="{section.key}" class="diag-tab-panel{active}">'
            f'<p class="diag-instruction">{html.escape(section.description)}</p>'
            f"{figure_html}</section>"
        )

    artifact_dir = html.escape(str(diagnostics.artifact_dir))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interactive Product Artifact Diagnostics</title>
<script>{plotly_js}</script>
<style>
:root {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #172033; background: #f6f8fb; }}
body {{ margin: 0; padding: 22px; background: #f6f8fb; }}
.diag-shell {{ max-width: 1500px; margin: auto; }}
.diag-header {{ background: white; border: 1px solid #dfe5ee; border-radius: 18px; padding: 20px; box-shadow: 0 8px 30px rgba(23,32,51,.06); }}
.diag-title {{ margin: 0 0 4px; font-size: 26px; }}
.diag-subtitle {{ margin: 0; color: #5a6578; }}
.diag-product {{ display: grid; gap: 5px; margin: 18px 0 14px; padding: 14px 16px; border-left: 5px solid #536dfe; background: #f8f9ff; border-radius: 10px; overflow-wrap: anywhere; }}
.diag-product span, .diag-product small {{ color: #4d586a; }}
.diag-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
.diag-card {{ border: 1px solid #e3e8f0; border-radius: 12px; padding: 12px; background: #fff; }}
.diag-card-label {{ color: #6c7789; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
.diag-card-value {{ margin-top: 5px; font-size: 18px; font-weight: 650; overflow-wrap: anywhere; }}
.diag-tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 20px 0 10px; }}
.diag-tab-button {{ border: 1px solid #cfd6e2; border-radius: 999px; padding: 9px 15px; background: white; cursor: pointer; font-weight: 600; }}
.diag-tab-button.active {{ background: #172033; color: white; border-color: #172033; }}
.diag-tab-panel {{ display: none; background: white; border: 1px solid #dfe5ee; border-radius: 16px; padding: 10px 14px 4px; box-shadow: 0 8px 30px rgba(23,32,51,.05); }}
.diag-tab-panel.active {{ display: block; }}
.diag-instruction {{ margin: 10px 10px 0; color: #5d687a; }}
.diag-footer {{ margin-top: 14px; color: #6c7789; font-size: 12px; overflow-wrap: anywhere; }}
@media (max-width: 700px) {{ body {{ padding: 10px; }} .diag-title {{ font-size: 21px; }} }}
</style>
</head>
<body>
<div class="diag-shell">
  <header class="diag-header">
    <h1 class="diag-title">Interactive Product Artifact Diagnostics</h1>
    <p class="diag-subtitle">Explore recorded evidence, actions, business rules, judgments and conclusions. This view does not expose hidden chain-of-thought.</p>
    {_overview_cards(diagnostics)}
  </header>
  <nav class="diag-tabs">{''.join(tab_buttons)}</nav>
  {''.join(tab_panels)}
  <div class="diag-footer">Artifact: {artifact_dir}</div>
</div>
<script>
function openDiagTab(event, tabId) {{
  document.querySelectorAll('.diag-tab-panel').forEach(function(panel) {{ panel.classList.remove('active'); }});
  document.querySelectorAll('.diag-tab-button').forEach(function(button) {{ button.classList.remove('active'); }});
  document.getElementById(tabId).classList.add('active');
  event.currentTarget.classList.add('active');
  window.setTimeout(function() {{
    document.getElementById(tabId).querySelectorAll('.plotly-graph-div').forEach(function(plot) {{ Plotly.Plots.resize(plot); }});
  }}, 40);
}}
</script>
</body>
</html>"""


def build_interactive_artifact_dashboard(
    diagnostics: ArtifactDiagnostics,
    *,
    output_path: str | Path | None = None,
) -> InteractiveArtifactDashboard:
    """Build and persist the primary interactive diagnostic experience."""

    figures = {
        "Decision map": build_interactive_decision_map(diagnostics),
        "Judgment timeline": build_interactive_judgement_timeline(diagnostics),
        "Candidate explorer": build_interactive_candidate_explorer(diagnostics),
        "Evidence explorer": build_interactive_evidence_explorer(diagnostics),
        "Artifact map": build_interactive_artifact_map(diagnostics),
    }
    sections = [
        _DashboardSection(
            "decision-map",
            "Decision map",
            "Navigate the observable end-to-end process. Hover nodes for full details, pan, zoom and isolate stages from the legend.",
            figures["Decision map"],
        ),
        _DashboardSection(
            "judgment-timeline",
            "Judgment timeline",
            "Follow the exact recorded business-judgment order. Hover each step to inspect evidence, rules, alternatives and next actions.",
            figures["Judgment timeline"],
        ),
        _DashboardSection(
            "candidate-explorer",
            "Candidates",
            "Compare candidate confidence and feature coverage. Use the dropdown and legend to focus on selected, eligible or rejected URLs.",
            figures["Candidate explorer"],
        ),
        _DashboardSection(
            "evidence-explorer",
            "Evidence",
            "Click through evidence method, source and feature. This makes text, browser and visual evidence explorable without a large table.",
            figures["Evidence explorer"],
        ),
        _DashboardSection(
            "artifact-map",
            "Artifacts",
            "Explore the generated files by type and size. Hover to understand the purpose and exact path of each artifact.",
            figures["Artifact map"],
        ),
    ]
    dashboard_html = _dashboard_html(diagnostics, sections)
    output = (
        Path(output_path).expanduser().resolve()
        if output_path
        else diagnostics.artifact_dir / "artifact_diagnostics_interactive.html"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dashboard_html, encoding="utf-8")
    return InteractiveArtifactDashboard(
        diagnostics=diagnostics,
        figures=figures,
        output_path=output,
        html=dashboard_html,
    )


def display_interactive_artifact_dashboard(
    dashboard: InteractiveArtifactDashboard,
    *,
    height: int = 980,
) -> Any:
    """Display the dashboard in a notebook, preferring compact tabs when available."""

    from IPython.display import HTML, display

    try:
        import ipywidgets as widgets
    except ModuleNotFoundError:
        display(HTML(dashboard.html))
        return None

    outputs = []
    for figure in dashboard.figures.values():
        output = widgets.Output(layout=widgets.Layout(width="100%"))
        with output:
            figure.show(
                config={
                    "responsive": True,
                    "displaylogo": False,
                    "scrollZoom": True,
                }
            )
        outputs.append(output)

    tabs = widgets.Tab(
        children=outputs,
        layout=widgets.Layout(width="100%", min_height=f"{height}px"),
    )
    for index, title in enumerate(dashboard.figures):
        tabs.set_title(index, title)

    overview = (
        dashboard.diagnostics.overview_df.iloc[0].to_dict()
        if not dashboard.diagnostics.overview_df.empty
        else {}
    )
    header = HTML(
        "<div style='padding:14px 16px;border:1px solid #dfe5ee;border-radius:12px;margin-bottom:10px'>"
        f"<b>{html.escape(_text(overview.get('identified_product'), 'Product artifact'))}</b><br>"
        f"<span>{html.escape(_text(overview.get('job_status'), 'unknown'))} · "
        f"{html.escape(_text(overview.get('primary_url_role'), 'unknown role'))}</span><br>"
        f"<small>{html.escape(_text(overview.get('primary_url'), 'URL not delivered'))}</small>"
        "</div>"
    )
    display(header, tabs)
    return tabs
