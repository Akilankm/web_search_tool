from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from hashlib import sha1
from typing import Any

from loguru import logger

from src.product_evidence_harness.contracts import MatchVerification, ProductQuery, ScrapeResult
from src.product_evidence_harness.identity.graph import ProductIdentityGraph, ProductIdentityGraphBuilder
from src.product_evidence_harness.identity.normalizer import fold_text, tokens

from .contracts import (
    AtomicEvidence,
    ClaimStatus,
    EvidencePolarity,
    MarketStage,
    ProductBeliefState,
    ProductClaim,
    ProductHypothesis,
    ProductUncertainty,
    ResolutionStatus,
)


_PACK_RE = re.compile(r"(?<![a-z0-9])(\d{1,4})\s*[x×]\s*(\d{1,4})(?:\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(ml|cl|l|g|kg|pcs?|ct))?", re.I)
_MEASURE_RE = re.compile(r"(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*(ml|cl|l|g|kg|mm|cm|m|inch|in|gb|tb|w|v)(?![a-z0-9])", re.I)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _softmax(scores: list[float], temperature: float) -> list[float]:
    if not scores:
        return []
    maximum = max(scores)
    values = [math.exp((score - maximum) / max(0.05, temperature)) for score in scores]
    total = sum(values) or 1.0
    return [value / total for value in values]


def _overlap(left: str, right: str) -> float:
    left_tokens = {item for item in tokens(left, min_len=2) if len(item) >= 2}
    if not left_tokens:
        return 0.0
    folded = fold_text(right)
    return sum(item in folded for item in left_tokens) / len(left_tokens)


def _id(prefix: str, *parts: Any) -> str:
    digest = sha1("|".join(map(str, parts)).encode("utf-8", "ignore")).hexdigest()[:12]
    return f"{prefix}-{digest}"


