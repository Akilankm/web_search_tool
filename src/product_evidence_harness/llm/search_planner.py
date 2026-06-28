from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.product_evidence_harness.config import HarnessConfig
from src.product_evidence_harness.contracts import LLMCallRecord, LLMSearchPlan, LLMSearchQuery, ProductQuery, ProductSearchState
from src.product_evidence_harness.country_profiles import CountryProfileRegistry
from src.product_evidence_harness.gtin import equivalent_gtins, is_valid_gtin
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.identity.normalizer import quoted
from src.product_evidence_harness.llm.prompts import (
    SYSTEM_PROMPT_SEARCH_FEEDBACK,
    SYSTEM_PROMPT_SEARCH_PLANNER,
    build_search_feedback_prompt,
    build_search_plan_prompt,
)
from src.product_evidence_harness.llm.service import LLMResponse, LLMService, get_llm_service
from src.product_evidence_harness.query_builder import QueryBuilder


@dataclass
class LLMSearchPlanner:
    """LLM as the search brain, with strict guardrails.

    It generates and repairs search queries. It never creates EAN/GTIN values:
    generated queries are sanitized so only the user-provided EAN/equivalents can
    appear as GTIN-like numbers.
    """

    config: HarnessConfig
    query_builder: QueryBuilder
    country_profiles: CountryProfileRegistry
    service: LLMService | None = None

    def __post_init__(self) -> None:
        if self.service is None:
            self.service = get_llm_service()

    def plan_initial(self, state: ProductSearchState) -> tuple[LLMSearchPlan, LLMCallRecord]:
        prompt = build_search_plan_prompt(
            task=state.task,
            country_profiles=self.country_profiles,
            max_queries=self.config.llm_search_plan_max_queries,
        )
        return self._call_and_parse(
            state=state,
            stage="initial_search_plan",
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_SEARCH_PLANNER,
            max_queries=self.config.llm_search_plan_max_queries,
        )

    def plan_feedback(self, state: ProductSearchState) -> tuple[LLMSearchPlan, LLMCallRecord]:
        prompt = build_search_feedback_prompt(
            state=state,
            country_profiles=self.country_profiles,
            max_queries=self.config.llm_search_feedback_max_queries,
        )
        return self._call_and_parse(
            state=state,
            stage="search_feedback",
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_SEARCH_FEEDBACK,
            max_queries=self.config.llm_search_feedback_max_queries,
        )

    def _call_and_parse(self, *, state: ProductSearchState, stage: str, prompt: str, system_prompt: str, max_queries: int) -> tuple[LLMSearchPlan, LLMCallRecord]:
        call_index = len(state.llm_call_records) + 1
        try:
            response = self.service.predict(
                text=prompt,
                system_prompt=system_prompt,
                response_format={"type": "json_object"},
                purpose=stage,
            )
            plan = self._parse_response(
                product=state.task,
                raw=response.content,
                row_id=state.task.row_id,
                call_index=call_index,
                stage=stage,
                max_queries=max_queries,
            )
            record = self._record(state, call_index, stage, True, plan.queries, None, response)
            return plan, record
        except Exception as exc:
            logger.warning("LLM search planning failed; using deterministic fallback | row_id={} | stage={} | error={}", state.task.row_id, stage, exc)
            fallback_queries = self._fallback_queries(state, stage=stage, max_queries=max_queries)
            plan = LLMSearchPlan(
                row_id=state.task.row_id,
                call_index=call_index,
                stage=stage,
                queries=tuple(fallback_queries),
                reasoning="LLM search planning failed; deterministic fallback queries generated.",
                success=False,
                error=str(exc),
            )
            record = self._record(state, call_index, stage, False, tuple(fallback_queries), str(exc), None)
            return plan, record

    def _parse_response(self, *, product: ProductQuery, raw: str, row_id: str, call_index: int, stage: str, max_queries: int) -> LLMSearchPlan:
        obj = self._loads_json(raw)
        raw_queries = obj.get("search_queries") or obj.get("queries") or []
        queries: list[LLMSearchQuery] = []
        for idx, item in enumerate(raw_queries, start=1):
            if isinstance(item, str):
                q = item
                scope = "country" if idx < max_queries else "global"
                reason = "LLM-generated query"
                priority = idx
                must_include_ean = bool(product.ean and product.ean in q)
            elif isinstance(item, dict):
                q = str(item.get("query") or "").strip()
                scope = str(item.get("scope") or "country").lower()
                reason = str(item.get("reason") or "LLM-generated query")[:500]
                priority = int(item.get("priority") or idx)
                must_include_ean = bool(item.get("must_include_ean"))
            else:
                continue
            if not q:
                continue
            sanitized = self._sanitize_query(q, product)
            if not sanitized:
                continue
            normalized_scope = self._normalize_scope(scope, sanitized, product)
            lang = self._language_for_query(product, normalized_scope)
            queries.append(LLMSearchQuery(
                query=sanitized,
                source="llm_search_feedback" if stage == "search_feedback" else "llm_search_plan",
                scope=normalized_scope,
                reason=reason,
                priority=priority,
                language_code=lang.get("language_code"),
                language_name=lang.get("language_name"),
                must_include_ean=must_include_ean,
            ))
            if len(queries) >= max_queries:
                break

        if not queries:
            queries = self._fallback_queries_from_product(product, max_queries=max_queries, stage=stage)

        return LLMSearchPlan(
            row_id=row_id,
            call_index=call_index,
            stage=stage,
            expanded_main_text=str(obj.get("expanded_main_text") or "")[:300],
            critical_terms=tuple(str(x)[:80] for x in (obj.get("critical_terms") or []) if str(x).strip()),
            variant_terms_to_preserve=tuple(str(x)[:80] for x in (obj.get("variant_terms_to_preserve") or []) if str(x).strip()),
            negative_terms=tuple(str(x)[:80] for x in (obj.get("negative_terms") or []) if str(x).strip()),
            queries=tuple(queries),
            reasoning=str(obj.get("reasoning") or obj.get("reason") or "")[:1000],
            payload_level=stage,
            success=True,
            raw_response=raw[:4000],
        )


    def _normalize_scope(self, scope: str, query: str, product: ProductQuery) -> str:
        scope_l = (scope or "country").lower().strip()
        if scope_l == "global":
            return "global"
        if scope_l in {"requested_retailer", "retailer", "preferred_retailer"}:
            return "requested_retailer"
        if scope_l in {"country_alternative", "other_country_retailers", "country_other_retailer"}:
            return "country_alternative"
        # If a retailer was provided, a country query containing that retailer is
        # a preferred-retailer attempt; otherwise it is a same-country alternative.
        if product.retailer_name:
            tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9À-ž]+", product.retailer_name) if len(t) >= 2]
            folded = (query or "").lower()
            compact = re.sub(r"[^a-zA-Z0-9À-ž]+", "", folded)
            if any(t in folded or t in compact for t in tokens + ["".join(tokens)]):
                return "requested_retailer"
            return "country_alternative"
        return "country"

    def _language_for_query(self, product: ProductQuery, scope: str) -> dict[str, str | None]:
        if scope == "global":
            return {"language_code": product.language_code or "en", "language_name": "Global/Any"}
        try:
            lp = self.country_profiles.language_profiles_for(product.country_code, product.language_code)[0]
            return {"language_code": lp.language_code, "language_name": lp.language_name}
        except Exception:
            return {"language_code": product.language_code, "language_name": None}

    @staticmethod
    def _loads_json(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw or "{}")
        except Exception:
            m = re.search(r"\{.*\}", raw or "", flags=re.S)
            if not m:
                raise
            return json.loads(m.group(0))

    def _sanitize_query(self, query: str, product: ProductQuery) -> str | None:
        query = " ".join((query or "").split())[:520]
        if not query:
            return None
        # Block LLM-invented GTIN/EAN-like values. Product codes like 1001/A5 are not affected.
        allowed = equivalent_gtins(product.ean) if product.ean else set()
        gtin_like = []
        for digits in re.findall(r"\d[\d\s.-]{6,20}\d", query):
            clean = "".join(ch for ch in digits if ch.isdigit())
            if len(clean) in {8, 12, 13, 14} and is_valid_gtin(clean):
                gtin_like.append(clean)
        for gtin in gtin_like:
            if not allowed or gtin not in allowed:
                logger.warning("Rejected LLM query containing non-user-provided GTIN | gtin={} | query={}", gtin, query)
                return None
        return query

    def _fallback_queries(self, state: ProductSearchState, *, stage: str, max_queries: int) -> list[LLMSearchQuery]:
        if stage == "search_feedback":
            out: list[LLMSearchQuery] = []
            # Repair should not keep forcing the requested retailer after scrape evidence
            # shows it is unusable/weak; same-country alternatives come next.
            out.append(LLMSearchQuery(query=self.query_builder.repair_from_state(state, global_fallback=False, include_retailer=False), source="deterministic_feedback_fallback", scope="country_alternative", reason="fallback same-country alternative retailer repair", priority=1))
            out.append(LLMSearchQuery(query=self.query_builder.repair_from_state(state, global_fallback=True, include_retailer=False), source="deterministic_feedback_fallback", scope="global", reason="fallback global repair", priority=2))
            return out[:max_queries]
        return self._fallback_queries_from_product(state.task, max_queries=max_queries, stage=stage)

    def _fallback_queries_from_product(self, product: ProductQuery, *, max_queries: int, stage: str) -> list[LLMSearchQuery]:
        identity = ProductIdentityGraphBuilder().build(product)
        qtext = identity.search_name or product.main_text
        terms = " ".join(identity.must_match_terms[:6])
        out: list[LLMSearchQuery] = []
        priority = 1
        if product.retailer_name:
            rq = self.query_builder.requested_retailer_search(product)
            out.append(LLMSearchQuery(query=rq, source="deterministic_plan_fallback", scope="requested_retailer", reason="requested retailer first-pass evidence search", priority=priority, must_include_ean=bool(product.ean))); priority += 1
        if product.ean:
            out.append(LLMSearchQuery(query=quoted(product.ean), source="deterministic_plan_fallback", scope="country_alternative" if product.retailer_name else "country", reason="exact user-provided EAN identifier search across country retailers", priority=priority, must_include_ean=True)); priority += 1
            out.append(LLMSearchQuery(query=f'{quoted(product.ean)} {quoted(qtext)}', source="deterministic_plan_fallback", scope="country_alternative" if product.retailer_name else "country", reason="EAN plus expanded product identity across country retailers", priority=priority, must_include_ean=True)); priority += 1
        out.append(LLMSearchQuery(query=quoted(qtext), source="deterministic_plan_fallback", scope="country_alternative" if product.retailer_name else "country", reason="exact expanded product phrase across country retailers", priority=priority)); priority += 1
        if terms and terms.lower() != qtext.lower():
            out.append(LLMSearchQuery(query=f'{quoted(qtext)} {terms}', source="deterministic_plan_fallback", scope="country_alternative" if product.retailer_name else "country", reason="expanded identity with critical terms across country retailers", priority=priority)); priority += 1
        out.append(LLMSearchQuery(query=self.query_builder.country_language_search(product, language_index=0, include_retailer=not bool(product.retailer_name)), source="deterministic_plan_fallback", scope="country_alternative" if product.retailer_name else "country", reason="country-language alternative retailer commerce search", priority=priority)); priority += 1
        out.append(LLMSearchQuery(query=self.query_builder.global_fallback(product, include_retailer=False), source="deterministic_plan_fallback", scope="global", reason="global fallback exact-product campaign", priority=priority, must_include_ean=bool(product.ean)))
        return out[:max_queries]

    def _record(self, state: ProductSearchState, call_index: int, stage: str, success: bool, queries: tuple[LLMSearchQuery, ...] | list[LLMSearchQuery], error: str | None, response: LLMResponse | None) -> LLMCallRecord:
        usage = response.usage if response else {}
        return LLMCallRecord(
            row_id=state.task.row_id,
            url="",
            call_index=call_index,
            payload_level=stage,
            image_used=False,
            image_url=None,
            success=success,
            decision="SEARCH_PLAN" if success else "SEARCH_PLAN_FAILED",
            error=error,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
        )
