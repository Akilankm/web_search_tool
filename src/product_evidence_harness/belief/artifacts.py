from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import EvidencePolarity, ProductBeliefState


@dataclass(frozen=True)
class ProductBeliefArtifactWriter:
    """Write auditable product-understanding artifacts without hidden chain-of-thought."""

    def write(self, root: str | Path, state: ProductBeliefState) -> Path:
        output = Path(root)
        output.mkdir(parents=True, exist_ok=True)
        (output / "product_belief.json").write_text(json.dumps(state.to_dict(), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        (output / "product_understanding.md").write_text(self._understanding(state), encoding="utf-8")
        (output / "market_decision_path.md").write_text(self._market_path(state), encoding="utf-8")
        (output / "belief_updates.md").write_text(self._updates(state), encoding="utf-8")
        with (output / "evidence_ledger.jsonl").open("w", encoding="utf-8") as handle:
            for item in state.evidence_ledger:
                handle.write(json.dumps(item.to_dict(), ensure_ascii=False, default=str) + "\n")
        return output

    def _understanding(self, state: ProductBeliefState) -> str:
        leading = state.leading_hypothesis
        lines = [
            "# Product Understanding", "",
            "This is an auditable summary of facts, hypotheses, assumptions, and unresolved fields. It is not hidden chain-of-thought.", "",
            "## Input", f"- **MAIN_TEXT:** {state.raw_main_text}", f"- **Country:** `{state.country_code}`",
            f"- **Requested retailer:** {state.requested_retailer or 'Not provided'}", f"- **Interpretation source:** `{state.interpretation_source}`", "",
            "## Leading product hypothesis", f"- **Identity:** {leading.canonical_name if leading else 'Unresolved'}",
            f"- **Posterior probability:** `{leading.posterior_probability if leading else 0:.4f}`",
            f"- **Resolution status:** `{state.resolution_status.value}`", f"- **Posterior margin:** `{state.posterior_margin:.4f}`", "",
            "## Claims", "| Field | Value | Epistemic status | Confidence | Source tokens |", "|---|---|---|---:|---|",
        ]
        for claim in state.claims:
            value = json.dumps(claim.value, ensure_ascii=False, default=str).replace("|", "\\|")
            source = ", ".join(claim.source_tokens).replace("|", "\\|")
            lines.append(f"| `{claim.field}` | {value} | `{claim.status.value}` | {claim.confidence:.2f} | {source} |")
        lines.extend(["", "## Competing hypotheses", ""])
        for hypothesis in sorted(state.hypotheses, key=lambda item: item.posterior_probability, reverse=True):
            lines.extend([
                f"### {hypothesis.hypothesis_id} — {hypothesis.canonical_name}", f"- Category: `{hypothesis.category}`",
                f"- Product role: `{hypothesis.product_role}`", f"- Posterior: `{hypothesis.posterior_probability:.4f}`",
                f"- Assumptions: {', '.join(hypothesis.assumptions) or 'None'}",
                f"- Negative constraints: {', '.join(hypothesis.negative_constraints) or 'None'}", "",
            ])
        lines.extend(["## Decision-critical uncertainties", "| Field | Candidate values | Entropy | Impact | Priority |", "|---|---|---:|---:|---:|"])
        for uncertainty in state.uncertainties:
            values = "; ".join(uncertainty.candidate_values).replace("|", "\\|")
            lines.append(f"| `{uncertainty.field}` | {values} | {uncertainty.entropy:.2f} | {uncertainty.decision_impact:.2f} | {uncertainty.priority:.2f} |")
        lines.extend(["", "## Readiness metrics", f"- Parse coverage: `{state.parse_coverage:.4f}`", f"- Identity completeness: `{state.identity_completeness:.4f}`", f"- Ambiguity entropy: `{state.ambiguity_entropy:.4f}`", f"- Assumption burden: `{state.assumption_burden:.4f}`", f"- Search readiness: `{state.search_readiness:.4f}`", ""])
        return "\n".join(lines)

    def _market_path(self, state: ProductBeliefState) -> str:
        lines = ["# Market Decision Path", "", "The market route is immutable. Search stops early only when a browser-openable, information-rich exact-product URL passes the production gate.", ""]
        if state.requested_retailer:
            lines.extend(["1. **Requested retailer in the requested country**", "2. **Alternative retailer within the requested country**", "3. **Global fallback**"])
        else:
            lines.extend(["1. **Alternative retailer within the requested country**", "2. **Country diagnostic refinement when uncertainty remains**", "3. **Global fallback**"])
        lines.extend(["", f"Current/last market stage: `{state.current_market_stage or 'not_started'}`", "", "## Final URL usability contract", "- Opens directly in a normal browser.", "- Resolves to a product-detail page, not a search/category/interstitial page.", "- Contains sufficient title, description, specifications, imagery, or commerce evidence for human eyeballing.", "- Represents the winning product hypothesis without hard variant, model, pack, or identity conflict.", ""])
        return "\n".join(lines)

    def _updates(self, state: ProductBeliefState) -> str:
        lines = ["# Belief Updates", "", "Each row records an observable state transition after offline interpretation or external evidence. No hidden reasoning is included.", "", "| Sequence | Trigger | Leading hypothesis | Status | Margin | Evidence count | Probabilities |", "|---:|---|---|---|---:|---:|---|"]
        for snapshot in state.snapshots:
            probabilities = ", ".join(f"{key}={value:.4f}" for key, value in snapshot.probabilities.items())
            lines.append(f"| {snapshot.sequence} | {snapshot.trigger.replace('|', '/')[:180]} | `{snapshot.leading_hypothesis_id or ''}` | `{snapshot.resolution_status.value}` | {snapshot.posterior_margin:.4f} | {snapshot.evidence_count} | {probabilities} |")
        supports = sum(item.polarity == EvidencePolarity.SUPPORTS for item in state.evidence_ledger)
        conflicts = sum(item.polarity == EvidencePolarity.CONTRADICTS for item in state.evidence_ledger)
        lines.extend(["", f"Supporting evidence items: **{supports}**", f"Contradicting evidence items: **{conflicts}**", ""])
        return "\n".join(lines)
