from __future__ import annotations

import json
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


KNOWN_ARTIFACT_FILES = (
    "business_judgement_review.md",
    "product_belief.json",
    "product_understanding.md",
    "market_decision_path.md",
    "belief_updates.md",
    "evidence_ledger.jsonl",
    "adaptive_search_trace.json",
    "candidate_url_records.json",
    "candidates.csv",
    "feature_evidence.csv",
    "primary_url_acceptance.json",
    "mandatory_url_delivery.json",
    "source_selection.json",
    "orchestrated_result.json",
    "review.md",
    "single_product_diagnostics.xlsx",
)


@dataclass(slots=True)
class ArtifactDiagnostics:
    artifact_dir: Path
    result: dict[str, Any]
    overview_df: pd.DataFrame
    product_input_df: pd.DataFrame
    business_judgement_steps_df: pd.DataFrame
    visual_evidence_summary_df: pd.DataFrame
    search_steps_df: pd.DataFrame
    candidates_df: pd.DataFrame
    feature_evidence_df: pd.DataFrame
    evidence_ledger_df: pd.DataFrame
    belief_updates_df: pd.DataFrame
    artifact_inventory_df: pd.DataFrame
    mindmap_nodes_df: pd.DataFrame
    mindmap_edges_df: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "overview_df": self.overview_df,
            "product_input_df": self.product_input_df,
            "business_judgement_steps_df": self.business_judgement_steps_df,
            "visual_evidence_summary_df": self.visual_evidence_summary_df,
            "search_steps_df": self.search_steps_df,
            "candidates_df": self.candidates_df,
            "feature_evidence_df": self.feature_evidence_df,
            "evidence_ledger_df": self.evidence_ledger_df,
            "belief_updates_df": self.belief_updates_df,
            "artifact_inventory_df": self.artifact_inventory_df,
            "mindmap_nodes_df": self.mindmap_nodes_df,
            "mindmap_edges_df": self.mindmap_edges_df,
        }


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"records": payload}


