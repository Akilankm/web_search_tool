from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from src.product_evidence_harness.contracts import ActionType, CandidateScorecard, ProductSearchState
from src.product_evidence_harness.country_profiles import CountryProfileRegistry


@dataclass(frozen=True)
class ArtifactWriter:
    """Product-grade search/validation artifact writer.

    Default behavior is intentionally *not* CSV-dump-first. The row folder is a
    readable evidence packet:

    - final_row.csv: compact operational output for the product row.
    - markdown files: human/LLM-readable decision trace and evidence audit.
    - trace.json: compact machine replay summary.

    Detailed debug CSVs can still be enabled for engineering investigations.
    """

    root_dir: str | Path
    include_debug_json: bool = False
    write_markdown_reports: bool = True
    write_trace_json: bool = True
    write_debug_csvs: bool = False
    country_profiles: CountryProfileRegistry = field(default_factory=CountryProfileRegistry.load)

    def write_state(self, state: ProductSearchState) -> Path:
        product_dir = Path(self.root_dir) / self._safe(state.task.row_id)
        product_dir.mkdir(parents=True, exist_ok=True)

        # The only default row-level CSV: compact, submission-friendly, one row.
        self._write_csv(product_dir / "final_row.csv", [self.final_submission_row(state, product_dir=product_dir)])

        if self.write_markdown_reports:
            self._write_markdown_packet(product_dir, state)

        if self.write_trace_json:
            self._write_json(product_dir / "trace.json", self._compact_trace(state, product_dir=product_dir))

        if self.write_debug_csvs:
            self._write_debug_csvs(product_dir, state)

        if self.include_debug_json:
            self._write_json(product_dir / "debug_state.json", state.to_dict())
        return product_dir

    # ------------------------------------------------------------------
    # Public compact row helpers
    # ------------------------------------------------------------------
    def final_submission_row(self, state: ProductSearchState, *, product_dir: Path | None = None) -> dict[str, Any]:
        """Return the one-row business/submission output for a state."""
        m = state.final_result
        selected_language = self._selected_candidate_language(state)
        budget = state.budget.snapshot() if hasattr(state.budget, "snapshot") else None
        candidates = self._ranked_cards(state)
        candidate_urls = [c.candidate.url for c in candidates[:15]]
        selected_card = self._selected_card(state)
        selected_scrape = selected_card.scrape if selected_card else None
        product_dir = product_dir or (Path(self.root_dir) / self._safe(state.task.row_id))
        report_path = product_dir / "report.md"

        if not m:
            return {
                "row_id": state.task.row_id,
                "main_text": state.task.main_text,
                "country_code": state.task.country_code,
                "ean": state.task.ean,
                "retailer_name": state.task.retailer_name,
                "product_url": None,
                "verified_exact_url": None,
                "best_available_url": None,
                "best_reference_url": None,
                "url_decision_status": "UNRESOLVED",
                "needs_review": True,
                "confidence": 0.0,
                "candidate_urls": "|".join(candidate_urls),
                "candidate_count": len(state.candidates),
                "scraped_candidate_count": len(state.scrapes),
                "serp_calls_used": budget.organic_used if budget else 0,
                "llm_calls_used": len(state.llm_call_records),
                "scrape_calls_used": budget.scrape_used if budget else len(state.scrapes),
                "row_report_path": str(report_path),
            }

        return {
            "row_id": m.row_id,
            "main_text": m.main_text,
            "country_code": m.country_code,
            "ean": m.ean,
            "retailer_name": m.retailer_name,
            "product_url": m.product_url,
            "verified_exact_url": m.verified_exact_url,
            "best_available_url": m.best_available_url,
            "best_reference_url": m.best_reference_url,
            "url_decision_status": m.url_decision_status,
            "resolution_status": m.resolution_status,
            "selection_scope": m.selection_scope,
            "selected_domain": m.selected_domain,
            "selected_retailer_name": m.selected_retailer_name,
            "selected_language_code": selected_language.get("language_code"),
            "selected_language_name": selected_language.get("language_name"),
            "is_exact_product_match": m.is_exact_product_match,
            "is_scrapable": m.is_scrapable,
            "is_product_page": bool(selected_scrape and selected_scrape.looks_like_product_page),
            "needs_review": m.needs_review,
            "confidence": m.confidence,
            "validation_status": m.validation_status,
            "identity_status": m.identity_status,
            "exact_product_check": m.exact_product_check,
            "variant_check": m.variant_check,
            "variant_conflict_terms": "|".join(m.variant_conflict_terms),
            "ean_status": m.ean_status,
            "ean_check": m.ean_check,
            "page_gtins_valid": "|".join(m.page_gtins_valid),
            "input_validation_status": m.input_validation_status,
            "input_validation_warnings": "|".join(m.input_validation_warnings),
            "requested_retailer_attempted": m.requested_retailer_attempted,
            "requested_retailer_scrapability_status": m.requested_retailer_scrapability_status,
            "requested_retailer_escape_reason": m.requested_retailer_escape_reason,
            "selected_from_requested_retailer": m.selected_from_requested_retailer,
            "selected_from_other_country_retailer": m.selected_from_other_country_retailer,
            "selected_from_global_fallback": m.selected_from_global_fallback,
            "candidate_urls": "|".join(candidate_urls),
            "candidate_count": len(state.candidates),
            "scored_candidate_count": len(state.scorecards),
            "scraped_candidate_count": len(state.scrapes),
            "scrape_success_count": sum(1 for s in state.scrapes.values() if s.success),
            "product_detail_pages_found": sum(1 for s in state.scrapes.values() if s.looks_like_product_page),
            "serp_calls_used": budget.organic_used if budget else m.organic_calls_used,
            "ai_mode_calls_used": budget.ai_mode_used if budget else m.ai_mode_calls_used,
            "llm_calls_used": len(state.llm_call_records) or m.llm_calls_used,
            "scrape_calls_used": budget.scrape_used if budget else m.scrape_calls_used,
            "repair_cycles": sum(1 for p in state.llm_search_plans if p.stage == "search_feedback"),
            "global_fallback_used": m.selected_from_global_fallback or m.is_global_fallback,
            "llm_decision": m.llm_decision,
            "llm_confidence": m.llm_confidence,
            "llm_reject_reason": m.llm_reject_reason,
            "final_justification": m.justification or m.llm_justification or m.match_reason,
            "termination_reason": m.termination_reason or state.termination_reason,
            "row_report_path": str(report_path),
        }

    # ------------------------------------------------------------------
    # Markdown packet
    # ------------------------------------------------------------------
    def _write_markdown_packet(self, product_dir: Path, state: ProductSearchState) -> None:
        files = {
            "report.md": self._render_report(state),
            "search_plan.md": self._render_search_plan(state),
            "candidate_review.md": self._render_candidate_review(state),
            "scrape_evidence.md": self._render_scrape_evidence(state),
            "retailer_scrapability.md": self._render_retailer_scrapability(state),
            "final_decision.md": self._render_final_decision(state),
            "decision_trace.md": self._render_decision_trace(state),
        }
        for filename, content in files.items():
            (product_dir / filename).write_text(content.rstrip() + "\n", encoding="utf-8")

    def _render_report(self, state: ProductSearchState) -> str:
        final = state.final_result
        lines = [
            "# Product Discovery Report",
            "",
            "## 1. Input",
            f"- **Row ID:** `{state.task.row_id}`",
            f"- **Main text:** {self._md_text(state.task.main_text)}",
            f"- **Country:** `{state.task.country_code}`",
            f"- **Language:** `{state.task.language_code or ''}`",
            f"- **EAN / GTIN:** `{state.task.ean or ''}`",
            f"- **Requested retailer:** {self._md_text(state.task.retailer_name or '')}",
            f"- **Input warnings:** {self._md_text(', '.join(state.task.input_validation_warnings) or 'None')}",
            "",
            "## 2. Final Decision",
        ]
        lines.extend(self._final_decision_bullets(state))
        lines.extend([
            "",
            "## 3. Product Identity Understanding",
            self._identity_graph_markdown(state),
            "",
            "## 4. Search Execution Summary",
            self._budget_markdown(state),
            "",
            "## 5. Requested Retailer Scrapability Review",
            self._retailer_scrapability_summary_markdown(state),
            "",
            "## 6. Candidate Review",
            self._candidate_table_markdown(state, limit=15),
            "",
            "## 7. Key Scrape Evidence",
            self._scrape_summary_markdown(state, limit=8),
            "",
            "## 8. Detector and LLM Decision Summary",
            self._decision_summary_markdown(state),
            "",
            "## 9. Review Notes",
            self._review_notes(state),
        ])
        return "\n".join(lines)

    def _render_search_plan(self, state: ProductSearchState) -> str:
        lines = [
            "# Search Plan",
            "",
            "This file records the observable search strategy and repair decisions. It is a decision trace, not hidden chain-of-thought.",
            "",
            "## Product Identity",
            self._identity_graph_markdown(state),
            "",
            "## LLM / Deterministic Query Plans",
        ]
        plans = state.llm_search_plans
        if not plans:
            lines.append("No LLM search plan was recorded. The deterministic query builder/planner was used.")
        for plan in plans:
            lines.extend([
                f"### Plan: `{plan.stage}` / call `{plan.call_index}`",
                f"- **Success:** `{plan.success}`",
                f"- **Expanded product text:** {self._md_text(plan.expanded_main_text)}",
                f"- **Critical terms:** {self._md_text(', '.join(plan.critical_terms) or 'None')}",
                f"- **Variant terms to preserve:** {self._md_text(', '.join(plan.variant_terms_to_preserve) or 'None')}",
                f"- **Negative terms:** {self._md_text(', '.join(plan.negative_terms) or 'None')}",
                f"- **Plan summary:** {self._md_text(plan.reasoning or plan.error or '')}",
                "",
                "| # | Query | Scope | Source | Reason | Priority |",
                "|---:|---|---|---|---|---:|",
            ])
            if plan.queries:
                for idx, q in enumerate(plan.queries, start=1):
                    lines.append(f"| {idx} | {self._md_cell(q.query)} | `{q.scope}` | `{q.source}` | {self._md_cell(q.reason)} | {q.priority} |")
            else:
                lines.append("| - | No query emitted | - | - | - | - |")
            lines.append("")
        lines.extend([
            "## Executed Queries",
            "",
            "| # | Iteration | Scope | Loop phase | Language | Query | Success |",
            "|---:|---:|---|---|---|---|---|",
        ])
        qrows = self._query_rows(state)
        for idx, row in enumerate(qrows, start=1):
            if not row.get("query"):
                continue
            language = row.get("language_code") or ""
            lines.append(
                f"| {idx} | {row.get('iteration') or ''} | `{row.get('scope') or ''}` | `{row.get('loop_phase') or ''}` | `{language}` | {self._md_cell(row.get('query') or '')} | `{row.get('success')}` |"
            )
        return "\n".join(lines)

    def _render_candidate_review(self, state: ProductSearchState) -> str:
        lines = [
            "# Candidate Review",
            "",
            "## Selected Candidate",
        ]
        selected = self._selected_card(state)
        if selected:
            lines.extend(self._candidate_detail_markdown(state, selected, rank=self._card_rank(state, selected)))
        else:
            lines.append("No selected candidate was available.")
        lines.extend([
            "",
            "## Ranked Candidate Table",
            self._candidate_table_markdown(state, limit=50),
            "",
            "## Rejection Summary",
            self._rejection_summary_markdown(state),
        ])
        return "\n".join(lines)

    def _render_scrape_evidence(self, state: ProductSearchState) -> str:
        lines = [
            "# Scrape Evidence",
            "",
            "crawl4ai output is treated as observable evidence. SerpAPI URLs are candidates only until this evidence exists.",
            "",
            self._scrape_summary_markdown(state, limit=999),
        ]
        return "\n".join(lines)

    def _render_retailer_scrapability(self, state: ProductSearchState) -> str:
        return "\n".join([
            "# Requested Retailer Scrapability Review",
            "",
            self._retailer_scrapability_summary_markdown(state),
            "",
            "## Requested-Retailer Candidates",
            self._requested_retailer_candidates_markdown(state),
        ])

    def _render_final_decision(self, state: ProductSearchState) -> str:
        lines = ["# Final Decision", ""]
        lines.extend(self._final_decision_bullets(state))
        lines.extend([
            "",
            "## Evidence Supporting Selection",
            self._selected_evidence_markdown(state),
            "",
            "## Why Other URLs Were Rejected",
            self._rejection_summary_markdown(state),
        ])
        return "\n".join(lines)

    def _render_decision_trace(self, state: ProductSearchState) -> str:
        lines = [
            "# Agent Decision Trace",
            "",
            "This is an observable execution trace: actions, evidence, decisions, and conclusions. It is not hidden chain-of-thought.",
            "",
            "| Iteration | Action | Scope | Phase | Query / URL | Result |",
            "|---:|---|---|---|---|---|",
        ]
        for record in state.actions_taken:
            action = record.action
            query_or_url = action.query or action.url or ""
            summary = self._summarize_output(record.output_summary)
            lines.append(
                f"| {record.iteration} | `{action.action_type.value}` | `{action.metadata.get('scope', '')}` | `{action.metadata.get('loop_phase', '')}` | {self._md_cell(query_or_url)} | {self._md_cell(summary or record.error or '')} |"
            )
        if not state.actions_taken:
            lines.append("| - | No actions recorded | - | - | - | - |")
        lines.extend(["", "## Termination", f"- **Reason:** `{state.termination_reason or ''}`"])
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Markdown section helpers
    # ------------------------------------------------------------------
    def _final_decision_bullets(self, state: ProductSearchState) -> list[str]:
        m = state.final_result
        if not m:
            return ["- **Status:** `UNRESOLVED`", "- **Product URL:** None"]
        return [
            f"- **Product URL:** {self._md_link(m.product_url)}",
            f"- **Verified exact URL:** {self._md_link(m.verified_exact_url)}",
            f"- **Best available URL:** {self._md_link(m.best_available_url)}",
            f"- **Best reference URL:** {self._md_link(m.best_reference_url)}",
            f"- **Decision status:** `{m.url_decision_status}`",
            f"- **Selection scope:** `{m.selection_scope}`",
            f"- **Selected domain:** `{m.selected_domain}`",
            f"- **Selected retailer:** {self._md_text(m.selected_retailer_name)}",
            f"- **Exact product match:** `{m.is_exact_product_match}`",
            f"- **Scrapable:** `{m.is_scrapable}`",
            f"- **Needs review:** `{m.needs_review}`",
            f"- **Confidence:** `{m.confidence:.3f}`",
            f"- **LLM decision:** `{m.llm_decision}` / confidence `{m.llm_confidence:.3f}`",
            f"- **Final justification:** {self._md_text(m.justification or m.llm_justification or m.match_reason)}",
        ]

    def _identity_graph_markdown(self, state: ProductSearchState) -> str:
        graph = state.identity_graph.to_dict() if hasattr(state.identity_graph, "to_dict") else {}
        fields = [
            ("Normalized text", graph.get("normalized_main_text")),
            ("Expanded product names", ", ".join(graph.get("expanded_product_name_candidates", []) or [])),
            ("Must-match terms", ", ".join(graph.get("must_match_terms", []) or [])),
            ("Variant terms", ", ".join(graph.get("variant_terms", []) or [])),
            ("Size terms", ", ".join(graph.get("size_terms", []) or [])),
            ("Color terms", ", ".join(graph.get("color_terms", []) or [])),
            ("Quantity terms", ", ".join(graph.get("quantity_terms", []) or [])),
            ("Product form terms", ", ".join(graph.get("product_form_terms", []) or [])),
            ("Product form families", ", ".join(graph.get("product_form_families", []) or [])),
            ("Input EAN", graph.get("input_ean") or state.task.ean),
        ]
        return "\n".join(f"- **{name}:** {self._md_text(value or 'None')}" for name, value in fields)

    def _budget_markdown(self, state: ProductSearchState) -> str:
        rs = self._run_summary(state)
        return "\n".join([
            f"- **SerpAPI organic calls:** `{rs['search_iterations']}`",
            f"- **AI mode calls:** `{rs.get('ai_mode_calls_used', 0)}`",
            f"- **LLM calls:** `{rs['llm_calls_used']}`",
            f"- **Candidates discovered:** `{rs['candidate_count']}`",
            f"- **Candidates scraped:** `{rs['scrape_count']}`",
            f"- **Scrape iterations:** `{rs['scrape_iterations']}`",
            f"- **Product detail pages found:** `{sum(1 for s in state.scrapes.values() if s.looks_like_product_page)}`",
            f"- **Repair cycles:** `{rs['repair_cycles']}`",
            f"- **Country searches:** `{rs['country_search_iterations']}`",
            f"- **Global searches:** `{rs['global_search_iterations']}`",
            f"- **Termination reason:** `{rs['termination_reason']}`",
        ])

    def _retailer_scrapability_summary_markdown(self, state: ProductSearchState) -> str:
        m = state.final_result
        if not m:
            return "No final retailer scrapability summary is available."
        return "\n".join([
            f"- **Requested retailer:** {self._md_text(m.requested_retailer_name or state.task.retailer_name or '')}",
            f"- **Attempted:** `{m.requested_retailer_attempted}`",
            f"- **Domains found:** {self._md_text(', '.join(m.requested_retailer_domains_found) or 'None')}",
            f"- **Candidates found:** `{m.requested_retailer_candidates_found}`",
            f"- **Candidates scraped:** `{m.requested_retailer_candidates_scraped}`",
            f"- **Scrape successes:** `{m.requested_retailer_scrape_success_count}`",
            f"- **Rich pages:** `{m.requested_retailer_rich_pages_count}`",
            f"- **Exact candidates:** `{m.requested_retailer_exact_candidates_count}`",
            f"- **Retailer scrapability status:** `{m.requested_retailer_scrapability_status}`",
            f"- **Escape reason:** {self._md_text(m.requested_retailer_escape_reason or 'None')}",
            f"- **Selected from requested retailer:** `{m.selected_from_requested_retailer}`",
            f"- **Selected from same-country alternative retailer:** `{m.selected_from_other_country_retailer}`",
            f"- **Selected from global fallback:** `{m.selected_from_global_fallback}`",
        ])

    def _candidate_table_markdown(self, state: ProductSearchState, *, limit: int) -> str:
        cards = self._ranked_cards(state)[:limit]
        lines = [
            "| Rank | Candidate ID | Scope | URL | Scraped | Product page | Exactness | Variant | Confidence | Decision / reject reason |",
            "|---:|---|---|---|---|---|---|---|---:|---|",
        ]
        if not cards:
            lines.append("| - | - | - | No candidates | - | - | - | - | - | - |")
            return "\n".join(lines)
        for idx, card in enumerate(cards, start=1):
            s = card.scrape
            v = card.verification
            scope = self._candidate_scope(state, card)
            exactness = v.exact_product_check if v else card.exact_product_check or "UNKNOWN"
            variant = v.variant_check if v else card.variant_check or "UNKNOWN"
            reason = card.primary_reject_reason or card.llm_reject_reason or "; ".join(card.hard_failures) or "selected/usable candidate"
            lines.append(
                f"| {idx} | `CAND-{idx:03d}` | `{scope}` | {self._md_link(card.candidate.url)} | `{bool(s and s.is_scrapable)}` | `{bool(s and s.looks_like_product_page)}` | `{exactness}` | `{variant}` | {card.final_confidence:.3f} | {self._md_cell(reason)} |"
            )
        return "\n".join(lines)

    def _scrape_summary_markdown(self, state: ProductSearchState, *, limit: int) -> str:
        cards = [c for c in self._ranked_cards(state) if c.scrape]
        if not cards:
            return "No scrape evidence was recorded."
        lines: list[str] = []
        for idx, card in enumerate(cards[:limit], start=1):
            s = card.scrape
            v = card.verification
            lines.extend([
                f"## CAND-{self._card_rank(state, card):03d}: {self._md_link(card.candidate.url)}",
                "",
                "### Page Access",
                f"- **Final URL:** {self._md_link(s.final_url)}",
                f"- **Status code:** `{s.status_code}`",
                f"- **Scraped:** `{s.scraped}`",
                f"- **Success:** `{s.success}`",
                f"- **Reachable:** `{s.reachable}`",
                f"- **Scrapable:** `{s.is_scrapable}`",
                f"- **Word count:** `{s.word_count}`",
                f"- **Richness score:** `{s.richness_score:.3f}`",
                f"- **Looks like product page:** `{s.looks_like_product_page}`",
                "",
                "### Extracted Product Evidence",
                f"- **Title:** {self._md_text(s.title)}",
                f"- **H1:** {self._md_text(s.h1)}",
                f"- **Product name:** {self._md_text(s.page_product_name)}",
                f"- **Brand:** {self._md_text(s.brand)}",
                f"- **Manufacturer:** {self._md_text(s.manufacturer)}",
                f"- **Price / currency:** {self._md_text(str(s.price or ''))} {self._md_text(s.currency)}",
                f"- **Availability:** {self._md_text(s.availability)}",
                f"- **Structured EANs:** {self._md_text(', '.join(s.structured_eans) or 'None')}",
                f"- **Image count:** `{s.image_count}`",
                f"- **Spec count:** `{len(s.specs)}`",
                "",
                "### Verification",
                f"- **Identity:** `{v.identity_status if v else 'UNVERIFIED'}`",
                f"- **Exact product check:** `{v.exact_product_check if v else 'UNKNOWN'}`",
                f"- **Variant check:** `{v.variant_check if v else 'UNKNOWN'}`",
                f"- **EAN status:** `{v.ean_status if v else 'UNKNOWN'}`",
                f"- **Blocking reasons:** {self._md_text(', '.join(v.blocking_reasons) if v else 'None')}",
                "",
            ])
        return "\n".join(lines)

    def _decision_summary_markdown(self, state: ProductSearchState) -> str:
        lines = [
            "### Detector Findings",
            f"- **Detector finding count:** `{sum(len(x) for x in state.detector_findings.values())}`",
            f"- **Hard blocker count:** `{sum(1 for findings in state.detector_findings.values() for f in findings if f.get('severity') == 'HARD_BLOCKER')}`",
            "",
            "### LLM Calls",
            "| Call | URL | Payload | Image used | Success | Decision | Error |",
            "|---:|---|---|---|---|---|---|",
        ]
        if state.llm_call_records:
            for r in state.llm_call_records:
                lines.append(f"| {r.call_index} | {self._md_link(r.url)} | `{r.payload_level}` | `{r.image_used}` | `{r.success}` | `{r.decision}` | {self._md_cell(r.error or '')} |")
        else:
            lines.append("| - | - | - | - | - | No LLM calls recorded | - |")
        return "\n".join(lines)

    def _review_notes(self, state: ProductSearchState) -> str:
        m = state.final_result
        if not m:
            return "- No final result was produced. Human review required."
        notes = []
        if m.needs_review:
            notes.append("- Final decision requires human review because exact proof was incomplete or the selected URL is not fully verified.")
        if m.best_reference_url and not m.product_url:
            notes.append("- Only a reference/rejected URL was available; it was not promoted to `product_url`.")
        if m.requested_retailer_escape_reason:
            notes.append(f"- Requested retailer escape reason: {self._md_text(m.requested_retailer_escape_reason)}")
        if m.variant_conflict_terms:
            notes.append(f"- Variant conflicts observed: {self._md_text(', '.join(m.variant_conflict_terms))}")
        return "\n".join(notes or ["- No manual review notes."])

    def _candidate_detail_markdown(self, state: ProductSearchState, card: CandidateScorecard, *, rank: int) -> list[str]:
        s = card.scrape
        v = card.verification
        return [
            f"- **Candidate ID:** `CAND-{rank:03d}`",
            f"- **URL:** {self._md_link(card.candidate.url)}",
            f"- **Domain:** `{card.candidate.domain}`",
            f"- **Scope:** `{self._candidate_scope(state, card)}`",
            f"- **Title:** {self._md_text(card.candidate.title)}",
            f"- **Confidence:** `{card.final_confidence:.3f}`",
            f"- **Validation status:** `{card.validation_status}`",
            f"- **Identity status:** `{v.identity_status if v else 'UNVERIFIED'}`",
            f"- **Exact product check:** `{v.exact_product_check if v else 'UNKNOWN'}`",
            f"- **Variant check:** `{v.variant_check if v else 'UNKNOWN'}`",
            f"- **Scrapable:** `{bool(s and s.is_scrapable)}`",
            f"- **Richness score:** `{s.richness_score if s else 0:.3f}`",
            f"- **Decision reason:** {self._md_text(card.primary_reject_reason or card.llm_justification or 'Selected / best-ranked candidate')}",
        ]

    def _rejection_summary_markdown(self, state: ProductSearchState) -> str:
        cards = self._ranked_cards(state)
        rejected = [c for c in cards if c.primary_reject_reason or c.hard_failures or (c.verification and c.verification.blocking_reasons)]
        if not rejected:
            return "No explicit rejected candidates were recorded."
        lines = ["| Candidate | URL | Reason |", "|---|---|---|"]
        for card in rejected[:30]:
            rank = self._card_rank(state, card)
            v = card.verification
            reason = card.primary_reject_reason or "; ".join(card.hard_failures) or (", ".join(v.blocking_reasons) if v else "")
            lines.append(f"| `CAND-{rank:03d}` | {self._md_link(card.candidate.url)} | {self._md_cell(reason)} |")
        return "\n".join(lines)

    def _selected_evidence_markdown(self, state: ProductSearchState) -> str:
        card = self._selected_card(state)
        if not card:
            return "No selected evidence card was available."
        lines = self._candidate_detail_markdown(state, card, rank=self._card_rank(state, card))
        if card.scrape:
            s = card.scrape
            lines.extend([
                f"- **Page title:** {self._md_text(s.title)}",
                f"- **Page product name:** {self._md_text(s.page_product_name)}",
                f"- **Structured EANs:** {self._md_text(', '.join(s.structured_eans) or 'None')}",
                f"- **Price/currency:** {self._md_text(str(s.price or ''))} {self._md_text(s.currency)}",
            ])
        return "\n".join(lines)

    def _requested_retailer_candidates_markdown(self, state: ProductSearchState) -> str:
        cards = [c for c in self._ranked_cards(state) if c.retailer_check == "MATCHED"]
        if not cards:
            return "No requested-retailer candidates were found or the retailer was not provided."
        lines = ["| Candidate | URL | Scraped | Richness | Exactness | Decision |", "|---|---|---|---:|---|---|"]
        for card in cards[:30]:
            rank = self._card_rank(state, card)
            s = card.scrape
            v = card.verification
            lines.append(
                f"| `CAND-{rank:03d}` | {self._md_link(card.candidate.url)} | `{bool(s and s.is_scrapable)}` | {(s.richness_score if s else 0):.3f} | `{v.exact_product_check if v else 'UNKNOWN'}` | {self._md_cell(card.primary_reject_reason or card.validation_status)} |"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Compact JSON trace
    # ------------------------------------------------------------------
    def _compact_trace(self, state: ProductSearchState, *, product_dir: Path | None = None) -> dict[str, Any]:
        return {
            "input": state.task.to_dict(),
            "final_submission_row": self.final_submission_row(state, product_dir=product_dir),
            "run_summary": self._run_summary(state),
            "identity_graph": state.identity_graph.to_dict() if hasattr(state.identity_graph, "to_dict") else state.identity_graph,
            "actions": [r.to_dict() for r in state.actions_taken],
            "search_plans": [p.to_dict() for p in state.llm_search_plans],
            "candidates": [self._candidate_trace_row(state, card, rank) for rank, card in enumerate(self._ranked_cards(state), start=1)],
            "llm_judgements": {url: j.to_dict() for url, j in state.llm_judgements.items()},
        }

    def _candidate_trace_row(self, state: ProductSearchState, card: CandidateScorecard, rank: int) -> dict[str, Any]:
        s = card.scrape
        v = card.verification
        return {
            "candidate_id": f"CAND-{rank:03d}",
            "rank": rank,
            "url": card.candidate.url,
            "domain": card.candidate.domain,
            "scope": self._candidate_scope(state, card),
            "title": card.candidate.title,
            "source_types": list(card.candidate.source_types),
            "query_sources": list(card.candidate.query_sources),
            "confidence": card.final_confidence,
            "validation_status": card.validation_status,
            "primary_reject_reason": card.primary_reject_reason,
            "scrape": None if not s else {
                "success": s.success,
                "is_scrapable": s.is_scrapable,
                "looks_like_product_page": s.looks_like_product_page,
                "status_code": s.status_code,
                "final_url": s.final_url,
                "title": s.title,
                "page_product_name": s.page_product_name,
                "structured_eans": list(s.structured_eans),
                "richness_score": s.richness_score,
                "word_count": s.word_count,
                "image_count": s.image_count,
                "specs_count": len(s.specs),
                "error": s.error,
            },
            "verification": None if not v else {
                "identity_status": v.identity_status,
                "exact_product_check": v.exact_product_check,
                "variant_check": v.variant_check,
                "variant_conflict_terms": list(v.variant_conflict_terms),
                "ean_status": v.ean_status,
                "page_gtins_valid": list(v.page_gtins_valid),
                "blocking_reasons": list(v.blocking_reasons),
            },
        }

    # ------------------------------------------------------------------
    # Optional detailed debug CSVs. These are intentionally disabled by default.
    # ------------------------------------------------------------------
    def _write_debug_csvs(self, product_dir: Path, state: ProductSearchState) -> None:
        debug_dir = product_dir / "debug_csv"
        debug_dir.mkdir(exist_ok=True)
        self._write_csv(debug_dir / "best_url.csv", [self._best_row(state)])
        self._write_csv(debug_dir / "summary.csv", [self._summary_row(state)])
        self._write_csv(debug_dir / "candidates.csv", [self._candidate_row(state, c, idx) for idx, c in enumerate(state.scorecards, start=1)])
        self._write_csv(debug_dir / "scrapes.csv", [self._scrape_row(url, s) for url, s in state.scrapes.items()])
        self._write_csv(debug_dir / "actions.csv", [self._action_row(a) for a in state.actions_taken])
        self._write_csv(debug_dir / "queries.csv", self._query_rows(state))
        self._write_csv(debug_dir / "search_plan.csv", self._search_plan_rows(state, stage="initial_search_plan"))
        self._write_csv(debug_dir / "search_feedback.csv", self._search_plan_rows(state, stage="search_feedback"))
        self._write_csv(debug_dir / "language_profile.csv", self._language_profile_rows(state))
        self._write_csv(debug_dir / "llm_judgements.csv", self._llm_judgement_rows(state))
        self._write_csv(debug_dir / "llm_calls.csv", self._llm_call_rows(state))
        self._write_csv(debug_dir / "detector_findings.csv", self._detector_finding_rows(state))
        self._write_csv(debug_dir / "evidence_scorecards.csv", self._evidence_scorecard_rows(state))
        self._write_csv(debug_dir / "identity_graph.csv", [self._identity_graph_row(state)])
        self._write_json(debug_dir / "run_summary.json", self._run_summary(state))

    # Original CSV row helpers kept for debug_csv mode.
    def _best_row(self, state: ProductSearchState) -> dict[str, Any]:
        m = state.final_result
        if not m:
            return {"row_id": state.task.row_id, "resolution_status": "UNRESOLVED", "product_url": None}
        selected_language = self._selected_candidate_language(state)
        data = m.to_dict()
        # Normalize tuple fields into pipe-delimited strings for CSV readability.
        for key, value in list(data.items()):
            if isinstance(value, tuple):
                data[key] = "|".join(str(x) for x in value)
            elif isinstance(value, dict):
                data[key] = json.dumps(value, ensure_ascii=False, default=str)
        data.update({
            "selected_language_code": selected_language.get("language_code"),
            "selected_language_name": selected_language.get("language_name"),
            "selected_language_priority": selected_language.get("language_priority"),
            "selected_language_distribution_weight": selected_language.get("language_distribution_weight"),
        })
        return data

    def _summary_row(self, state: ProductSearchState) -> dict[str, Any]:
        final = state.final_result
        return {
            "row_id": state.task.row_id,
            "main_text": state.task.main_text,
            "country_code": state.task.country_code,
            "country_name": self.country_profiles.get(state.task.country_code).country_name,
            "language_code": state.task.language_code,
            "country_language_order": "|".join(lp.language_code for lp in self.country_profiles.language_profiles_for(state.task.country_code, state.task.language_code)),
            "ean": state.task.ean,
            "retailer_name": state.task.retailer_name,
            "resolution_status": final.resolution_status if final else "UNRESOLVED",
            "url_decision_status": final.url_decision_status if final else "UNRESOLVED",
            "product_url": final.product_url if final else None,
            "candidate_count": len(state.candidates),
            "scorecard_count": len(state.scorecards),
            "scrape_count": len(state.scrapes),
            "scrapable_count": sum(1 for s in state.scrapes.values() if s.is_scrapable),
            "verified_count": sum(1 for c in state.scorecards if c.verification and c.verification.identity_status == "VERIFIED"),
            "organic_calls_used": state.budget.snapshot().organic_used,
            "ai_mode_calls_used": state.budget.snapshot().ai_mode_used,
            "scrape_calls_used": state.budget.snapshot().scrape_used,
            "llm_calls_used": len(state.llm_call_records),
            "termination_reason": state.termination_reason,
        }

    def _candidate_row(self, state: ProductSearchState, card: CandidateScorecard, rank: int) -> dict[str, Any]:
        c = card.candidate
        s = card.scrape
        v = card.verification
        final_url = state.final_result.product_url if state.final_result else None
        lang = self._candidate_language_info(state, c)
        country_specific = self.country_profiles.domain_matches_country(c.url, state.task.country_code)
        return {
            "rank": rank,
            "row_id": state.task.row_id,
            "selected_best": bool(final_url and c.url == final_url),
            "url": c.url,
            "domain": c.domain,
            "country_specific_candidate": country_specific,
            "language_code": lang.get("language_code"),
            "language_name": lang.get("language_name"),
            "title": c.title,
            "source_types": "|".join(c.source_types),
            "query_sources": "|".join(c.query_sources),
            "best_position": c.best_position,
            "organic_count": c.organic_count,
            "ai_reference_count": c.ai_reference_count,
            "country_check": card.country_check,
            "retailer_check": card.retailer_check,
            "requested_retailer_candidate": bool(state.task.retailer_name and card.retailer_check == "MATCHED"),
            "candidate_lifecycle_status": c.lifecycle_status,
            "validation_status": card.validation_status,
            "identity_status": v.identity_status if v else "UNVERIFIED",
            "exact_product_check": v.exact_product_check if v else "UNKNOWN",
            "variant_check": v.variant_check if v else "UNKNOWN",
            "variant_conflict_terms": "|".join(v.variant_conflict_terms) if v else "",
            "identity_driver": v.identity_driver if v else "UNKNOWN",
            "primary_reject_reason": card.primary_reject_reason,
            "llm_decision": card.llm_decision,
            "llm_confidence": card.llm_confidence,
            "confidence": card.final_confidence,
            "weighted_confidence": card.weighted_confidence,
            "confidence_cap": card.confidence_cap,
            "ean_score": card.ean_score,
            "title_score": card.title_score,
            "country_score": card.country_score,
            "scrape_score": card.scrape_score,
            "identity_score": card.identity_score,
            "richness_score": card.richness_score,
            "scraped": bool(s and s.scraped),
            "scrape_success": bool(s and s.success),
            "reachable": bool(s and s.reachable),
            "is_scrapable": bool(s and s.is_scrapable),
            "looks_like_product_page": bool(s and s.looks_like_product_page),
            "status_code": s.status_code if s else None,
            "word_count": s.word_count if s else 0,
            "ean_check": v.ean_check if v else "UNKNOWN",
            "ean_status": v.ean_status if v else "UNKNOWN",
            "page_gtins_valid": "|".join(v.page_gtins_valid) if v else "",
            "title_check": v.title_check if v else "UNKNOWN",
            "quantity_check": v.quantity_check if v else "UNKNOWN",
            "page_type_check": v.page_type_check if v else "UNKNOWN",
            "hard_failures": "; ".join(card.hard_failures),
            "soft_warnings": "; ".join(card.soft_warnings),
            "ranking_reasons": " | ".join(card.ranking_reasons),
        }

    def _scrape_row(self, url: str, s) -> dict[str, Any]:
        return {
            "url": url,
            "final_url": s.final_url,
            "scraped": s.scraped,
            "success": s.success,
            "reachable": s.reachable,
            "is_scrapable": s.is_scrapable,
            "status_code": s.status_code,
            "looks_like_product_page": s.looks_like_product_page,
            "looks_like_homepage": s.looks_like_homepage,
            "is_soft_404": s.is_soft_404,
            "title": s.title,
            "h1": s.h1,
            "page_product_name": s.page_product_name,
            "brand": s.brand,
            "manufacturer": s.manufacturer,
            "has_price": s.has_price,
            "currency": s.currency,
            "availability": s.availability,
            "structured_eans": "|".join(s.structured_eans),
            "word_count": s.word_count,
            "markdown_chars": s.markdown_chars,
            "image_count": s.image_count,
            "richness_score": s.richness_score,
            "error": s.error,
        }

    def _action_row(self, record) -> dict[str, Any]:
        return {
            "iteration": record.iteration,
            "action_type": record.action.action_type.value,
            "reason": record.action.reason,
            "scope": record.action.metadata.get("scope"),
            "kind": record.action.metadata.get("kind"),
            "loop_phase": record.action.metadata.get("loop_phase"),
            "language_code": record.action.metadata.get("language_code"),
            "query": record.action.query,
            "url": record.action.url,
            "success": record.success,
            "output_summary": json.dumps(record.output_summary, ensure_ascii=False, default=str),
            "error": record.error,
        }

    def _language_profile_rows(self, state: ProductSearchState) -> list[dict[str, Any]]:
        profile = self.country_profiles.get(state.task.country_code)
        rows = profile.to_language_rows()
        for row in rows:
            row["active_requested_language"] = state.task.language_code
            row["search_order"] = "|".join(lp.language_code for lp in profile.language_profiles_for(state.task.language_code))
        return rows

    def _search_plan_rows(self, state: ProductSearchState, *, stage: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for plan in state.llm_search_plans:
            if plan.stage != stage:
                continue
            if not plan.queries:
                rows.append({
                    "row_id": plan.row_id,
                    "llm_call_index": plan.call_index,
                    "stage": plan.stage,
                    "success": plan.success,
                    "expanded_main_text": plan.expanded_main_text,
                    "critical_terms": "|".join(plan.critical_terms),
                    "variant_terms_to_preserve": "|".join(plan.variant_terms_to_preserve),
                    "negative_terms": "|".join(plan.negative_terms),
                    "query": None,
                    "reasoning": plan.reasoning,
                    "error": plan.error,
                })
            for idx, q in enumerate(plan.queries, start=1):
                rows.append({
                    "row_id": plan.row_id,
                    "llm_call_index": plan.call_index,
                    "stage": plan.stage,
                    "success": plan.success,
                    "query_index": idx,
                    "query": q.query,
                    "query_source": q.source,
                    "scope": q.scope,
                    "reason": q.reason,
                    "priority": q.priority,
                    "must_include_ean": q.must_include_ean,
                    "expanded_main_text": plan.expanded_main_text,
                    "critical_terms": "|".join(plan.critical_terms),
                    "variant_terms_to_preserve": "|".join(plan.variant_terms_to_preserve),
                    "negative_terms": "|".join(plan.negative_terms),
                    "reasoning": plan.reasoning,
                    "error": plan.error,
                })
        if not rows:
            return [{"row_id": state.task.row_id, "stage": stage, "note": "no LLM search plan/feedback recorded"}]
        return rows

    def _query_rows(self, state: ProductSearchState) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        query_index = 0
        for record in state.actions_taken:
            if not record.action.query:
                continue
            query_index += 1
            rows.append({
                "query_index": query_index,
                "iteration": record.iteration,
                "action_type": record.action.action_type.value,
                "scope": record.action.metadata.get("scope"),
                "kind": record.action.metadata.get("kind"),
                "loop_phase": record.action.metadata.get("loop_phase"),
                "repair_reason": record.action.metadata.get("reason"),
                "language_code": record.action.metadata.get("language_code"),
                "language_name": record.action.metadata.get("language_name"),
                "language_priority": record.action.metadata.get("language_priority"),
                "language_distribution_weight": record.action.metadata.get("language_distribution_weight"),
                "success": record.success,
                "query": record.action.query,
            })
        if not rows:
            return [{"query_index": None, "query": None}]
        return rows

    def _candidate_language_info(self, state: ProductSearchState, card_or_candidate) -> dict[str, Any]:
        candidate = getattr(card_or_candidate, "candidate", card_or_candidate)
        query_sources = set(getattr(candidate, "query_sources", ()) or ())
        for record in state.actions_taken:
            if record.action.action_type != ActionType.ORGANIC_SEARCH:
                continue
            if record.action.query and record.action.query in query_sources:
                return {
                    "language_code": record.action.metadata.get("language_code"),
                    "language_name": record.action.metadata.get("language_name"),
                    "language_priority": record.action.metadata.get("language_priority"),
                    "language_distribution_weight": record.action.metadata.get("language_distribution_weight"),
                }
        return {}

    def _selected_candidate_language(self, state: ProductSearchState) -> dict[str, Any]:
        final = state.final_result.product_url if state.final_result else None
        if not final:
            return {}
        for card in state.scorecards:
            if card.candidate.url == final:
                return self._candidate_language_info(state, card.candidate)
        return {}

    def _llm_judgement_rows(self, state: ProductSearchState) -> list[dict[str, Any]]:
        if not state.llm_judgements and not state.llm_call_records:
            return [{"row_id": state.task.row_id, "llm_used": False, "note": "LLM adjudication disabled or no promising candidates"}]
        rows: list[dict[str, Any]] = []
        for url, j in state.llm_judgements.items():
            rows.append(j.to_dict())
        return rows or [{"row_id": state.task.row_id, "llm_used": False}]

    def _llm_call_rows(self, state: ProductSearchState) -> list[dict[str, Any]]:
        return [r.to_dict() for r in state.llm_call_records]

    def _identity_graph_row(self, state: ProductSearchState) -> dict[str, Any]:
        graph = state.identity_graph.to_dict() if hasattr(state.identity_graph, "to_dict") else {}
        return {
            "row_id": state.task.row_id,
            "raw_main_text": graph.get("raw_main_text", state.task.main_text),
            "normalized_main_text": graph.get("normalized_main_text"),
            "expanded_product_name_candidates": "|".join(graph.get("expanded_product_name_candidates", []) or []),
            "must_match_terms": "|".join(graph.get("must_match_terms", []) or []),
            "variant_terms": "|".join(graph.get("variant_terms", []) or []),
            "size_terms": "|".join(graph.get("size_terms", []) or []),
            "color_terms": "|".join(graph.get("color_terms", []) or []),
            "quantity_terms": "|".join(graph.get("quantity_terms", []) or []),
            "product_form_terms": "|".join(graph.get("product_form_terms", []) or []),
            "product_form_families": "|".join(graph.get("product_form_families", []) or []),
            "input_ean": graph.get("input_ean"),
            "input_validation_status": "WARN" if state.task.input_validation_warnings else "OK",
            "input_validation_warnings": "|".join(state.task.input_validation_warnings),
            "country_code": graph.get("country_code", state.task.country_code),
        }

    def _detector_finding_rows(self, state: ProductSearchState) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for url, findings in state.detector_findings.items():
            for idx, finding in enumerate(findings, start=1):
                rows.append({
                    "row_id": state.task.row_id,
                    "url": url,
                    "finding_index": idx,
                    "detector": finding.get("detector"),
                    "status": finding.get("status"),
                    "severity": finding.get("severity"),
                    "input_value": finding.get("input_value"),
                    "page_value": finding.get("page_value"),
                    "explanation": finding.get("explanation"),
                })
        return rows

    def _evidence_scorecard_rows(self, state: ProductSearchState) -> list[dict[str, Any]]:
        rows = []
        for rank, card in enumerate(self._ranked_cards(state), start=1):
            s = card.scrape
            v = card.verification
            rows.append({
                "row_id": state.task.row_id,
                "rank": rank,
                "url": card.candidate.url,
                "organic_score": card.organic_score,
                "ai_score": card.ai_score,
                "retailer_score": card.retailer_score,
                "country_score": card.country_score,
                "ean_score": card.ean_score,
                "title_score": card.title_score,
                "product_page_score": card.product_page_score,
                "scrape_score": card.scrape_score,
                "identity_score": card.identity_score,
                "richness_score": card.richness_score,
                "weighted_confidence": card.weighted_confidence,
                "confidence_cap": card.confidence_cap,
                "final_confidence": card.final_confidence,
                "validation_status": card.validation_status,
                "identity_status": v.identity_status if v else "UNVERIFIED",
                "exact_product_check": v.exact_product_check if v else "UNKNOWN",
                "variant_check": v.variant_check if v else "UNKNOWN",
                "scrapable": bool(s and s.is_scrapable),
                "product_page": bool(s and s.looks_like_product_page),
                "word_count": s.word_count if s else 0,
                "specs_count": len(s.specs) if s else 0,
                "image_count": s.image_count if s else 0,
                "hard_failures": "; ".join(card.hard_failures),
                "soft_warnings": "; ".join(card.soft_warnings),
            })
        return rows

    # ------------------------------------------------------------------
    # Summaries and formatting
    # ------------------------------------------------------------------
    def _run_summary(self, state: ProductSearchState) -> dict[str, Any]:
        final = state.final_result
        budget = state.budget.snapshot() if hasattr(state.budget, "snapshot") else None
        return {
            "row_id": state.task.row_id,
            "main_text": state.task.main_text,
            "country_code": state.task.country_code,
            "product_url": final.product_url if final else None,
            "verified_exact_url": final.verified_exact_url if final else None,
            "best_available_url": final.best_available_url if final else None,
            "best_reference_url": final.best_reference_url if final else None,
            "url_decision_status": final.url_decision_status if final else "UNRESOLVED",
            "requested_retailer_scrapability_status": final.requested_retailer_scrapability_status if final else "",
            "requested_retailer_escape_reason": final.requested_retailer_escape_reason if final else "",
            "selection_scope": final.selection_scope if final else "",
            "input_validation_warnings": list(state.task.input_validation_warnings),
            "needs_review": final.needs_review if final else True,
            "candidate_count": len(state.candidates),
            "scrape_count": len(state.scrapes),
            "scrape_success_count": sum(1 for s in state.scrapes.values() if s.success),
            "llm_calls_used": len(state.llm_call_records),
            "organic_calls_used": budget.organic_used if budget else 0,
            "ai_mode_calls_used": budget.ai_mode_used if budget else 0,
            "scrape_calls_used": budget.scrape_used if budget else len(state.scrapes),
            "loop_iterations": state.iteration,
            "search_iterations": sum(1 for a in state.actions_taken if a.action.action_type == ActionType.ORGANIC_SEARCH),
            "scrape_iterations": sum(1 for a in state.actions_taken if a.action.action_type == ActionType.SCRAPE_URL),
            "judge_iterations": sum(1 for a in state.actions_taken if a.action.action_type == ActionType.LLM_EXACT_ADJUDICATION),
            "repair_cycles": sum(1 for p in state.llm_search_plans if p.stage == "search_feedback"),
            "country_search_iterations": sum(1 for a in state.actions_taken if a.action.action_type == ActionType.ORGANIC_SEARCH and a.action.metadata.get("scope") != "global"),
            "global_search_iterations": sum(1 for a in state.actions_taken if a.action.action_type == ActionType.ORGANIC_SEARCH and a.action.metadata.get("scope") == "global"),
            "detector_finding_count": sum(len(x) for x in state.detector_findings.values()),
            "hard_conflict_count": sum(1 for findings in state.detector_findings.values() for f in findings if f.get("status") == "CONFLICT" and f.get("severity") == "HARD_BLOCKER"),
            "termination_reason": state.termination_reason,
        }

    def _ranked_cards(self, state: ProductSearchState) -> list[CandidateScorecard]:
        return list(state.scorecards)

    def _selected_card(self, state: ProductSearchState) -> CandidateScorecard | None:
        if not state.final_result:
            return None
        urls = [state.final_result.product_url, state.final_result.verified_exact_url, state.final_result.best_available_url, state.final_result.best_reference_url]
        for url in urls:
            if not url:
                continue
            for card in state.scorecards:
                if card.candidate.url == url:
                    return card
        return None

    def _card_rank(self, state: ProductSearchState, card: CandidateScorecard) -> int:
        try:
            return self._ranked_cards(state).index(card) + 1
        except ValueError:
            return 0

    def _candidate_scope(self, state: ProductSearchState, card: CandidateScorecard) -> str:
        if card.is_global_fallback or any("global" == str(q).lower() for q in card.candidate.query_sources):
            return "GLOBAL_FALLBACK"
        if state.task.retailer_name and card.retailer_check == "MATCHED":
            return "REQUESTED_RETAILER"
        if card.country_check == "MATCHED" or self.country_profiles.domain_matches_country(card.candidate.url, state.task.country_code):
            return "COUNTRY_ALTERNATIVE"
        return "UNKNOWN_SCOPE"

    def _summarize_output(self, summary: dict[str, Any]) -> str:
        if not summary:
            return ""
        priority_keys = ["result_count", "candidate_count", "url", "status", "decision", "selected", "reason"]
        parts = []
        for key in priority_keys:
            if key in summary:
                parts.append(f"{key}={summary[key]}")
        return "; ".join(parts) or json.dumps(summary, ensure_ascii=False, default=str)[:240]

    def _write_csv(self, path: Path, rows: Iterable[dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _write_json(self, path: Path, obj: Any) -> None:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _safe(self, value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:120]

    def _md_text(self, value: Any) -> str:
        text = "" if value is None else str(value)
        return text.replace("\n", " ").strip() or "None"

    def _md_cell(self, value: Any) -> str:
        text = self._md_text(value).replace("|", "\\|")
        return text[:500]

    def _md_link(self, url: Any) -> str:
        if not url:
            return "None"
        text = str(url)
        label = urlparse(text).netloc or text
        return f"[{self._md_cell(label)}]({text})"
