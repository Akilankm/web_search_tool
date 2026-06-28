from __future__ import annotations

import json
from typing import Any

from src.product_evidence_harness.contracts import CandidateScorecard, ProductQuery, ProductSearchState
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder

ALLOWED_DECISIONS = {
    "EXACT_MATCH",
    "EXACT_MATCH_WITH_WARNING",
    "SIBLING_VARIANT",
    "WRONG_PRODUCT",
    "INSUFFICIENT_EVIDENCE",
    "NON_PRODUCT_PAGE",
    "UNSCRAPABLE",
}

SYSTEM_PROMPT_SEARCH_PLANNER = """
You are the reasoning/planning brain for a product URL discovery harness.
SerpAPI is only a search tool. crawl4ai is only a scraping/evidence tool.

Your job: create high-recall search queries to discover exact product detail page URLs.
Use only the user-provided fields. Never infer, guess, correct, or generate EAN/GTIN values.
If EAN is provided, you may include that exact EAN in queries. If EAN is absent, do not add any EAN/GTIN-like number.

MAIN_TEXT drives exact product identity. First reason about product identity: product form, model/series, size/format, color, quantity, pack/bundle/display status, language/edition, and manufacturer/brand terms. Preserve critical attributes in search queries.
Country code means country-first search. If RETAILER_NAME is provided, treat it as a preferred first evidence source, not as a hard constraint. First create requested_retailer queries. Then create country_alternative queries that do not force that retailer. Global fallback queries are allowed only after country-oriented queries.
Return search strategy, not facts. Do not claim a URL is final; crawl4ai must inspect pages before final selection.
Return strict JSON only.
""".strip()

SYSTEM_PROMPT_SEARCH_FEEDBACK = """
You are the feedback brain for a product URL discovery harness.
Review current search/candidate/scrape evidence and propose repair queries only when needed.
Do not invent facts. Do not suggest, correct, or generate EAN/GTIN values.
Use the input EAN only if it was provided by the user. SerpAPI will execute your queries; you are not browsing.
Return strict JSON only.
""".strip()

SYSTEM_PROMPT_EXACT_PRODUCT_JUDGE = """
You are an exact product URL validation judge.
Decide whether a scraped candidate URL represents the exact same product requested by MAIN_TEXT.

Rules:
- MAIN_TEXT/product identity is the driver.
- EAN is a strong user-provided anchor, but retailer EAN can be missing or wrong.
- Never invent, guess, correct, or suggest EAN/GTIN values.
- Use only user-provided EAN and scraped page EAN/GTIN evidence.
- Do not accept sibling variants, bundles, displays, boxes, cases, different colors, sizes, quantities, formats, language editions, or product forms as exact matches.
- If evidence is insufficient, return INSUFFICIENT_EVIDENCE.
- If one image is provided, use it only as supporting evidence; it cannot override text/variant mismatch.
Return strict JSON only.
""".strip()


def _country_profile_block(country_profiles: Any, task: ProductQuery) -> str:
    profile = country_profiles.get(task.country_code)
    lines = []
    for lp in profile.language_profiles_for(task.language_code):
        lines.append(
            f"- {lp.language_code} ({lp.language_name}) priority={lp.priority} distribution={lp.distribution_weight}; "
            f"country_terms={', '.join(lp.country_terms[:5])}; commerce_terms={', '.join(lp.commerce_terms[:8])}"
        )
    return "\n".join([
        f"country_code: {profile.country_code}",
        f"country_name: {profile.country_name}",
        f"country_tlds: {', '.join(profile.tlds) or 'not_configured'}",
        "language_priority:",
        *lines,
    ])