def _read_jsonl(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError:
            records.append({"line_number": line_number, "raw": text, "parse_error": True})
            continue
        records.append(item if isinstance(item, dict) else {"value": item})
    return pd.DataFrame(records)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _flatten_feature_evidence(result: Mapping[str, Any]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for assessment in result.get("feature_assessments") or []:
        if not isinstance(assessment, Mapping):
            continue
        for evidence in assessment.get("evidence") or []:
            if not isinstance(evidence, Mapping):
                continue
            records.append(
                {
                    "url": assessment.get("url"),
                    "source_role": assessment.get("source_role"),
                    "identity_accepted": assessment.get("identity_accepted"),
                    "coverage": assessment.get("coverage"),
                    "feature_id": evidence.get("feature_id"),
                    "feature_name": evidence.get("feature_name"),
                    "value": evidence.get("value"),
                    "status": evidence.get("status"),
                    "confidence": evidence.get("confidence"),
                    "extraction_method": evidence.get("extraction_method"),
                    "evidence_location": evidence.get("evidence_location"),
                    "evidence_text": evidence.get("evidence_text"),
                }
            )
    return pd.DataFrame(records)


def resolve_artifact_dir(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        raise FileNotFoundError(f"Artifact path does not exist: {candidate}")
    root = candidate.parent if candidate.is_file() else candidate

    if (root / "orchestrated_result.json").is_file():
        return root

    parents = (root, *root.parents)
    for parent in parents:
        if (parent / "orchestrated_result.json").is_file():
            return parent

    expected = ", ".join(KNOWN_ARTIFACT_FILES[:6])
    raise ValueError(
        f"{candidate} is not inside a recognized product artifact directory. "
        f"Expected orchestrated_result.json and related files such as: {expected}"
    )


def _search_steps(result: Mapping[str, Any], search_trace: Mapping[str, Any]) -> pd.DataFrame:
    search = result.get("search") if isinstance(result.get("search"), Mapping) else {}
    stages = list(search.get("stages") or [])
    if not stages:
        stages = list(search_trace.get("search_actions") or search_trace.get("stages") or [])
    return pd.DataFrame(stages)


def _candidate_frame(result: Mapping[str, Any], artifact_dir: Path) -> pd.DataFrame:
    frame = _read_csv(artifact_dir / "candidates.csv")
    if not frame.empty:
        return frame
    records = result.get("candidate_url_records") or result.get("candidate_records") or []
    if records:
        return pd.DataFrame(records)
    records = []
    for item in result.get("feature_assessments") or []:
        if isinstance(item, Mapping):
            records.append(
                {
                    "url": item.get("url"),
                    "source_role": item.get("source_role"),
                    "identity_accepted": item.get("identity_accepted"),
                    "coverage": item.get("coverage"),
                    "missing_features": item.get("missing_features"),
                    "rejection_reasons": item.get("rejection_reasons"),
                }
            )
    return pd.DataFrame(records)


def _markdown_table(frame: pd.DataFrame, *, max_rows: int | None = None) -> str:
    data = frame.head(max_rows).copy() if max_rows is not None else frame.copy()
    if data.empty:
        return "_No records._"
    data = data.fillna("").astype(str)
    columns = [str(column) for column in data.columns]

    def escape(value: Any) -> str:
        return " ".join(str(value).replace("|", "\\|").split())

    lines = [
        "| " + " | ".join(escape(column) for column in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in data.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(escape(value) for value in row) + " |")
    return "\n".join(lines)


def _artifact_inventory(artifact_dir: Path) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for path in sorted(item for item in artifact_dir.iterdir() if item.is_file()):
        records.append(
            {
                "file_name": path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "purpose": _artifact_purpose(path.name),
                "present_in_contract": path.name in KNOWN_ARTIFACT_FILES,
                "path": str(path),
            }
        )
    return pd.DataFrame(records)


def _artifact_purpose(name: str) -> str:
    purposes = {
        "business_judgement_review.md": "Human-comparable observable decision sequence",
        "product_belief.json": "Product hypotheses, uncertainties, posterior state and evidence ledger",
        "product_understanding.md": "Readable product interpretation",
        "market_decision_path.md": "Country, retailer and global routing decisions",
        "belief_updates.md": "Readable belief changes after evidence",
        "evidence_ledger.jsonl": "Atomic evidence records",
        "adaptive_search_trace.json": "Search plans, engines, credits and feedback",
        "candidate_url_records.json": "Candidate provenance and status",
        "candidates.csv": "Candidate-level ranking and rejection table",
        "feature_evidence.csv": "Feature-level evidence by URL",
        "primary_url_acceptance.json": "Strict final URL gate outcome",
        "mandatory_url_delivery.json": "Delivery and review status",
        "source_selection.json": "Manufacturer-versus-retailer authority decision",
        "orchestrated_result.json": "Canonical machine-readable result",
        "review.md": "General human review pack",
        "single_product_diagnostics.xlsx": "Workbook of diagnostic tables",
    }
    return purposes.get(name, "Supporting artifact")


def _leading_identity(result: Mapping[str, Any], belief: Mapping[str, Any]) -> str:
    identification = result.get("product_identification")
    if isinstance(identification, Mapping):
        leading = (
            identification.get("leading_hypothesis")
            or identification.get("winning_hypothesis")
            or identification.get("identified_product")
        )
        if isinstance(leading, Mapping):
            return _text(
                leading.get("canonical_name")
                or leading.get("product_name")
                or leading.get("name")
                or leading.get("hypothesis_id")
            )
        if leading:
            return _text(leading)
    leading = belief.get("leading_hypothesis") if isinstance(belief, Mapping) else None
    if isinstance(leading, Mapping):
        return _text(
            leading.get("canonical_name")
            or leading.get("product_name")
            or leading.get("name")
            or leading.get("hypothesis_id")
        )
    product = result.get("product") if isinstance(result.get("product"), Mapping) else {}
    return _text(product.get("main_text"), "Unresolved product")


def _build_mindmap(
    *,
    result: Mapping[str, Any],
    belief: Mapping[str, Any],
    search_steps_df: pd.DataFrame,
    candidates_df: pd.DataFrame,
    business_steps_df: pd.DataFrame,
    visual_summary: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    product = result.get("product") if isinstance(result.get("product"), Mapping) else {}
    source_selection = result.get("source_selection") if isinstance(result.get("source_selection"), Mapping) else {}
    acceptance = result.get("primary_url_acceptance") if isinstance(result.get("primary_url_acceptance"), Mapping) else {}
    delivery = result.get("url_delivery") if isinstance(result.get("url_delivery"), Mapping) else {}

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    def add(node_id: str, label: str, group: str, depth: int, order: float, parent: str | None = None) -> None:
        nodes.append(
            {
                "node_id": node_id,
                "label": label,
                "group": group,
                "depth": depth,
                "order": order,
            }
        )
        if parent:
            edges.append({"source": parent, "target": node_id})

    add(
        "root",
        "Product URL decision\n" + _leading_identity(result, belief),
        "root",
        0,
        0,
    )
    add(
        "input",
        "Input\n"
        f"MAIN_TEXT: {_text(product.get('main_text'), '—')}\n"
        f"EAN: {_text(product.get('ean'), 'not supplied')}\n"
        f"Country: {_text(product.get('country_code'), '—')}\n"
        f"Retailer: {_text(product.get('retailer_name'), 'not supplied')}",
        "input",
        1,
        0,
        "root",
    )
    add(
        "identity",
        "Product interpretation\n"
        f"Resolved identity: {_leading_identity(result, belief)}\n"
        f"Status: {_text((result.get('product_identification') or {}).get('resolution_status'), 'reported in artifact')}",
        "identity",
        1,
        1,
        "root",
    )
    route = " → ".join(
        _text(
            row.get("name")
            or row.get("market_stage")
            or row.get("stage"),
            f"credit {index + 1}",
        )
        for index, row in search_steps_df.to_dict(orient="records")
    ) or "manufacturer_primary → country/retailer → global_fallback"
    add(
        "search",
        "Search route\n" + route,
        "search",
        1,
        2,
        "root",
    )
    add(
        "validation",
        "Candidate validation\n"
        f"Candidate rows: {len(candidates_df)}\n"
        f"Exact identity, browser, feature, scrapability and durability gates",
        "validation",
        1,
        3,
        "root",
    )
    add(
        "visual",
        "Multimodal evidence\n"
        f"Visual assets: {visual_summary.get('visual_assets_collected', 0)}\n"
        f"Screenshots: {visual_summary.get('screenshots_captured', 0)}\n"
        f"Impact: {_text(visual_summary.get('image_influenced_final_decision'), 'not recorded')}",
        "visual",
        1,
        4,
        "root",
    )
    add(
        "authority",
        "Source authority\n"
        f"Role: {_text(result.get('primary_url_role'), '—')}\n"
        f"Reason: {_text(source_selection.get('selection_reason'), '—')}",
        "authority",
        1,
        5,
        "root",
    )
    add(
        "outcome",
        "Final outcome\n"
        f"Status: {_text(result.get('job_status'), '—')}\n"
        f"Accepted: {acceptance.get('accepted')}\n"
        f"Delivered: {delivery.get('delivered')}\n"
        f"URL: {_text(result.get('primary_url'), 'not delivered')}",
        "outcome",
        1,
        6,
        "root",
    )
    add(
        "judgments",
        f"Observable business judgments\n{len(business_steps_df)} recorded steps",
        "judgments",
        1,
        7,
        "root",
    )

    for index, row in enumerate(business_steps_df.head(18).to_dict(orient="records"), start=1):
        stage = _text(row.get("decision_stage"), f"STEP_{index}")
        judgment = _text(row.get("agent_judgement"), "No judgment text")
        rule = _text(row.get("business_rule_applied"), "")
        label = f"{index}. {stage}\n{judgment}"
        if rule:
            label += f"\nRule: {rule}"
        add(f"judgment_{index}", label, "judgment_step", 2, index, "judgments")

    return pd.DataFrame(nodes), pd.DataFrame(edges)


def build_artifact_diagnostics(path: str | Path) -> ArtifactDiagnostics:
    artifact_dir = resolve_artifact_dir(path)
    result = _read_json(artifact_dir / "orchestrated_result.json")
    belief = _read_json(artifact_dir / "product_belief.json")
    source_selection = _read_json(artifact_dir / "source_selection.json")
    acceptance = _read_json(artifact_dir / "primary_url_acceptance.json")
    delivery = _read_json(artifact_dir / "mandatory_url_delivery.json")
    search_trace = _read_json(artifact_dir / "adaptive_search_trace.json")

    if source_selection and not result.get("source_selection"):
        result["source_selection"] = source_selection
    if acceptance and not result.get("primary_url_acceptance"):
        result["primary_url_acceptance"] = acceptance
    if delivery and not result.get("url_delivery"):
        result["url_delivery"] = delivery

    product = result.get("product") if isinstance(result.get("product"), Mapping) else {}
    judgement = result.get("business_judgement_review")
    judgement = judgement if isinstance(judgement, Mapping) else {}
    business_steps_df = pd.DataFrame(judgement.get("steps") or [])
    visual_summary = (
        judgement.get("visual_evidence_summary")
        if isinstance(judgement.get("visual_evidence_summary"), Mapping)
        else {}
    )
    visual_evidence_summary_df = pd.DataFrame([visual_summary])

    search_steps_df = _search_steps(result, search_trace)
    candidates_df = _candidate_frame(result, artifact_dir)
    feature_evidence_df = _read_csv(artifact_dir / "feature_evidence.csv")
    if feature_evidence_df.empty:
        feature_evidence_df = _flatten_feature_evidence(result)

    evidence_ledger_df = _read_jsonl(artifact_dir / "evidence_ledger.jsonl")
    if evidence_ledger_df.empty and isinstance(belief.get("evidence_ledger"), list):
        evidence_ledger_df = pd.DataFrame(belief.get("evidence_ledger"))

    snapshots = belief.get("snapshots") or belief.get("belief_updates") or []
    belief_updates_df = pd.DataFrame(snapshots)

    product_input_df = pd.DataFrame(
        [
            {
                "row_id": product.get("row_id"),
                "main_text": product.get("main_text"),
                "ean": product.get("ean"),
                "retailer_name": product.get("retailer_name"),
                "country_code": product.get("country_code"),
                "language_code": product.get("language_code"),
            }
        ]
    )
    source = result.get("source_selection") if isinstance(result.get("source_selection"), Mapping) else {}
    visual = dict(visual_summary)
    overview_df = pd.DataFrame(
        [
            {
                "artifact_dir": str(artifact_dir),
                "row_id": product.get("row_id"),
                "identified_product": _leading_identity(result, belief),
                "job_status": result.get("job_status"),
                "primary_url": result.get("primary_url"),
                "primary_url_role": result.get("primary_url_role"),
                "manufacturer_url": result.get("manufacturer_url"),
                "retailer_url": result.get("retailer_url"),
                "selection_reason": source.get("selection_reason"),
                "business_judgement_count": len(business_steps_df),
                "image_influenced_final_decision": visual.get("image_influenced_final_decision"),
                "visual_assets_collected": visual.get("visual_assets_collected"),
                "screenshots_captured": visual.get("screenshots_captured"),
                "candidate_rows": len(candidates_df),
                "feature_evidence_rows": len(feature_evidence_df),
                "evidence_ledger_rows": len(evidence_ledger_df),
            }
        ]
    )

    inventory_df = _artifact_inventory(artifact_dir)
    nodes_df, edges_df = _build_mindmap(
        result=result,
        belief=belief,
        search_steps_df=search_steps_df,
        candidates_df=candidates_df,
        business_steps_df=business_steps_df,
        visual_summary=visual,
    )

    return ArtifactDiagnostics(
        artifact_dir=artifact_dir,
        result=result,
        overview_df=overview_df,
        product_input_df=product_input_df,
        business_judgement_steps_df=business_steps_df,
        visual_evidence_summary_df=visual_evidence_summary_df,
        search_steps_df=search_steps_df,
        candidates_df=candidates_df,
        feature_evidence_df=feature_evidence_df,
        evidence_ledger_df=evidence_ledger_df,
        belief_updates_df=belief_updates_df,
        artifact_inventory_df=inventory_df,
        mindmap_nodes_df=nodes_df,
        mindmap_edges_df=edges_df,
    )


def _wrap(text: str, width: int) -> str:
    lines = []
    for raw in str(text).splitlines():
        wrapped = textwrap.wrap(raw, width=width) or [""]
        lines.extend(wrapped)
    return "\n".join(lines)


def plot_artifact_mindmap(
    diagnostics: ArtifactDiagnostics,
    *,
    figsize: tuple[float, float] = (22, 14),
    max_judgement_steps: int = 12,
):
    nodes = diagnostics.mindmap_nodes_df.copy()
    if nodes.empty:
        raise ValueError("No mindmap nodes were built from the artifact")

    allowed = {"root", "input", "identity", "search", "validation", "visual", "authority", "outcome", "judgments"}
    allowed.update(f"judgment_{index}" for index in range(1, max_judgement_steps + 1))
    nodes = nodes[nodes["node_id"].isin(allowed)].copy()
    edges = diagnostics.mindmap_edges_df[
        diagnostics.mindmap_edges_df["source"].isin(nodes["node_id"])
        & diagnostics.mindmap_edges_df["target"].isin(nodes["node_id"])
    ].copy()

    positions: dict[str, tuple[float, float]] = {"root": (0.5, 0.52)}
    primary = nodes[nodes["depth"] == 1].sort_values("order")
    count = max(len(primary), 1)
    for index, row in enumerate(primary.to_dict(orient="records")):
        angle = math.pi * (0.08 + 0.84 * index / max(count - 1, 1))
        radius_x, radius_y = 0.40, 0.38
        positions[row["node_id"]] = (
            0.5 + radius_x * math.cos(angle),
            0.52 + radius_y * math.sin(angle),
        )

    judgement_nodes = nodes[nodes["group"] == "judgment_step"].sort_values("order")
    if not judgement_nodes.empty:
        columns = 3
        for index, row in enumerate(judgement_nodes.to_dict(orient="records")):
            column = index % columns
            row_number = index // columns
            positions[row["node_id"]] = (
                0.15 + 0.35 * column,
                0.34 - 0.12 * row_number,
            )

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.45, 1)
    ax.axis("off")

    for edge in edges.to_dict(orient="records"):
        if edge["source"] not in positions or edge["target"] not in positions:
            continue
        x1, y1 = positions[edge["source"]]
        x2, y2 = positions[edge["target"]]
        arrow = FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.2,
            connectionstyle="arc3,rad=0.05",
        )
        ax.add_patch(arrow)

    for row in nodes.to_dict(orient="records"):
        node_id = row["node_id"]
        if node_id not in positions:
            continue
        x, y = positions[node_id]
        is_root = node_id == "root"
        is_step = row["group"] == "judgment_step"
        width = 0.28 if is_root else (0.28 if is_step else 0.23)
        height = 0.11 if is_root else (0.10 if is_step else 0.12)
        box = FancyBboxPatch(
            (x - width / 2, y - height / 2),
            width,
            height,
            boxstyle="round,pad=0.012",
            linewidth=1.4 if is_root else 1.0,
        )
        ax.add_patch(box)
        ax.text(
            x,
            y,
            _wrap(row["label"], 38 if is_step else 32),
            ha="center",
            va="center",
            fontsize=10 if is_root else (7.7 if is_step else 8.5),
        )

    title = diagnostics.overview_df.iloc[0].get("identified_product", "Artifact decision map")
    ax.set_title(
        f"Observable Agent Decision Mindmap — {title}\n"
        "Evidence → business rule → judgment → action → final URL",
        fontsize=16,
        pad=20,
    )
    return fig


def plot_business_judgement_timeline(
    diagnostics: ArtifactDiagnostics,
    *,
    max_steps: int = 20,
    figsize: tuple[float, float] | None = None,
):
    frame = diagnostics.business_judgement_steps_df.head(max_steps).copy()
    if frame.empty:
        raise ValueError("The artifact does not contain structured business judgment steps")

    count = len(frame)
    figsize = figsize or (18, max(7, count * 1.25))
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.5, count - 0.5)
    ax.axis("off")

    for index, row in enumerate(frame.to_dict(orient="records")):
        y = count - 1 - index
        ax.text(0.02, y, str(row.get("sequence_number") or index + 1), va="center", fontsize=11)
        stage = _text(row.get("decision_stage"), f"STEP_{index + 1}")
        question = _text(row.get("business_question"))
        judgment = _text(row.get("agent_judgement"))
        rule = _text(row.get("business_rule_applied"))
        action = _text(row.get("effect_on_next_action"))
        label = (
            f"{stage}\n"
            f"Question: {question}\n"
            f"Judgment: {judgment}\n"
            f"Rule: {rule}\n"
            f"Next action: {action}"
        )
        box = FancyBboxPatch(
            (0.08, y - 0.38),
            0.88,
            0.76,
            boxstyle="round,pad=0.012",
            linewidth=1.0,
        )
        ax.add_patch(box)
        ax.text(0.10, y, _wrap(label, 120), va="center", ha="left", fontsize=8.5)
        if index < count - 1:
            ax.add_patch(
                FancyArrowPatch(
                    (0.52, y - 0.39),
                    (0.52, y - 0.61),
                    arrowstyle="-|>",
                    mutation_scale=12,
                    linewidth=1.0,
                )
            )

    ax.set_title(
        "Chronological Observable Business Judgment Trace\n"
        "This is an audit of recorded evidence and actions, not hidden chain-of-thought.",
        fontsize=15,
        pad=18,
    )
    return fig


def _mermaid_escape(value: Any, limit: int = 180) -> str:
    text = " ".join(_text(value).split())
    text = text.replace('"', "'").replace("[", "(").replace("]", ")")
    return text[:limit]


def render_mermaid_decision_flow(diagnostics: ArtifactDiagnostics, *, max_steps: int = 20) -> str:
    lines = ["```mermaid", "flowchart TD"]
    lines.append('    INPUT["Submitted product input"]')
    frame = diagnostics.business_judgement_steps_df.head(max_steps)
    previous = "INPUT"
    for index, row in enumerate(frame.to_dict(orient="records"), start=1):
        node = f"J{index}"
        stage = _mermaid_escape(row.get("decision_stage"), 60)
        judgment = _mermaid_escape(row.get("agent_judgement"), 150)
        lines.append(f'    {node}["{index}. {stage}<br/>{judgment}"]')
        lines.append(f"    {previous} --> {node}")
        previous = node
    final_url = _mermaid_escape(diagnostics.result.get("primary_url"), 160)
    role = _mermaid_escape(diagnostics.result.get("primary_url_role"), 50)
    lines.append(f'    OUTCOME["Final URL<br/>{role}<br/>{final_url}"]')
    lines.append(f"    {previous} --> OUTCOME")
    lines.append("```")
    return "\n".join(lines)


def write_artifact_diagnostic_report(
    diagnostics: ArtifactDiagnostics,
    *,
    output_path: str | Path | None = None,
) -> Path:
    output = (
        Path(output_path).expanduser().resolve()
        if output_path
        else diagnostics.artifact_dir / "artifact_diagnostic_report.md"
    )
    overview = diagnostics.overview_df.iloc[0].to_dict()
    lines = [
        "# Product Artifact Diagnostic Report",
        "",
        "> Observable evidence, business rules, actions and conclusions reconstructed from the generated artifact. This report does not expose hidden chain-of-thought.",
        "",
        "## Executive conclusion",
        "",
        f"- **Row ID:** `{_text(overview.get('row_id'), 'unknown')}`",
        f"- **Identified product:** {_text(overview.get('identified_product'), 'unknown')}",
        f"- **Job status:** `{_text(overview.get('job_status'), 'unknown')}`",
        f"- **Primary role:** `{_text(overview.get('primary_url_role'), 'unknown')}`",
        f"- **Primary URL:** {_text(overview.get('primary_url'), 'not delivered')}",
        f"- **Selection reason:** {_text(overview.get('selection_reason'), 'not recorded')}",
        f"- **Visual evidence impact:** `{_text(overview.get('image_influenced_final_decision'), 'not recorded')}`",
        "",
        "## Decision mindmap",
        "",
        render_mermaid_decision_flow(diagnostics),
        "",
        "## Chronological business judgments",
        "",
    ]

    if diagnostics.business_judgement_steps_df.empty:
        lines.append("No structured business judgment steps were present.")
    else:
        columns = [
            column
            for column in (
                "sequence_number",
                "decision_stage",
                "business_question",
                "evidence_considered",
                "agent_judgement",
                "business_rule_applied",
                "effect_on_next_action",
                "visual_evidence_used",
                "confidence",
                "final_outcome",
            )
            if column in diagnostics.business_judgement_steps_df
        ]
        lines.append(_markdown_table(diagnostics.business_judgement_steps_df[columns], max_rows=50))

    lines.extend(["", "## Visual evidence summary", ""])
    lines.append(_markdown_table(diagnostics.visual_evidence_summary_df, max_rows=5))

    lines.extend(["", "## Search route", ""])
    if diagnostics.search_steps_df.empty:
        lines.append("No structured search stages were found.")
    else:
        lines.append(_markdown_table(diagnostics.search_steps_df, max_rows=20))

    lines.extend(["", "## Candidate decisions", ""])
    if diagnostics.candidates_df.empty:
        lines.append("No candidate table was found.")
    else:
        preferred = [
            column
            for column in (
                "url",
                "source_role",
                "source_tier_name",
                "validation_status",
                "identity_status",
                "identity_accepted",
                "coverage",
                "strict_selected",
                "review_selected",
                "decision_reasons",
                "rejection_reasons",
            )
            if column in diagnostics.candidates_df
        ]
        lines.append(
            _markdown_table(
                diagnostics.candidates_df[
                    preferred or list(diagnostics.candidates_df.columns[:10])
                ],
                max_rows=50,
            )
        )

    lines.extend(["", "## Artifact inventory", ""])
    lines.append(_markdown_table(diagnostics.artifact_inventory_df, max_rows=100))

    lines.extend(
        [
            "",
            "## Human review prompts",
            "",
            "1. Is the product interpretation identical to the human interpretation?",
            "2. Is the search order identical: manufacturer, local retailer/country, then global fallback?",
            "3. Were the same candidates accepted or rejected for the same reasons?",
            "4. Was image evidence used correctly and only where visibly supported?",
            "5. Would the human select the same primary URL and source role?",
            "6. What is the first divergent judgment step?",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")
    return output
