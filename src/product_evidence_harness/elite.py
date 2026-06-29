from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from src.product_evidence_harness.contracts import CandidateScorecard, ProductSearchState
from src.product_evidence_harness.url_utils import domain_of


MARKETPLACE_HINTS = (
    "amazon.", "ebay.", "aliexpress.", "mercadolibre.", "marketplace", "allegro.", "bol.", "cdiscount.", "rakuten.",
)
AGGREGATOR_HINTS = (
    "heureka.", "idealo.", "pricespy", "pricecompare", "shopping.google", "kelkoo", "comparar", "comparison",
)
MANUFACTURER_HINTS = (
    "lego.", "mattel.", "hasbro.", "ravensburger.", "spinmaster.", "playmobil.", "pokemon.", "nintendo.",
)


@dataclass(frozen=True)
class ConfidenceBreakdown:
    identity_confidence: float
    scrapability_confidence: float
    country_confidence: float
    retailer_confidence: float
    variant_confidence: float
    source_consensus_score: float
    coding_readiness_confidence: float
    final_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodingReadiness:
    status: str
    score: float
    available_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    feature_hints: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnterpriseEvidenceAssessment:
    quality_tier: str
    quality_tier_reason: str
    failure_taxonomy: tuple[str, ...]
    confidence: ConfidenceBreakdown
    coding_readiness: CodingReadiness
    source_consensus_score: float
    supporting_urls: tuple[str, ...]
    evidence_graph: dict[str, Any]
    product_coding_input: dict[str, Any]
    review_feedback_template: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["confidence"] = self.confidence.to_dict()
        data["coding_readiness"] = self.coding_readiness.to_dict()
        return data

    def final_submission_extras(self) -> dict[str, Any]:
        return {
            "quality_tier": self.quality_tier,
            "quality_tier_reason": self.quality_tier_reason,
            "coding_readiness_status": self.coding_readiness.status,
            "coding_readiness_score": self.coding_readiness.score,
            "identity_confidence": self.confidence.identity_confidence,
            "scrapability_confidence": self.confidence.scrapability_confidence,
            "country_confidence": self.confidence.country_confidence,
            "retailer_confidence": self.confidence.retailer_confidence,
            "variant_confidence": self.confidence.variant_confidence,
            "source_consensus_score": self.source_consensus_score,
            "coding_readiness_confidence": self.confidence.coding_readiness_confidence,
            "failure_taxonomy": "|".join(self.failure_taxonomy),
            "supporting_urls": "|".join(self.supporting_urls),
            "coding_available_evidence": "|".join(self.coding_readiness.available_evidence),
            "coding_missing_evidence": "|".join(self.coding_readiness.missing_evidence),
        }