@dataclass
class ProductBeliefEngine:
    """Offline-first product interpretation followed by evidence-driven updates."""

    enable_llm: bool | None = None
    temperature: float = 0.85
    max_hypotheses: int = 5

    def initialize(self, product: ProductQuery, identity_graph: ProductIdentityGraph | None = None) -> ProductBeliefState:
        graph = identity_graph or ProductIdentityGraphBuilder().build(product)
        claims = self._claims(product, graph)
        llm_payload, usage = self._llm_interpret(product, graph, claims)
        hypotheses = self._hypotheses(product, graph, llm_payload)
        probabilities = _softmax([hypothesis.prior_score for hypothesis in hypotheses], self.temperature)
        for hypothesis, probability in zip(hypotheses, probabilities):
            hypothesis.score = hypothesis.prior_score
            hypothesis.posterior_probability = round(probability, 6)

        state = ProductBeliefState(
            row_id=product.row_id,
            raw_main_text=product.main_text,
            country_code=product.country_code,
            requested_retailer=product.retailer_name,
            interpretation_source="LLM_STRUCTURED_NO_WEB" if llm_payload else "DETERMINISTIC_FALLBACK",
            claims=claims,
            hypotheses=hypotheses,
            negative_constraints=[_clean(item) for item in llm_payload.get("negative_constraints", []) if _clean(item)] if llm_payload else [],
            unknowns=[_clean(item) for item in llm_payload.get("unknowns", []) if _clean(item)] if llm_payload else self._default_unknowns(graph),
            llm_summary=_clean(llm_payload.get("summary")) if llm_payload else "",
            llm_usage=usage,
        )
        if not product.retailer_name:
            state.market_path = (MarketStage.COUNTRY_ALTERNATIVE.value, MarketStage.GLOBAL_FALLBACK.value)
        state.uncertainties = self._uncertainties(state)
        self._metrics(state, graph)
        state.current_market_stage = self.market_stage_for_credit(product, 1).value
        state.add_snapshot("offline_product_interpretation")
        return state

    def market_stage_for_credit(self, product: ProductQuery, credit_number: int) -> MarketStage:
        credit_number = max(1, int(credit_number))
        if product.retailer_name and credit_number == 1:
            return MarketStage.REQUESTED_RETAILER
        if product.retailer_name and credit_number == 2:
            return MarketStage.COUNTRY_ALTERNATIVE
        if not product.retailer_name and credit_number <= 2:
            return MarketStage.COUNTRY_ALTERNATIVE
        return MarketStage.GLOBAL_FALLBACK

    def query_for_stage(self, product: ProductQuery, state: ProductBeliefState, stage: MarketStage, *, diagnostic: bool = False) -> str:
        leading = state.leading_hypothesis
        identity = leading.canonical_name if leading else product.main_text
        parts = [f'"{product.ean}"' if product.ean else "", f'"{_clean(identity)}"']
        if diagnostic and state.uncertainties:
            parts.extend(f'"{value}"' for value in state.uncertainties[0].candidate_values[:2])
        if stage == MarketStage.REQUESTED_RETAILER:
            parts.extend([f'"{product.retailer_name}"', product.country_code, "product"])
        elif stage == MarketStage.COUNTRY_ALTERNATIVE:
            parts.extend([product.country_code, "product"])
        else:
            parts.append("product")
        return _clean(" ".join(part for part in parts if part))

    def search_plan_summary(self, product: ProductQuery, state: ProductBeliefState, max_credits: int = 3) -> list[dict[str, Any]]:
        return [
            {
                "credit": credit,
                "market_stage": (stage := self.market_stage_for_credit(product, credit)).value,
                "query": self.query_for_stage(product, state, stage, diagnostic=credit > 1),
                "objective": self._stage_objective(stage, state),
            }
            for credit in range(1, max_credits + 1)
        ]

    def update_from_scrape(
        self,
        state: ProductBeliefState,
        product: ProductQuery,
        scrape: ScrapeResult,
        verification: MatchVerification,
        *,
        market_stage: str = "",
    ) -> ProductBeliefState:
        new_evidence = self._evidence(state, scrape, verification, market_stage)
        known = {item.evidence_id for item in state.evidence_ledger}
        new_evidence = [item for item in new_evidence if item.evidence_id not in known]
        if not new_evidence:
            return state
        state.evidence_ledger.extend(new_evidence)
        page_text = " ".join(
            [scrape.title, scrape.h1, scrape.page_product_name, scrape.brand, scrape.manufacturer, scrape.description, scrape.markdown_excerpt]
            + [f"{key} {value}" for key, value in (scrape.specs or {}).items()]
        )
        for hypothesis in state.hypotheses:
            delta = 2.8 * _overlap(hypothesis.canonical_name, page_text)
            delta += 0.8 * _overlap(hypothesis.category, page_text) if hypothesis.category != "unknown" else 0.0
            if verification.identity_status == "VERIFIED":
                delta += 2.2
            elif verification.identity_status == "PROBABLE":
                delta += 0.8
            elif verification.identity_status == "MISMATCH":
                delta -= 5.0
            if verification.exact_product_check == "EXACT_MATCH":
                delta += 2.5
            elif verification.exact_product_check in {"WRONG_PRODUCT", "MISMATCH"}:
                delta -= 5.0
            if verification.variant_check == "MATCHED":
                delta += 1.2
            elif verification.variant_check == "CONFLICT":
                delta -= 4.0
            if verification.quantity_check == "MATCHED":
                delta += 1.0
            elif verification.quantity_check == "CONFLICT":
                delta -= 3.0
            if verification.ean_check == "MATCHED":
                delta += 4.5
            elif verification.ean_conflict_is_blocking:
                delta -= 6.0
            if scrape.reachable and scrape.is_scrapable and scrape.looks_like_product_page:
                delta += 0.6
            hypothesis.score += delta
            for evidence in new_evidence:
                target = hypothesis.supporting_evidence_ids if evidence.polarity == EvidencePolarity.SUPPORTS else hypothesis.contradicting_evidence_ids
                if evidence.polarity != EvidencePolarity.NEUTRAL and evidence.evidence_id not in target:
                    target.append(evidence.evidence_id)
        probabilities = _softmax([hypothesis.score for hypothesis in state.hypotheses], self.temperature)
        for hypothesis, probability in zip(state.hypotheses, probabilities):
            hypothesis.posterior_probability = round(probability, 6)
        state.current_market_stage = market_stage or state.current_market_stage
        state.recalculate_entropy()
        state.uncertainties = self._uncertainties(state)
        self._resolution(state, verification)
        state.add_snapshot(f"scrape_evidence:{scrape.url}")
        return state

    def _claims(self, product: ProductQuery, graph: ProductIdentityGraph) -> list[ProductClaim]:
        output: list[ProductClaim] = []

        def add(field: str, value: Any, status: ClaimStatus, confidence: float, source: tuple[str, ...] = (), code: str = "") -> None:
            if value in (None, "", (), [], {}):
                return
            output.append(ProductClaim(_id("C", field, value), field, value, status, confidence, source, code))

        add("main_text", product.main_text, ClaimStatus.EXPLICIT, 1.0, (product.main_text,), "USER_INPUT")
        add("country_code", product.country_code, ClaimStatus.EXPLICIT, 1.0, (product.country_code,), "USER_INPUT")
        add("requested_retailer", product.retailer_name, ClaimStatus.EXPLICIT, 1.0, ((product.retailer_name or ""),), "USER_INPUT")
        add("ean", product.ean, ClaimStatus.EXPLICIT, 1.0, ((product.ean or ""),), "USER_INPUT")
        add("normalized_main_text", graph.normalized_main_text, ClaimStatus.NORMALIZED, 0.98, (product.main_text,), "TEXT_NORMALIZATION")
        add("model_or_series", list(graph.model_or_series_terms), ClaimStatus.DETERMINISTICALLY_DERIVED, 0.90, graph.model_or_series_terms, "MODEL_PATTERN")
        add("product_form", list(graph.product_form_families or graph.product_form_terms), ClaimStatus.DETERMINISTICALLY_DERIVED, 0.82, graph.product_form_terms, "FORM_LEXICON")
        add("variants", list(graph.variant_terms), ClaimStatus.DETERMINISTICALLY_DERIVED, 0.82, graph.variant_terms, "VARIANT_PARSER")
        add("size", list(graph.size_terms), ClaimStatus.DETERMINISTICALLY_DERIVED, 0.95, graph.size_terms, "MEASUREMENT_PARSER")
        add("color", list(graph.color_terms), ClaimStatus.DETERMINISTICALLY_DERIVED, 0.92, graph.color_terms, "COLOR_LEXICON")
        add("quantity", list(graph.quantity_terms), ClaimStatus.DETERMINISTICALLY_DERIVED, 0.88, graph.quantity_terms, "QUANTITY_PARSER")
        packs = [match.group(0) for match in _PACK_RE.finditer(product.main_text)]
        measures = [f"{match.group(1)} {match.group(2)}" for match in _MEASURE_RE.finditer(product.main_text)]
        add("pack_expressions", packs, ClaimStatus.DETERMINISTICALLY_DERIVED, 0.92, tuple(packs), "PACK_ALGEBRA")
        add("measurements", measures, ClaimStatus.DETERMINISTICALLY_DERIVED, 0.96, tuple(measures), "MEASUREMENT_PARSER")
        return output

    def _hypotheses(self, product: ProductQuery, graph: ProductIdentityGraph, payload: dict[str, Any]) -> list[ProductHypothesis]:
        output: list[ProductHypothesis] = []
        for index, raw in enumerate(payload.get("hypotheses", [])[: self.max_hypotheses], 1):
            if not isinstance(raw, dict) or not _clean(raw.get("canonical_name")):
                continue
            probability = float(raw.get("prior_probability") or 0.5)
            output.append(
                ProductHypothesis(
                    hypothesis_id=f"H{index}",
                    canonical_name=_clean(raw["canonical_name"]),
                    category=_clean(raw.get("category")) or "unknown",
                    product_role=_clean(raw.get("product_role")) or "consumer_product",
                    attributes=dict(raw.get("attributes") or {}),
                    assumptions=[_clean(item) for item in raw.get("assumptions", []) if _clean(item)],
                    negative_constraints=[_clean(item) for item in raw.get("negative_constraints", []) if _clean(item)],
                    prior_score=max(-3.0, min(3.0, math.log(max(0.01, min(0.99, probability)) / max(0.01, 1 - min(0.99, probability))))),
                )
            )
        if output:
            return output
        base = graph.search_name or graph.normalized_main_text or product.main_text
        category = graph.product_form_families[0] if graph.product_form_families else "unknown"
        output.append(ProductHypothesis("H1", base, category=category, prior_score=1.2, attributes={"size": list(graph.size_terms), "variant": list(graph.variant_terms)}))
        pack = next(iter(_PACK_RE.finditer(product.main_text)), None)
        if pack:
            output[0].assumptions.append("The outer multiplier may represent vendor logistics rather than the consumer sale unit.")
            output.append(
                ProductHypothesis(
                    "H2",
                    f"{base} consumer multipack {pack.group(0)}",
                    category=category,
                    product_role="consumer_multipack",
                    prior_score=0.35,
                    attributes={"pack_interpretation": "consumer_multipack", "raw_pack": pack.group(0)},
                    assumptions=["The complete pack expression is visible to the retailer consumer."],
                )
            )
        if not graph.product_form_families:
            output.append(ProductHypothesis("H3", f"{base} exact product form unresolved", category="unknown", prior_score=-0.15, assumptions=["Product form must be resolved from external evidence."]))
        return output[: self.max_hypotheses]

    def _uncertainties(self, state: ProductBeliefState) -> list[ProductUncertainty]:
        fields: dict[str, set[str]] = {}
        impacted: dict[str, set[str]] = {}
        for hypothesis in state.hypotheses:
            values = {"category": hypothesis.category, "product_role": hypothesis.product_role, **hypothesis.attributes}
            for field, value in values.items():
                text = _clean(value)
                if not text:
                    continue
                fields.setdefault(field, set()).add(text)
                impacted.setdefault(field, set()).add(hypothesis.hypothesis_id)
        output: list[ProductUncertainty] = []
        for field, values in fields.items():
            if len(values) < 2:
                continue
            impact = 0.95 if field in {"category", "product_role", "model", "pack_interpretation"} else 0.65
            entropy = min(1.0, math.log(len(values) + 1, 4))
            output.append(ProductUncertainty(field, tuple(sorted(values)), round(entropy, 4), impact, round(entropy * impact, 4), tuple(sorted(impacted[field]))))
        for unknown in state.unknowns:
            if unknown not in fields:
                output.append(ProductUncertainty(unknown, ("unknown",), 1.0, 0.8, 0.8, tuple(h.hypothesis_id for h in state.hypotheses)))
        return sorted(output, key=lambda item: item.priority, reverse=True)

    def _evidence(self, state: ProductBeliefState, scrape: ScrapeResult, verification: MatchVerification, market_stage: str) -> list[AtomicEvidence]:
        url = scrape.final_url or scrape.url
        hypotheses = tuple(item.hypothesis_id for item in state.hypotheses)
        output: list[AtomicEvidence] = []

        def add(field: str, value: Any, polarity: EvidencePolarity, directness: str, reliability: float, confidence: float, excerpt: str = "", hard: bool = False) -> None:
            if value in (None, "", (), [], {}):
                return
            output.append(AtomicEvidence(_id("E", url, field, value), url, field, value, polarity, hypotheses, directness, reliability, confidence, market_stage, _clean(excerpt)[:500], hard))

        add("browser_reachable", scrape.reachable, EvidencePolarity.SUPPORTS if scrape.reachable else EvidencePolarity.CONTRADICTS, "HTTP_OR_BROWSER", 0.95, 1.0, hard=not scrape.reachable)
        add("product_page", scrape.looks_like_product_page, EvidencePolarity.SUPPORTS if scrape.looks_like_product_page else EvidencePolarity.CONTRADICTS, "PAGE_CLASSIFIER", 0.90, 0.95, hard=not scrape.looks_like_product_page)
        add("page_title", scrape.page_product_name or scrape.h1 or scrape.title, EvidencePolarity.SUPPORTS, "EXPLICIT_PAGE_TITLE", 0.86, 0.95, scrape.title)
        add("brand", scrape.brand, EvidencePolarity.SUPPORTS, "STRUCTURED_BRAND", 0.88, 0.92)
        add("manufacturer", scrape.manufacturer, EvidencePolarity.SUPPORTS, "STRUCTURED_MANUFACTURER", 0.82, 0.88)
        add("gtins", list(scrape.structured_eans), EvidencePolarity.CONTRADICTS if verification.ean_check == "CONFLICT" else EvidencePolarity.SUPPORTS, "STRUCTURED_GTIN", 0.98, 0.98, hard=verification.ean_conflict_is_blocking)
        add("identity_status", verification.identity_status, EvidencePolarity.CONTRADICTS if verification.identity_status == "MISMATCH" else EvidencePolarity.SUPPORTS, "DETERMINISTIC_VERIFICATION", 0.96, 0.98, hard=verification.identity_status == "MISMATCH")
        add("exact_product_check", verification.exact_product_check, EvidencePolarity.CONTRADICTS if verification.exact_product_check in {"WRONG_PRODUCT", "MISMATCH"} else EvidencePolarity.SUPPORTS, "DETERMINISTIC_EXACTNESS", 0.96, 0.98, hard=verification.exact_product_check in {"WRONG_PRODUCT", "MISMATCH"})
        add("variant_check", verification.variant_check, EvidencePolarity.CONTRADICTS if verification.variant_check == "CONFLICT" else EvidencePolarity.SUPPORTS, "VARIANT_VALIDATION", 0.94, 0.96, ", ".join(verification.variant_conflict_terms), verification.variant_check == "CONFLICT")
        add("quantity_check", verification.quantity_check, EvidencePolarity.CONTRADICTS if verification.quantity_check == "CONFLICT" else EvidencePolarity.SUPPORTS, "PACK_VALIDATION", 0.90, 0.94, hard=verification.quantity_check == "CONFLICT")
        add("content_richness", scrape.richness_score, EvidencePolarity.SUPPORTS if scrape.richness_score >= 0.35 else EvidencePolarity.NEUTRAL, "SCRAPE_QUALITY", 0.75, 0.90)
        return output

    def _resolution(self, state: ProductBeliefState, verification: MatchVerification) -> None:
        leading = state.leading_hypothesis
        if leading is None:
            state.resolution_status = ResolutionStatus.INSUFFICIENT_EVIDENCE
            return
        hard_conflict = any(item.hard_conflict and item.polarity == EvidencePolarity.CONTRADICTS for item in state.evidence_ledger)
        exact = verification.identity_status == "VERIFIED" and verification.exact_product_check in {"EXACT_MATCH", "UNKNOWN"} and verification.variant_check != "CONFLICT"
        if hard_conflict and leading.posterior_probability < 0.80:
            state.resolution_status = ResolutionStatus.CONFLICTING
        elif exact and leading.posterior_probability >= 0.90 and state.posterior_margin >= 0.20:
            state.resolution_status = ResolutionStatus.EXACT
            state.selected_hypothesis_id = leading.hypothesis_id
        elif leading.posterior_probability >= 0.72 and state.posterior_margin >= 0.12:
            state.resolution_status = ResolutionStatus.PROBABLE
            state.selected_hypothesis_id = leading.hypothesis_id
        elif state.posterior_margin < 0.12:
            state.resolution_status = ResolutionStatus.AMBIGUOUS
        else:
            state.resolution_status = ResolutionStatus.IN_PROGRESS

    def _metrics(self, state: ProductBeliefState, graph: ProductIdentityGraph) -> None:
        classified = sum(bool(value) for value in (graph.model_or_series_terms, graph.product_form_terms, graph.variant_terms, graph.size_terms, graph.color_terms, graph.quantity_terms, graph.input_ean))
        state.parse_coverage = round(min(1.0, 0.35 + classified / 10.0), 4)
        critical = [bool(graph.model_or_series_terms or graph.input_ean), bool(graph.product_form_terms or graph.product_form_families), bool(graph.variant_terms), bool(graph.size_terms or graph.quantity_terms)]
        state.identity_completeness = round(sum(critical) / len(critical), 4)
        state.recalculate_entropy()
        assumptions = sum(len(item.assumptions) for item in state.hypotheses)
        state.assumption_burden = round(min(1.0, assumptions / max(1, len(state.hypotheses) * 3)), 4)
        state.search_readiness = round(max(0.0, min(1.0, 0.38 * state.parse_coverage + 0.42 * state.identity_completeness + 0.20 * (1.0 - state.assumption_burden))), 4)

    @staticmethod
    def _default_unknowns(graph: ProductIdentityGraph) -> list[str]:
        output: list[str] = []
        if not graph.product_form_families:
            output.append("exact_product_type")
        if not graph.model_or_series_terms and not graph.input_ean:
            output.append("unique_model_or_identifier")
        if graph.quantity_terms:
            output.append("vendor_case_vs_consumer_sale_unit")
        if not graph.brand_candidates:
            output.append("consumer_brand")
        return output

    @staticmethod
    def _stage_objective(stage: MarketStage, state: ProductBeliefState) -> str:
        uncertainty = state.uncertainties[0].field if state.uncertainties else "exact_product_identity"
        if stage == MarketStage.REQUESTED_RETAILER:
            return f"Find a browser-openable exact product page at the requested retailer and resolve {uncertainty}."
        if stage == MarketStage.COUNTRY_ALTERNATIVE:
            return f"Find the exact product at another retailer within the requested country and resolve {uncertainty}."
        return f"Find a global exact-product reference after country exhaustion and resolve {uncertainty}."

    def _llm_interpret(self, product: ProductQuery, graph: ProductIdentityGraph, claims: list[ProductClaim]) -> tuple[dict[str, Any], dict[str, int]]:
        enabled = self.enable_llm
        if enabled is None:
            enabled = _enabled("PRODUCT_HARNESS_ENABLE_BELIEF_LLM", _enabled("PRODUCT_HARNESS_ENABLE_LLM", False) or _enabled("PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING", False))
        if not enabled:
            return {}, {}
        try:
            from src.product_evidence_harness.llm.service import get_llm_service

            schema = {
                "summary": "brief observable product interpretation",
                "hypotheses": [{
                    "canonical_name": "possible exact consumer product identity",
                    "category": "product category",
                    "product_role": "consumer_product|refill|accessory|replacement_part|bundle|vendor_case",
                    "attributes": {"brand": "", "model": "", "variant": "", "size": "", "pack_interpretation": ""},
                    "assumptions": [], "negative_constraints": [], "prior_probability": 0.0,
                }],
                "negative_constraints": [], "unknowns": [],
            }
            prompt = "\n".join([
                "NO INTERNET IS AVAILABLE. Build falsifiable product hypotheses from the input only.",
                f"MAIN_TEXT: {product.main_text}", f"COUNTRY_CODE: {product.country_code}",
                f"RETAILER_NAME: {product.retailer_name or 'not_provided'}", f"EAN: {product.ean or 'not_provided'}",
                "DETERMINISTIC_GRAPH:", json.dumps(graph.to_dict(), ensure_ascii=False),
                "CLAIMS:", json.dumps([claim.to_dict() for claim in claims], ensure_ascii=False),
                "Separate explicit facts, deterministic derivations, assumptions, and unknowns. Do not invent EAN/GTIN or URLs.",
                "Return strict JSON:", json.dumps(schema, ensure_ascii=False),
            ])
            response = get_llm_service().predict(
                prompt,
                system_prompt="You are an offline product identity analyst. Search evidence will be collected later.",
                response_format={"type": "json_object"}, max_tokens=1600, temperature=0.0,
                purpose="offline_product_belief_initialization",
            )
            return json.loads(response.content or "{}"), dict(response.usage or {})
        except Exception as exc:
            logger.warning("Offline product interpretation failed; deterministic fallback used | row_id={} | error={}", product.row_id, type(exc).__name__)
            return {}, {}