def build_search_plan_prompt(*, task: ProductQuery, country_profiles: Any, max_queries: int) -> str:
    schema = {
        "expanded_main_text": "string; expansion of MAIN_TEXT if compact/noisy, otherwise same meaning",
        "critical_terms": ["terms that must be preserved for exact product identity"],
        "variant_terms_to_preserve": ["color/size/format/quantity/language/edition/product-form terms"],
        "negative_terms": ["terms to exclude only if clearly sibling variants"],
        "search_queries": [
            {
                "query": "SerpAPI query string",
                "scope": "requested_retailer|country_alternative|country|global",
                "reason": "why this query is useful",
                "priority": 1,
                "must_include_ean": False,
            }
        ],
        "reasoning": "brief search strategy explanation",
    }
    return "\n".join([
        "INPUT PRODUCT",
        f"MAIN_TEXT: {task.main_text}",
        f"COUNTRY_CODE: {task.country_code}",
        f"EAN_USER_PROVIDED: {task.ean or 'not_provided'}",
        f"RETAILER_NAME: {task.retailer_name or 'not_provided'}",
        f"LANGUAGE_CODE: {task.language_code or 'not_provided'}",
        "",
        "DETERMINISTIC PRODUCT IDENTITY GRAPH",
        json.dumps(ProductIdentityGraphBuilder().build(task).to_dict(), ensure_ascii=False),
        "",
        "COUNTRY PROFILE",
        _country_profile_block(country_profiles, task),
        "",
        "TASK",
        f"Return up to {max_queries} search queries. If RETAILER_NAME is provided, first include requested_retailer queries for that retailer/country. Then include country_alternative queries that DO NOT force the requested retailer. Add at most one global fallback query.",
        "If MAIN_TEXT is compacted, expand it into searchable words while preserving exact product meaning.",
        "If EAN_USER_PROVIDED is present, use only that exact EAN in queries when useful. Do not create any other GTIN/EAN.",
        "",
        "REQUIRED JSON SHAPE",
        json.dumps(schema, ensure_ascii=False),
    ])


def build_search_feedback_prompt(*, state: ProductSearchState, country_profiles: Any, max_queries: int) -> str:
    candidates = []
    for idx, card in enumerate(state.scorecards[:12], start=1):
        s = card.scrape
        v = card.verification
        candidates.append({
            "rank": idx,
            "url": card.candidate.url,
            "title": card.candidate.title,
            "snippet": card.candidate.snippet[:300],
            "country_check": card.country_check,
            "scraped": bool(s and s.scraped),
            "scrapable": bool(s and s.is_scrapable),
            "product_page": bool(s and s.looks_like_product_page),
            "richness": s.richness_score if s else 0,
            "identity_status": v.identity_status if v else "UNVERIFIED",
            "ean_check": v.ean_check if v else "UNKNOWN",
            "variant_check": v.variant_check if v else "UNKNOWN",
            "hard_failures": list(card.hard_failures),
            "warnings": list(card.soft_warnings),
            "detector_findings": list(v.detector_findings)[:8] if v else [],
        })
    schema = {
        "expanded_main_text": "optional refined expansion",
        "critical_terms": ["terms to preserve"],
        "variant_terms_to_preserve": ["variant terms to preserve"],
        "negative_terms": ["terms to exclude if useful"],
        "search_queries": [
            {"query": "repair query", "scope": "requested_retailer|country_alternative|country|global", "reason": "why", "priority": 1, "must_include_ean": False}
        ],
        "reasoning": "why these repair/fallback queries are needed",
    }
    return "\n".join([
        "INPUT PRODUCT",
        f"MAIN_TEXT: {state.task.main_text}",
        f"COUNTRY_CODE: {state.task.country_code}",
        f"EAN_USER_PROVIDED: {state.task.ean or 'not_provided'}",
        f"RETAILER_NAME: {state.task.retailer_name or 'not_provided'}",
        "",
        "PRODUCT IDENTITY GRAPH",
        json.dumps((state.identity_graph.to_dict() if hasattr(state.identity_graph, "to_dict") else ProductIdentityGraphBuilder().build(state.task).to_dict()), ensure_ascii=False),
        "",
        "COUNTRY PROFILE",
        _country_profile_block(country_profiles, state.task),
        "",
        "CURRENT QUERIES EXECUTED",
        json.dumps(state.queries[-8:], ensure_ascii=False),
        "",
        "CURRENT CANDIDATE/SCRAPE SUMMARY",
        json.dumps(candidates, ensure_ascii=False),
        "",
        "TASK",
        f"Return up to {max_queries} refined queries if the exact product URL has not been sufficiently found.",
        "If requested retailer evidence is weak/non-scrapable/not exact, repair by searching other retailers within the same country using scope=country_alternative and without forcing RETAILER_NAME. Add global fallback only when country candidates are weak/non-scrapable/not exact.",
        "Use only the user-provided EAN if present. Do not invent or modify EAN/GTIN.",
        "",
        "REQUIRED JSON SHAPE",
        json.dumps(schema, ensure_ascii=False),
    ])