class EnterpriseEvidenceEngine:
    """Enterprise-grade evidence synthesis layer.

    This layer does not replace discovery, scraping, verification, ranking, or the
    final URL selector. It summarizes their observable outputs into a product
    evidence graph, decomposed confidence, quality tier, failure taxonomy, and a
    downstream product-coding handoff payload.
    """

    def assess(self, state: ProductSearchState) -> EnterpriseEvidenceAssessment:
        selected = self._selected_card(state)
        graph = self.evidence_graph(state)
        readiness = self.coding_readiness(state, selected)
        consensus = self.source_consensus_score(state)
        confidence = self.confidence_breakdown(state, selected, readiness, consensus)
        failures = self.failure_taxonomy(state, selected)
        quality_tier, quality_reason = self.quality_tier(state, selected, readiness, confidence, failures)
        supporting_urls = tuple(self.supporting_urls(state, selected))
        product_coding_input = self.product_coding_input(state, selected, readiness, confidence, quality_tier, supporting_urls)
        review_template = self.review_feedback_template(state, quality_tier, failures)
        return EnterpriseEvidenceAssessment(
            quality_tier=quality_tier,
            quality_tier_reason=quality_reason,
            failure_taxonomy=tuple(failures),
            confidence=confidence,
            coding_readiness=readiness,
            source_consensus_score=consensus,
            supporting_urls=supporting_urls,
            evidence_graph=graph,
            product_coding_input=product_coding_input,
            review_feedback_template=review_template,
        )

    def write_artifacts(self, state: ProductSearchState, product_dir: str | Path) -> EnterpriseEvidenceAssessment:
        product_dir = Path(product_dir)
        product_dir.mkdir(parents=True, exist_ok=True)
        assessment = self.assess(state)
        self._write_json(product_dir / "enterprise_assessment.json", assessment.to_dict())
        self._write_json(product_dir / "evidence_graph.json", assessment.evidence_graph)
        self._write_json(product_dir / "product_coding_input.json", assessment.product_coding_input)
        self._write_json(product_dir / "review_feedback_template.json", assessment.review_feedback_template)
        (product_dir / "quality_assessment.md").write_text(self.render_quality_markdown(state, assessment), encoding="utf-8")
        return assessment

    def evidence_graph(self, state: ProductSearchState) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        row_id = state.task.row_id
        input_node = f"input:{row_id}"
        nodes.append({
            "id": input_node,
            "type": "input_product",
            "label": state.task.main_text,
            "properties": state.task.to_dict(),
        })
        if state.identity_graph is not None:
            graph_dict = state.identity_graph.to_dict() if hasattr(state.identity_graph, "to_dict") else state.identity_graph
            nodes.append({"id": f"identity:{row_id}", "type": "identity_graph", "label": "normalized_identity", "properties": graph_dict})
            edges.append({"from": input_node, "to": f"identity:{row_id}", "relation": "normalized_into"})

        for rank, card in enumerate(state.scorecards, start=1):
            candidate = card.candidate
            url_id = f"url:{candidate.url}"
            nodes.append({
                "id": url_id,
                "type": "candidate_url",
                "label": candidate.url,
                "properties": {
                    "rank": rank,
                    "domain": domain_of(candidate.url),
                    "source_types": list(candidate.source_types),
                    "query_sources": list(candidate.query_sources),
                    "final_confidence": card.final_confidence,
                    "validation_status": card.validation_status,
                    "retailer_check": card.retailer_check,
                    "country_check": card.country_check,
                    "source_reliability": self.source_reliability(candidate.url, candidate.source_types),
                    "source_reliability_label": self.source_reliability_label(candidate.url, candidate.source_types),
                },
            })
            edges.append({"from": input_node, "to": url_id, "relation": "discovered_candidate"})
            if card.scrape:
                scrape_id = f"scrape:{candidate.url}"
                s = card.scrape
                nodes.append({
                    "id": scrape_id,
                    "type": "scrape_evidence",
                    "label": s.page_product_name or s.title or candidate.url,
                    "properties": {
                        "success": s.success,
                        "reachable": s.reachable,
                        "is_scrapable": s.is_scrapable,
                        "looks_like_product_page": s.looks_like_product_page,
                        "richness_score": s.richness_score,
                        "brand": s.brand,
                        "manufacturer": s.manufacturer,
                        "structured_eans": list(s.structured_eans),
                        "image_count": s.image_count,
                        "specs_count": len(s.specs),
                        "has_price": s.has_price,
                        "availability": s.availability,
                    },
                })
                edges.append({"from": url_id, "to": scrape_id, "relation": "scraped_into"})
            if card.verification:
                verification_id = f"verification:{candidate.url}"
                v = card.verification
                nodes.append({
                    "id": verification_id,
                    "type": "identity_verification",
                    "label": v.identity_status,
                    "properties": {
                        "identity_status": v.identity_status,
                        "ean_check": v.ean_check,
                        "title_check": v.title_check,
                        "quantity_check": v.quantity_check,
                        "variant_check": v.variant_check,
                        "exact_product_check": v.exact_product_check,
                        "blocking_reasons": list(v.blocking_reasons),
                        "matched_tokens": list(v.matched_tokens),
                        "missing_tokens": list(v.missing_tokens),
                    },
                })
                edges.append({"from": url_id, "to": verification_id, "relation": "verified_by_detectors"})
            if card.llm_judgement:
                llm_id = f"llm:{candidate.url}"
                j = card.llm_judgement
                nodes.append({
                    "id": llm_id,
                    "type": "llm_adjudication",
                    "label": j.decision,
                    "properties": {
                        "decision": j.decision,
                        "exact_product_match": j.exact_product_match,
                        "confidence": j.confidence,
                        "reject_reason": j.reject_reason,
                        "scrape_usable": j.scrape_usable,
                        "image_used": j.image_used,
                    },
                })
                edges.append({"from": url_id, "to": llm_id, "relation": "adjudicated_by_llm"})

        return {
            "row_id": row_id,
            "graph_version": "enterprise_evidence_graph_v1",
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "candidate_count": len(state.candidates),
                "scored_candidate_count": len(state.scorecards),
                "scraped_candidate_count": len(state.scrapes),
                "verified_candidates": sum(1 for c in state.scorecards if c.validation_status == "VERIFIED"),
            },
        }

    def coding_readiness(self, state: ProductSearchState, selected: CandidateScorecard | None) -> CodingReadiness:
        scrape = selected.scrape if selected else None
        evidence: list[str] = []
        missing: list[str] = []
        hints: dict[str, Any] = {}

        checks = {
            "product_name": bool(scrape and (scrape.page_product_name or scrape.title or scrape.h1)),
            "brand": bool(scrape and scrape.brand),
            "manufacturer": bool(scrape and scrape.manufacturer),
            "description": bool(scrape and scrape.description and len(scrape.description) >= 40),
            "spec_table_or_attributes": bool(scrape and (scrape.specs or scrape.attributes)),
            "images": bool(scrape and scrape.image_count > 0),
            "ean_or_gtin": bool((scrape and scrape.structured_eans) or state.task.ean),
            "price_or_availability": bool(scrape and (scrape.has_price or scrape.availability)),
            "product_page": bool(scrape and scrape.looks_like_product_page),
            "scrape_usable": bool(scrape and scrape.is_scrapable and scrape.success and scrape.reachable),
        }
        weights = {
            "product_name": 0.14,
            "brand": 0.12,
            "manufacturer": 0.10,
            "description": 0.10,
            "spec_table_or_attributes": 0.14,
            "images": 0.12,
            "ean_or_gtin": 0.12,
            "price_or_availability": 0.04,
            "product_page": 0.06,
            "scrape_usable": 0.06,
        }
        for key, ok in checks.items():
            (evidence if ok else missing).append(key)
        score = round(sum(weights[k] for k, ok in checks.items() if ok), 4)
        if score >= 0.80:
            status = "CODING_READY"
        elif score >= 0.55:
            status = "CODING_PARTIAL"
        elif scrape and scrape.is_scrapable:
            status = "URL_ONLY_NOT_CODING_READY"
        else:
            status = "NEEDS_REVIEW"

        if scrape:
            hints = {
                "product_name": scrape.page_product_name or scrape.title or scrape.h1,
                "brand": scrape.brand,
                "manufacturer": scrape.manufacturer,
                "description_excerpt": scrape.description[:500],
                "specs": dict(list(scrape.specs.items())[:30]),
                "attributes": dict(list(scrape.attributes.items())[:30]),
                "image_urls": list(scrape.image_urls[:10]),
                "structured_eans": list(scrape.structured_eans),
                "price": scrape.price,
                "currency": scrape.currency,
                "availability": scrape.availability,
            }
        return CodingReadiness(status=status, score=score, available_evidence=tuple(evidence), missing_evidence=tuple(missing), feature_hints=hints)

    def confidence_breakdown(self, state: ProductSearchState, selected: CandidateScorecard | None, readiness: CodingReadiness, consensus: float) -> ConfidenceBreakdown:
        if not selected:
            return ConfidenceBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, consensus, readiness.score, 0.0)
        scrape = selected.scrape
        verification = selected.verification
        identity = max(selected.identity_score, 1.0 if verification and verification.identity_status == "VERIFIED" else 0.0)
        scrapability = 0.0
        if scrape:
            scrapability = sum([
                0.25 if scrape.success else 0,
                0.20 if scrape.reachable else 0,
                0.25 if scrape.is_scrapable else 0,
                0.20 if scrape.looks_like_product_page else 0,
                0.10 * min(1.0, scrape.richness_score),
            ])
        country = 1.0 if selected.country_check in {"MATCHED", "NOT_PROVIDED"} else 0.35
        retailer = 1.0 if selected.retailer_check == "MATCHED" else 0.65 if selected.retailer_check in {"NOT_PROVIDED", "UNKNOWN"} else 0.35
        variant = 1.0
        if selected.variant_check == "CONFLICT" or (verification and verification.variant_check == "CONFLICT"):
            variant = 0.0
        elif selected.variant_check in {"UNKNOWN", "NOT_CHECKED"}:
            variant = 0.70
        final = round(min(1.0, (identity * 0.28) + (scrapability * 0.22) + (country * 0.12) + (retailer * 0.08) + (variant * 0.12) + (consensus * 0.08) + (readiness.score * 0.10)), 4)
        return ConfidenceBreakdown(
            identity_confidence=round(min(1.0, identity), 4),
            scrapability_confidence=round(min(1.0, scrapability), 4),
            country_confidence=round(country, 4),
            retailer_confidence=round(retailer, 4),
            variant_confidence=round(variant, 4),
            source_consensus_score=round(consensus, 4),
            coding_readiness_confidence=readiness.score,
            final_confidence=final,
        )

    def source_consensus_score(self, state: ProductSearchState) -> float:
        usable = [c for c in state.scorecards if c.scrape and c.scrape.is_scrapable and c.scrape.looks_like_product_page]
        if not usable:
            return 0.0
        verified = [c for c in usable if c.validation_status == "VERIFIED"]
        domains = {domain_of(c.candidate.url) for c in usable if c.candidate.url}
        source_types = Counter(st for c in usable for st in c.candidate.source_types)
        score = 0.25
        score += min(0.30, len(usable) * 0.08)
        score += min(0.20, len(domains) * 0.06)
        score += 0.20 if verified else 0.0
        score += 0.05 if len(source_types) >= 2 else 0.0
        return round(min(1.0, score), 4)

    def quality_tier(self, state: ProductSearchState, selected: CandidateScorecard | None, readiness: CodingReadiness, confidence: ConfidenceBreakdown, failures: list[str]) -> tuple[str, str]:
        final = state.final_result
        if not final or not selected:
            return "E", "No final candidate was selected."
        if final.product_url and final.verified_exact_url and not final.needs_review and readiness.score >= 0.80 and confidence.final_confidence >= 0.85:
            return "A", "Verified exact, scrape-usable, coding-ready evidence."
        if final.product_url and final.is_scrapable and final.is_exact_product_match and confidence.final_confidence >= 0.75:
            return "B", "Exact and scrape-usable, but coding evidence or confidence is not Tier A."
        if final.product_url and final.is_scrapable:
            return "C", "Usable product URL exists but exactness/coding readiness requires review."
        if final.best_reference_url or failures:
            return "D", "Reference-only or weak evidence; do not auto-submit."
        return "E", "No usable URL or evidence was found."

    def failure_taxonomy(self, state: ProductSearchState, selected: CandidateScorecard | None) -> list[str]:
        final = state.final_result
        failures: set[str] = set()
        if not state.candidates:
            failures.add("NO_CANDIDATE_FOUND")
        if final and not final.product_url:
            failures.add(final.url_decision_status or "NO_OPERATIONAL_PRODUCT_URL")
        if state.task.retailer_name and final and final.requested_retailer_attempted and not final.selected_from_requested_retailer:
            failures.add("REQUESTED_RETAILER_NOT_SELECTED")
        if final and final.requested_retailer_scrapability_status in {"UNUSABLE_FOR_EVIDENCE", "SCRAPABILITY_CHECK_IN_PROGRESS"}:
            failures.add("REQUESTED_RETAILER_BLOCKED_OR_THIN")
        if any(c.variant_check == "CONFLICT" for c in state.scorecards):
            failures.add("VARIANT_CONFLICT")
        if any(c.verification and c.verification.ean_conflict_is_blocking for c in state.scorecards):
            failures.add("EAN_CONFLICT")
        if any(c.scrape and c.scrape.looks_like_homepage for c in state.scorecards):
            failures.add("HOMEPAGE_OR_LISTING_PAGE_CANDIDATE")
        if any(c.scrape and c.scrape.is_soft_404 for c in state.scorecards):
            failures.add("SOFT_404_OR_REMOVED_PAGE")
        if any(c.scrape and c.scrape.reachable and c.scrape.word_count < 80 for c in state.scorecards):
            failures.add("PRODUCT_PAGE_THIN")
        if any(c.llm_decision in {"INSUFFICIENT_EVIDENCE", "LLM_FAILED", "UNSCRAPABLE"} for c in state.scorecards):
            failures.add("LLM_OR_EVIDENCE_INSUFFICIENT")
        if final and final.selected_from_global_fallback:
            failures.add("ONLY_GLOBAL_OR_GLOBAL_FALLBACK_SELECTED")
        if selected and selected.hard_failures:
            failures.update(selected.hard_failures)
        return sorted(failures)

    def product_coding_input(self, state: ProductSearchState, selected: CandidateScorecard | None, readiness: CodingReadiness, confidence: ConfidenceBreakdown, quality_tier: str, supporting_urls: tuple[str, ...]) -> dict[str, Any]:
        final = state.final_result
        scrape = selected.scrape if selected else None
        verification = selected.verification if selected else None
        return {
            "schema_version": "product_coding_input_v1",
            "row_id": state.task.row_id,
            "quality_tier": quality_tier,
            "coding_readiness_status": readiness.status,
            "coding_readiness_score": readiness.score,
            "confidence": confidence.to_dict(),
            "input_identity": state.task.to_dict(),
            "normalized_identity_graph": state.identity_graph.to_dict() if hasattr(state.identity_graph, "to_dict") else state.identity_graph,
            "selected_url": final.product_url if final else None,
            "verified_exact_url": final.verified_exact_url if final else None,
            "best_reference_url": final.best_reference_url if final else None,
            "supporting_urls": list(supporting_urls),
            "selected_page_evidence": {
                "title": scrape.title if scrape else "",
                "h1": scrape.h1 if scrape else "",
                "product_name": scrape.page_product_name if scrape else "",
                "brand": scrape.brand if scrape else "",
                "manufacturer": scrape.manufacturer if scrape else "",
                "description": scrape.description if scrape else "",
                "specs": scrape.specs if scrape else {},
                "attributes": scrape.attributes if scrape else {},
                "structured_eans": list(scrape.structured_eans) if scrape else [],
                "image_urls": list(scrape.image_urls) if scrape else [],
                "price": scrape.price if scrape else None,
                "currency": scrape.currency if scrape else "",
                "availability": scrape.availability if scrape else "",
                "richness_score": scrape.richness_score if scrape else 0.0,
            },
            "identity_verification": verification.to_dict() if verification else None,
            "review_flags": self.failure_taxonomy(state, selected),
            "feature_hints": readiness.feature_hints,
        }

    def review_feedback_template(self, state: ProductSearchState, quality_tier: str, failures: list[str]) -> dict[str, Any]:
        return {
            "schema_version": "review_feedback_v1",
            "row_id": state.task.row_id,
            "quality_tier_at_review": quality_tier,
            "failure_taxonomy_at_review": failures,
            "review_status": "PENDING",
            "accepted_url": "",
            "rejected_url": state.final_result.product_url if state.final_result else "",
            "correct_url": "",
            "correct_brand": "",
            "correct_manufacturer": "",
            "correct_variant_notes": "",
            "review_reason": "",
            "reviewer_notes": "",
        }

    def supporting_urls(self, state: ProductSearchState, selected: CandidateScorecard | None, *, limit: int = 5) -> list[str]:
        urls: list[str] = []
        if selected:
            urls.append(selected.candidate.url)
        for card in state.scorecards:
            if card.candidate.url in urls:
                continue
            if card.scrape and card.scrape.is_scrapable and card.scrape.looks_like_product_page and not card.hard_failures:
                urls.append(card.candidate.url)
            if len(urls) >= limit:
                break
        return urls

    def source_reliability(self, url: str, source_types: tuple[str, ...] = ()) -> float:
        domain = domain_of(url).lower()
        if any(h in domain for h in MANUFACTURER_HINTS):
            return 0.95
        if any(h in domain for h in MARKETPLACE_HINTS):
            return 0.70
        if any(h in domain for h in AGGREGATOR_HINTS):
            return 0.40
        if "ai" in {s.lower() for s in source_types} and not source_types:
            return 0.35
        return 0.82

    def source_reliability_label(self, url: str, source_types: tuple[str, ...] = ()) -> str:
        score = self.source_reliability(url, source_types)
        if score >= 0.90:
            return "OFFICIAL_OR_MANUFACTURER_LIKE"
        if score >= 0.78:
            return "RETAILER_OR_DOMAIN_EVIDENCE"
        if score >= 0.60:
            return "MARKETPLACE_EVIDENCE"
        return "LOW_RELIABILITY_REFERENCE"

    def render_quality_markdown(self, state: ProductSearchState, assessment: EnterpriseEvidenceAssessment) -> str:
        c = assessment.confidence
        r = assessment.coding_readiness
        lines = [
            "# Enterprise Quality Assessment",
            "",
            f"- **Row ID:** `{state.task.row_id}`",
            f"- **Quality tier:** `{assessment.quality_tier}`",
            f"- **Reason:** {assessment.quality_tier_reason}",
            f"- **Coding readiness:** `{r.status}` / `{r.score}`",
            f"- **Failure taxonomy:** {', '.join(assessment.failure_taxonomy) or 'None'}",
            "",
            "## Confidence Decomposition",
            "",
            "| Component | Score |",
            "|---|---:|",
            f"| Identity | {c.identity_confidence:.4f} |",
            f"| Scrapability | {c.scrapability_confidence:.4f} |",
            f"| Country | {c.country_confidence:.4f} |",
            f"| Retailer | {c.retailer_confidence:.4f} |",
            f"| Variant | {c.variant_confidence:.4f} |",
            f"| Source consensus | {c.source_consensus_score:.4f} |",
            f"| Coding readiness | {c.coding_readiness_confidence:.4f} |",
            f"| Final | {c.final_confidence:.4f} |",
            "",
            "## Coding Evidence",
            "",
            f"- **Available:** {', '.join(r.available_evidence) or 'None'}",
            f"- **Missing:** {', '.join(r.missing_evidence) or 'None'}",
            "",
            "## Supporting URLs",
            "",
        ]
        if assessment.supporting_urls:
            lines.extend([f"- {url}" for url in assessment.supporting_urls])
        else:
            lines.append("No supporting URLs were available.")
        lines.extend([
            "",
            "## Product Coding Handoff",
            "",
            "See `product_coding_input.json` for the downstream feature-coding payload.",
        ])
        return "\n".join(lines).rstrip() + "\n"

    def _selected_card(self, state: ProductSearchState) -> CandidateScorecard | None:
        final = state.final_result
        if not final:
            return None
        urls = [final.product_url, final.verified_exact_url, final.best_available_url, final.best_reference_url]
        for url in urls:
            if not url:
                continue
            for card in state.scorecards:
                if card.candidate.url == url:
                    return card
        return state.scorecards[0] if state.scorecards else None

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
