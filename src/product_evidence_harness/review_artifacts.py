from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.product_evidence_harness.contracts import CandidateScorecard, ProductSearchState
from src.product_evidence_harness.review_safety import card_for_url, is_safe_review_candidate


@dataclass(frozen=True)
class ReviewArtifactWriter:
    """Write the small, reviewer-first artifact layer.

    This is intentionally concise. Deep traces can still exist for engineering,
    but reviewers should start from these files:

    - review_summary.md: what was selected/rejected, why, and how the decision was made.
    - review_decision.json: compact machine-readable summary for notebooks/UI.
    - candidate_decisions.csv: top candidate outcomes in one table.
    """

    candidate_limit: int = 10

    def write_state(self, product_dir: str | Path, state: ProductSearchState) -> None:
        product_dir = Path(product_dir)
        product_dir.mkdir(parents=True, exist_ok=True)
        payload = self.decision_payload(state)
        self._write_markdown(product_dir / "review_summary.md", self.render_markdown(state, payload))
        self._write_json(product_dir / "review_decision.json", payload)
        self._write_csv(product_dir / "candidate_decisions.csv", payload["candidate_decisions"])

    def decision_payload(self, state: ProductSearchState) -> dict[str, Any]:
        final = state.final_result
        selected = self._selected_card(state)
        tournament = getattr(state, "tournament_result", None)
        confirmation = getattr(tournament, "champion_confirmation", None) if tournament else None
        budget = state.budget.snapshot() if hasattr(state.budget, "snapshot") else None
        best_review_url = final.best_available_url if final and selected and final.best_available_url else None

        decision = {
            "row_id": state.task.row_id,
            "main_text": state.task.main_text,
            "country_code": state.task.country_code,
            "retailer_name": state.task.retailer_name,
            "ean": state.task.ean,
            "decision": self._decision_label(state),
            "selected_url": final.product_url if final else None,
            "verified_exact_url": final.verified_exact_url if final else None,
            "best_review_url": best_review_url,
            "needs_review": bool(final.needs_review) if final else True,
            "confidence": round(float(final.confidence), 4) if final else 0.0,
            "status": final.url_decision_status if final else "UNRESOLVED",
            "identity_status": final.identity_status if final else "UNVERIFIED",
            "validation_status": final.validation_status if final else "UNRESOLVED",
            "selected_domain": final.selected_domain if final and selected else "",
            "selection_scope": final.selection_scope if final and selected else "unresolved",
        }

        checks = {
            "browser_or_page_access": bool(selected and selected.scrape and selected.scrape.reachable),
            "scrapable": bool(selected and selected.scrape and selected.scrape.is_scrapable),
            "looks_like_product_page": bool(selected and selected.scrape and selected.scrape.looks_like_product_page),
            "exact_product_match": bool(final and final.is_exact_product_match),
            "country_check": selected.country_check if selected else getattr(final, "country_check", "UNKNOWN") if final else "UNKNOWN",
            "retailer_check": selected.retailer_check if selected else getattr(final, "retailer_check", "UNKNOWN") if final else "UNKNOWN",
            "champion_confirmation_passed": bool(confirmation and confirmation.passed),
        }

        why = self._why_summary(state, selected)
        how = self._how_summary(state, tournament, budget)
        ai = self._ai_summary(state)
        evidence = self._selected_evidence(selected)
        rejected = self._rejected_summary(state, selected)

        return {
            "schema_version": "concise_review_decision/v2",
            "decision": decision,
            "checks": checks,
            "what_selected": self._what_selected(state, selected),
            "why_selected": why,
            "how_decided": how,
            "ai_reasoning_summary": ai,
            "selected_evidence": evidence,
            "rejection_summary": rejected,
            "candidate_decisions": self._candidate_rows(state, selected),
            "review_instruction": self._review_instruction(final, selected),
        }

    def render_markdown(self, state: ProductSearchState, payload: dict[str, Any]) -> str:
        d = payload["decision"]
        checks = payload["checks"]
        lines = [
            "# Review Summary",
            "",
            "This is the reviewer-first artifact. It is intentionally concise and decision-oriented.",
            "Deep trace/debug files should be opened only when this summary is insufficient.",
            "",
            "## 1. What was decided?",
            "",
            f"| Field | Value |",
            "|---|---|",
            f"| Decision | `{d['decision']}` |",
            f"| Selected URL | {self._link(d.get('selected_url'))} |",
            f"| Best review URL | {self._link(d.get('best_review_url'))} |",
            f"| Status | `{d.get('status')}` |",
            f"| Needs review | `{d.get('needs_review')}` |",
            f"| Confidence | `{d.get('confidence')}` |",
            f"| Selected domain | `{d.get('selected_domain')}` |",
            "",
            "## 2. Why was this decision made?",
            "",
        ]
        lines.extend(f"- {x}" for x in payload["why_selected"])
        lines.extend([
            "",
            "## 3. How was the decision made?",
            "",
        ])
        lines.extend(f"- {x}" for x in payload["how_decided"])
        lines.extend([
            "",
            "## 4. Gate checks",
            "",
            "| Check | Result |",
            "|---|---|",
        ])
        for key, value in checks.items():
            lines.append(f"| {key} | `{value}` |")
        lines.extend([
            "",
            "## 5. AI / model reasoning summary",
            "",
        ])
        lines.extend(f"- {x}" for x in payload["ai_reasoning_summary"])
        lines.extend([
            "",
            "## 6. Selected / safe review evidence",
            "",
            "| Evidence | Value |",
            "|---|---|",
        ])
        for key, value in payload["selected_evidence"].items():
            lines.append(f"| {key} | {self._text(value)} |")
        lines.extend([
            "",
            "## 7. What was rejected and why?",
            "",
            "| URL | Decision | Reason |",
            "|---|---|---|",
        ])
        for row in payload["candidate_decisions"][: self.candidate_limit]:
            if row.get("selected"):
                continue
            lines.append(f"| {self._link(row.get('url'))} | `{row.get('decision')}` | {self._text(row.get('reason'))} |")
        if all(row.get("selected") for row in payload["candidate_decisions"][: self.candidate_limit]):
            lines.append("| - | - | No rejected candidate in top review set. |")
        lines.extend([
            "",
            "## 8. Review instruction",
            "",
            payload["review_instruction"],
            "",
            "## 9. Related concise files",
            "",
            "| File | Use |",
            "|---|---|",
            "| `final_row.csv` | Operational one-row output. |",
            "| `review_decision.json` | Same decision summary in machine-readable form. |",
            "| `candidate_decisions.csv` | Top candidate accept/reject table. |",
            "| `product_coding_input.json` | Downstream product-coding evidence when available. |",
        ])
        return "\n".join(lines).rstrip() + "\n"

    def _decision_label(self, state: ProductSearchState) -> str:
        final = state.final_result
        selected = self._selected_card(state)
        if not final:
            return "UNRESOLVED_REVIEW_REQUIRED"
        if final.product_url and not final.needs_review and selected:
            return "ACCEPT_PRODUCTION_URL"
        if final.best_available_url and selected:
            return "REVIEW_SAFE_AVAILABLE_URL"
        return "UNRESOLVED_REVIEW_REQUIRED"

    def _what_selected(self, state: ProductSearchState, selected: CandidateScorecard | None) -> dict[str, Any]:
        final = state.final_result
        return {
            "selected_url": final.product_url if final and selected else None,
            "review_url": final.best_available_url if final and selected else None,
            "candidate_rank": self._rank(state, selected) if selected else None,
            "domain": selected.candidate.domain if selected else "",
            "title": selected.candidate.title if selected else "",
        }

    def _why_summary(self, state: ProductSearchState, selected: CandidateScorecard | None) -> list[str]:
        final = state.final_result
        if not final:
            return ["No final URL was selected; manual review is required."]
        points: list[str] = []
        if final.product_url and not final.needs_review and selected:
            points.append("Selected URL passed the final production handoff gates.")
        elif final.best_available_url and selected:
            points.append("No production-ready URL was confirmed; a safe review URL was retained for manual review only.")
        else:
            points.append("No production-ready URL and no safe review URL were confirmed; rejected candidates remain visible only in the candidate table.")
        if selected:
            points.append(f"Candidate score/confidence was `{selected.final_confidence:.3f}` with status `{selected.validation_status}`.")
            if selected.primary_reject_reason:
                points.append(f"Primary rejection/limitation noted: `{selected.primary_reject_reason}`.")
            if selected.hard_failures:
                points.append("Hard failures observed: " + "; ".join(selected.hard_failures[:3]) + ".")
        justification = final.justification or final.llm_justification or final.match_reason
        if justification:
            points.append("Final justification: " + self._short(justification, 280))
        return points or ["Decision was based on available ranking, scrape, identity, and validation signals."]

    def _how_summary(self, state: ProductSearchState, tournament: Any, budget: Any) -> list[str]:
        points = [
            f"Discovered `{len(state.candidates)}` candidate URL(s).",
            f"Scored `{len(state.scorecards)}` candidate(s).",
            f"Scraped `{len(state.scrapes)}` candidate page(s).",
        ]
        if budget:
            points.append(f"Used search=`{getattr(budget, 'organic_used', 0)}`, AI-mode=`{getattr(budget, 'ai_mode_used', 0)}`, scrape=`{getattr(budget, 'scrape_used', 0)}` calls.")
        if tournament:
            points.append(f"Tournament used `{tournament.search_credits_used}` search credit(s), considered `{tournament.preflight_candidate_count}` preflight candidate(s), and scraped `{tournament.scraped_candidate_count}` candidate(s).")
            points.append(f"Champion status: `{tournament.champion_status}`; champion URL: `{tournament.champion_url or 'None'}`.")
            if tournament.runner_up_url:
                points.append(f"Runner-up was `{tournament.runner_up_url}` with margin `{tournament.champion_margin}`.")
        if state.termination_reason:
            points.append(f"Run ended because `{state.termination_reason}`.")
        return points

    def _ai_summary(self, state: ProductSearchState) -> list[str]:
        points: list[str] = []
        if state.llm_search_plans:
            for plan in state.llm_search_plans[:2]:
                reason = plan.reasoning or plan.error or "No plan reason recorded."
                points.append(f"Search plan `{plan.stage}` used critical terms `{', '.join(plan.critical_terms) or 'None'}`; summary: {self._short(reason, 220)}")
        if state.llm_call_records:
            for call in state.llm_call_records[:3]:
                decision = call.decision or "NO_DECISION"
                points.append(f"LLM call `{call.call_index}` decision=`{decision}`, success=`{call.success}`, image_used=`{call.image_used}`.")
        if not points:
            points.append("No LLM reasoning call was recorded for this run; decision used deterministic search, scrape, ranking, and validation signals.")
        points.append("This section records observable model/planner outputs only; it is not hidden chain-of-thought.")
        return points

    def _selected_evidence(self, selected: CandidateScorecard | None) -> dict[str, Any]:
        if not selected:
            return {"selected_candidate": "None", "note": "No production-ready or safe review candidate was selected."}
        scrape = selected.scrape
        verification = selected.verification
        return {
            "url": selected.candidate.url,
            "domain": selected.candidate.domain or self._domain(selected.candidate.url),
            "title": selected.candidate.title,
            "scrape_success": bool(scrape and scrape.success),
            "scrapable": bool(scrape and scrape.is_scrapable),
            "product_page": bool(scrape and scrape.looks_like_product_page),
            "page_title": scrape.title if scrape else "",
            "product_name": scrape.page_product_name if scrape else "",
            "brand": scrape.brand if scrape else "",
            "manufacturer": scrape.manufacturer if scrape else "",
            "structured_eans": ", ".join(scrape.structured_eans) if scrape else "",
            "word_count": scrape.word_count if scrape else 0,
            "richness_score": round(scrape.richness_score, 4) if scrape else 0.0,
            "identity_status": verification.identity_status if verification else "UNVERIFIED",
            "exact_product_check": verification.exact_product_check if verification else "UNKNOWN",
            "variant_check": verification.variant_check if verification else "UNKNOWN",
            "ean_check": verification.ean_check if verification else "UNKNOWN",
        }

    def _rejected_summary(self, state: ProductSearchState, selected: CandidateScorecard | None) -> dict[str, Any]:
        rows = self._candidate_rows(state, selected)
        rejected = [r for r in rows if not r.get("selected")]
        return {
            "reviewed_candidate_count": len(rows),
            "rejected_in_review_set": len(rejected),
            "top_reject_reasons": [r.get("reason") for r in rejected[:5]],
        }

    def _candidate_rows(self, state: ProductSearchState, selected: CandidateScorecard | None) -> list[dict[str, Any]]:
        cards = self._ranked_cards(state)[: self.candidate_limit]
        selected_url = selected.candidate.url if selected else None
        rows: list[dict[str, Any]] = []
        for rank, card in enumerate(cards, start=1):
            scrape = card.scrape
            verification = card.verification
            is_selected = bool(selected_url and card.candidate.url == selected_url)
            reason = self._candidate_reason(card, is_selected)
            if is_selected and state.final_result and state.final_result.product_url == card.candidate.url:
                decision = "SELECTED_PRODUCTION_URL"
            elif is_selected:
                decision = "SAFE_REVIEW_CANDIDATE"
            else:
                decision = "REJECTED_OR_NOT_PROMOTED"
            rows.append({
                "rank": rank,
                "selected": is_selected,
                "decision": decision,
                "url": card.candidate.url,
                "domain": card.candidate.domain or self._domain(card.candidate.url),
                "confidence": round(float(card.final_confidence), 4),
                "validation_status": card.validation_status,
                "identity_status": verification.identity_status if verification else "UNVERIFIED",
                "exact_product_check": verification.exact_product_check if verification else card.exact_product_check or "UNKNOWN",
                "variant_check": verification.variant_check if verification else card.variant_check or "UNKNOWN",
                "country_check": card.country_check,
                "retailer_check": card.retailer_check,
                "scrape_success": bool(scrape and scrape.success),
                "scrapable": bool(scrape and scrape.is_scrapable),
                "product_page": bool(scrape and scrape.looks_like_product_page),
                "reason": reason,
            })
        if not rows:
            rows.append({
                "rank": None,
                "selected": False,
                "decision": "NO_CANDIDATES",
                "url": "",
                "domain": "",
                "confidence": 0.0,
                "validation_status": "UNRESOLVED",
                "identity_status": "UNVERIFIED",
                "exact_product_check": "UNKNOWN",
                "variant_check": "UNKNOWN",
                "country_check": "UNKNOWN",
                "retailer_check": "UNKNOWN",
                "scrape_success": False,
                "scrapable": False,
                "product_page": False,
                "reason": "No candidates were available for review.",
            })
        return rows

    def _candidate_reason(self, card: CandidateScorecard, selected: bool) -> str:
        if selected:
            return "Promoted because it passed either production gates or the safe-review fallback gate."
        if card.primary_reject_reason:
            return card.primary_reject_reason
        if card.llm_reject_reason:
            return card.llm_reject_reason
        if card.hard_failures:
            return "; ".join(card.hard_failures[:3])
        if card.verification and card.verification.blocking_reasons:
            return "; ".join(card.verification.blocking_reasons[:3])
        if not (card.scrape and card.scrape.success):
            return "Not promoted because scrape evidence was missing or unsuccessful."
        if not is_safe_review_candidate(card):
            return "Not promoted because it failed the safe-review fallback gate."
        if card.exact_product_check not in {"EXACT", "MATCHED", "VERIFIED", "EXACT_MATCH"}:
            return f"Not promoted because exact product check was `{card.exact_product_check or 'UNKNOWN'}`."
        return "Not promoted because another candidate had stronger combined evidence."

    def _review_instruction(self, final: Any, selected: CandidateScorecard | None = None) -> str:
        if not final:
            return "Manual review required: no final result was produced."
        if final.product_url and not final.needs_review:
            return "Reviewer can accept this row for automated handoff unless business policy requires additional manual sampling."
        if final.best_available_url and selected:
            return "Manual review required: a safe review URL exists, but do not use it for automated handoff until a reviewer confirms it."
        return "Manual review required: no safe review URL was retained; inspect rejected candidates only as search diagnostics, not as product URLs."

    def _selected_card(self, state: ProductSearchState) -> CandidateScorecard | None:
        if not state.final_result:
            return None
        final = state.final_result
        for url in (final.product_url, final.verified_exact_url):
            card = card_for_url(state, url)
            if card:
                return card
        fallback = card_for_url(state, final.best_available_url)
        if fallback and is_safe_review_candidate(fallback):
            return fallback
        return None

    def _ranked_cards(self, state: ProductSearchState) -> list[CandidateScorecard]:
        return sorted(state.scorecards, key=lambda c: (c.final_confidence, c.weighted_confidence), reverse=True)

    def _rank(self, state: ProductSearchState, selected: CandidateScorecard | None) -> int | None:
        if not selected:
            return None
        for idx, card in enumerate(self._ranked_cards(state), start=1):
            if card.candidate.url == selected.candidate.url:
                return idx
        return None

    def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    def _write_markdown(self, path: Path, content: str) -> None:
        path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames: list[str] = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _link(self, value: Any) -> str:
        value = str(value or "")
        if not value:
            return "None"
        return f"[{value}]({value})"

    def _text(self, value: Any) -> str:
        text = str(value or "")
        return self._short(text.replace("\n", " "), 240) if text else "None"

    def _short(self, text: str, limit: int) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."

    def _domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""