def build_adjudication_prompt(*, product: ProductQuery, card: CandidateScorecard, payload_level: str, image_url: str | None = None) -> str:
    s = card.scrape
    v = card.verification
    assert s is not None
    compact = payload_level.startswith("compact") or payload_level.startswith("minimal")
    minimal = payload_level.startswith("minimal")
    specs = dict(list((s.specs or {}).items())[:20 if not compact else 8])
    description = (s.description or s.markdown_excerpt or "")[: 1600 if not compact else 500]
    evidence = {
        "input": {
            "main_text": product.main_text,
            "country_code": product.country_code,
            "ean_user_provided": product.ean or "not_provided",
            "retailer_name": product.retailer_name or "not_provided",
        },
        "candidate": {
            "url": card.candidate.url,
            "domain": card.candidate.domain,
            "country_check": card.country_check,
            "source_types": list(card.candidate.source_types),
        },
        "scrape": {
            "reachable": s.reachable,
            "scraped": s.scraped,
            "success": s.success,
            "is_scrapable": s.is_scrapable,
            "looks_like_product_page": s.looks_like_product_page,
            "status_code": s.status_code,
            "title": s.title,
            "h1": s.h1,
            "page_product_name": s.page_product_name,
            "gtins": list(s.structured_eans),
            "brand": s.brand,
            "manufacturer": s.manufacturer,
            "availability": s.availability,
            "description": "" if minimal else description,
            "specs": {} if minimal else specs,
            "image_url_sent": image_url or None,
        },
        "deterministic_verification": {
            "identity_status": v.identity_status if v else "UNVERIFIED",
            "ean_check": v.ean_check if v else "UNKNOWN",
            "title_check": v.title_check if v else "UNKNOWN",
            "variant_check": v.variant_check if v else "UNKNOWN",
            "exact_product_check": v.exact_product_check if v else "UNKNOWN",
            "blocking_reasons": list(v.blocking_reasons) if v else [],
        },
    }
    schema = {
        "exact_product_match": True,
        "decision": "EXACT_MATCH|EXACT_MATCH_WITH_WARNING|SIBLING_VARIANT|WRONG_PRODUCT|INSUFFICIENT_EVIDENCE|NON_PRODUCT_PAGE|UNSCRAPABLE",
        "confidence": 0.0,
        "primary_identity_driver": "MAIN_TEXT_AND_SCRAPED_EVIDENCE",
        "main_text_assessment": {"status": "MATCHED|PARTIAL|MISMATCH|UNKNOWN", "reason": "..."},
        "ean_assessment": {"status": "MATCHED|CONFLICT|ABSENT|NOT_PROVIDED|NOISY|UNKNOWN", "is_blocking": False, "reason": "..."},
        "variant_assessment": {"status": "MATCHED|CONFLICT|UNKNOWN", "conflict_terms": [], "reason": "..."},
        "scrape_assessment": {"is_product_page": True, "is_scrapable": True, "usable_for_final": True},
        "image_assessment": {"used": bool(image_url), "status": "SUPPORTS_MATCH|CONTRADICTS_MATCH|NOT_USED|NOT_USEFUL", "reason": "..."},
        "reject_reason": None,
        "final_explanation": "short justification",
    }
    return "\n".join([
        "EVIDENCE PACKET",
        json.dumps(evidence, ensure_ascii=False),
        "",
        "TASK",
        "Decide whether this candidate URL is the exact same product as MAIN_TEXT.",
        "Pay special attention to product form, color, size/format, quantity/pack, language/edition, and scraped EAN/GTIN.",
        "Do not invent facts. Do not invent or correct EAN/GTIN.",
        "",
        "REQUIRED JSON SHAPE",
        json.dumps(schema, ensure_ascii=False),
    ])
