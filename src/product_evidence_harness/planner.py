from __future__ import annotations

from dataclasses import dataclass

from src.product_evidence_harness.config import HarnessConfig
from src.product_evidence_harness.constants import TERMINATION_BUDGET_EXHAUSTED, TERMINATION_VERIFIED
from src.product_evidence_harness.contracts import ActionType, AgentAction, LLMSearchQuery, ProductSearchState
from src.product_evidence_harness.country_profiles import CountryProfileRegistry
from src.product_evidence_harness.query_builder import QueryBuilder
from src.product_evidence_harness.retailer_strategy import (
    candidate_matches_requested_retailer,
    requested_retailer_metrics,
    requested_retailer_search_attempted,
)


@dataclass(frozen=True)
class HarnessPlanner:
    """LLM-controlled iterative discovery planner.

    The planner is deliberately not a linear pipeline.  After the initial
    product-identity/search plan, every iteration chooses the next best action
    from the current state:

        search -> candidate pool -> scrape -> score -> LLM judge -> repair -> search again

    The feedback edge is the important part: weak/non-scrapable/wrong-variant
    evidence changes the next query/fallback decision inside the same bounded
    run.  SerpAPI and crawl4ai remain tools; the LLM plans, diagnoses, and
    adjudicates within a strict per-product budget.
    """

    config: HarnessConfig
    query_builder: QueryBuilder
    country_profiles: CountryProfileRegistry

    def next_action(self, state: ProductSearchState) -> AgentAction:
        best = state.best_scorecard()
        if best and self._is_verified_usable(best):
            return AgentAction(ActionType.FINISH, TERMINATION_VERIFIED)

        # 0) LLM creates the product-identity/search campaign before any search.
        if self.config.enable_llm_search_planning and not self._llm_stage_done(state, "initial_search_plan"):
            if self._llm_calls_remaining(state) > self._reserved_llm_calls(state):
                return AgentAction(
                    ActionType.LLM_SEARCH_PLAN,
                    "LLM creates product-identity graph and retailer-first/country/global campaign",
                    metadata={"kind": "llm_search_plan", "loop_phase": "plan"},
                )

        # 1) If a requested retailer was supplied, it is a preferred evidence source,
        # not a hard constraint. First attempt that retailer in-country and scrape its
        # candidates enough to determine whether it is evidence-usable.
        if self._requested_retailer_first_active(state):
            requested_plan = self._next_planned_query(state, include_global=False, only_scopes={"requested_retailer"})
            if requested_plan and state.budget.can_search_organic():
                return self._organic_from_plan(requested_plan, loop_phase="requested_retailer_search")
            if not requested_retailer_search_attempted(state) and state.budget.can_search_organic():
                return AgentAction(
                    ActionType.ORGANIC_SEARCH,
                    "requested retailer first-pass search to test scrape-usable evidence",
                    query=self.query_builder.requested_retailer_search(state.task),
                    metadata={"kind": "requested_retailer_first", "scope": "requested_retailer", "language_code": state.task.language_code, "loop_phase": "requested_retailer_search"},
                )
            next_requested = self._next_unscraped_urls(state, scope="requested_retailer", limit=self.config.max_requested_retailer_scrapes_per_batch)
            if next_requested and not self._requested_retailer_should_escape(state) and state.budget.can_scrape():
                return self._scrape_action(
                    next_requested,
                    reason="scrape requested-retailer candidates concurrently to assess product evidence usability",
                    scope="requested_retailer",
                    loop_phase="scrape_requested_retailer",
                )

        # 2) Judge scraped promising candidates before continuing. A rejection or
        # insufficient-evidence judgement can trigger feedback/repair while budget remains.
        if self._should_adjudicate_now(state):
            return AgentAction(
                ActionType.LLM_EXACT_ADJUDICATION,
                "LLM judges scraped evidence inside the loop before deciding repair/fallback",
                metadata={"kind": "llm_exact_adjudication", "loop_phase": "judge"},
            )

        # 3) If evidence shows weakness or LLM rejected/flagged ambiguity, ask the
        # LLM to repair the search. For requested-retailer failures, feedback should
        # usually produce country_alternative queries rather than keep forcing retailer.
        if self._should_request_llm_feedback(state):
            return AgentAction(
                ActionType.LLM_SEARCH_FEEDBACK,
                "LLM diagnoses failed evidence and creates retailer-escape/country/global repair queries",
                metadata={"kind": "llm_search_feedback", "loop_phase": "diagnose_repair"},
            )

        # 4) Execute queued repair queries before scraping stale lower-quality candidates.
        repair_query = self._next_planned_query(state, include_global=True, preferred_sources={"llm_search_feedback", "deterministic_feedback_fallback"})
        if repair_query and state.budget.can_search_organic():
            return self._organic_from_plan(repair_query, loop_phase="repair_search")

        # 5) Country alternative phase: once requested retailer is unusable/not exact,
        # remove the requested retailer constraint and search other retailers in-country.
        if self._country_alternative_allowed(state):
            scope = "country_alternative" if state.task.retailer_name else "country"
            next_country_alt = self._next_unscraped_urls(state, scope=scope, limit=self.config.max_country_scrapes_per_batch)
            if next_country_alt and state.budget.can_scrape():
                return self._scrape_action(
                    next_country_alt,
                    reason="scrape same-country candidates concurrently so free scrape evidence is mined before spending another search",
                    scope=scope,
                    loop_phase="scrape_country_alternative" if state.task.retailer_name else "scrape_country",
                )

            planned_country_alt = self._next_planned_query(state, include_global=False, only_scopes={"country", "country_alternative"})
            if planned_country_alt and state.budget.can_search_organic():
                return self._organic_from_plan(planned_country_alt, loop_phase="country_alternative_search" if state.task.retailer_name else "country_search")

            if state.task.retailer_name and not self._country_alternative_search_done(state) and state.budget.can_search_organic():
                return AgentAction(
                    ActionType.ORGANIC_SEARCH,
                    "requested retailer was not enough; search other retailers within the same country",
                    query=self.query_builder.country_alternative_search(state.task, language_index=0),
                    metadata={"kind": "country_alternative", "scope": "country_alternative", "language_code": state.task.language_code, "loop_phase": "country_alternative_search"},
                )

        # 6) Deterministic country-language fallback when LLM planning is disabled or failed.
        if not self.config.enable_llm_search_planning:
            idx = self._next_country_language_index(state)
            if idx is not None and state.budget.can_search_organic():
                meta = self.query_builder.country_language_metadata(state.task, idx)
                meta["loop_phase"] = "country_search"
                if state.task.retailer_name and self._requested_retailer_should_escape(state):
                    meta["scope"] = "country_alternative"
                    meta["kind"] = "country_alternative"
                    query = self.query_builder.country_alternative_search(state.task, language_index=idx)
                else:
                    query = self.query_builder.country_language_search(state.task, language_index=idx)
                return AgentAction(
                    ActionType.ORGANIC_SEARCH,
                    "country/language-priority search",
                    query=query,
                    metadata=meta,
                )

        # 7) AI Mode is an addon discovery tool. Use it when organic/scrape evidence is weak.
        if (
            self.config.budget.max_ai_mode_searches > 0
            and state.budget.can_search_ai()
            and not self._ai_discovery_done(state)
            and self._should_use_ai_discovery(state)
        ):
            scope = "country_alternative" if self._requested_retailer_should_escape(state) else "requested_retailer" if state.task.retailer_name else "country"
            return AgentAction(
                ActionType.AI_MODE_SEARCH,
                "SerpAPI AI Mode addon discovery after weak organic evidence",
                query=self.query_builder.ai_discovery_prompt(state.task, allow_global_fallback=self.config.policy.allow_global_fallback),
                metadata={"kind": "ai_discovery", "scope": scope, "loop_phase": "addon_discovery"},
            )

        # 8) Global fallback: only after requested-retailer and same-country alternatives
        # have not produced exact scrape-usable evidence.
        next_global_url = self._next_unscraped_urls(state, scope="global", limit=self.config.max_global_scrapes_per_batch)
        if next_global_url and state.budget.can_scrape():
            return self._scrape_action(
                next_global_url,
                reason="scrape global candidates concurrently after requested retailer/country evidence failed",
                scope="global",
                loop_phase="scrape_global",
            )

        planned_global = self._next_planned_query(state, include_global=True, only_global=True)
        if planned_global and state.budget.can_search_organic():
            return self._organic_from_plan(planned_global, loop_phase="global_fallback_search")

        if state.budget.can_search_organic() and not self._global_search_done(state):
            return AgentAction(
                ActionType.ORGANIC_SEARCH,
                "deterministic global fallback search after requested retailer/country loop exhausted",
                query=self.query_builder.global_fallback(state.task, include_retailer=False),
                metadata={"kind": "global_fallback", "scope": "global", "language_code": self.config.global_fallback_language_code, "loop_phase": "global_fallback_search"},
            )

        if state.budget.exhausted():
            return AgentAction(ActionType.FINISH, TERMINATION_BUDGET_EXHAUSTED)
        return AgentAction(ActionType.FINISH, "no_more_actions")

    def _organic_from_plan(self, planned: LLMSearchQuery, *, loop_phase: str) -> AgentAction:
        return AgentAction(
            ActionType.ORGANIC_SEARCH,
            planned.reason or "execute planned query",
            query=planned.query,
            metadata={
                "kind": planned.source,
                "scope": planned.scope,
                "reason": planned.reason,
                "priority": planned.priority,
                "language_code": planned.language_code,
                "language_name": planned.language_name,
                "must_include_ean": planned.must_include_ean,
                "loop_phase": loop_phase,
            },
        )

    def _scrape_action(self, urls: list[str], *, reason: str, scope: str, loop_phase: str) -> AgentAction:
        urls = list(dict.fromkeys(urls))
        return AgentAction(
            ActionType.SCRAPE_URL,
            reason,
            url=urls[0] if urls else None,
            metadata={"scope": scope, "loop_phase": loop_phase, "urls": tuple(urls), "batch_size": len(urls)},
        )

    def _is_verified_usable(self, card) -> bool:
        s = card.scrape
        v = card.verification
        if not s or not v:
            return False
        if not (s.scraped and s.success and s.reachable and s.is_scrapable and s.looks_like_product_page):
            return False
        if card.hard_failures:
            return False
        if self.config.policy.require_llm_exact_match_for_final or self.config.llm_require_exact_match_for_final:
            return card.llm_decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"} and card.llm_exact_product_match
        return (
            v.identity_status == "VERIFIED"
            and v.exact_product_check in {"EXACT_MATCH", "UNKNOWN"}
            and v.variant_check != "CONFLICT"
        )

    def _llm_calls_remaining(self, state: ProductSearchState) -> int:
        return max(0, self.config.llm_max_calls_per_product - len(state.llm_call_records))

    def _reserved_llm_calls(self, state: ProductSearchState) -> int:
        if not self.config.reserve_llm_call_for_adjudication or not self.config.enable_llm_adjudication:
            return 0
        # Reserve one adjudication call until an exact-product judgement has accepted
        # a final candidate. A rejected/insufficient judgement should still leave
        # budget for a later repaired candidate to be judged.
        return 0 if any(j.accepted_for_final for j in state.llm_judgements.values()) else 1

    def _llm_stage_done(self, state: ProductSearchState, stage: str) -> bool:
        return any(p.stage == stage for p in state.llm_search_plans)

    def _next_planned_query(
        self,
        state: ProductSearchState,
        *,
        include_global: bool = False,
        only_global: bool = False,
        only_scopes: set[str] | None = None,
        preferred_sources: set[str] | None = None,
    ) -> LLMSearchQuery | None:
        executed = set(state.queries)
        in_progress = {
            r.action.query for r in state.actions_taken
            if r.action.action_type == ActionType.ORGANIC_SEARCH and r.action.query
        }
        for query in sorted(state.planned_search_queries, key=lambda q: (q.priority, q.source, q.query)):
            if query.query in executed or query.query in in_progress:
                continue
            scope = str(query.scope).lower()
            if only_global and scope != "global":
                continue
            if not include_global and scope == "global":
                continue
            if only_scopes and scope not in only_scopes:
                continue
            if preferred_sources and query.source not in preferred_sources:
                continue
            return query
        return None

    def _should_adjudicate_now(self, state: ProductSearchState) -> bool:
        if not self.config.enable_llm_adjudication or self._llm_calls_remaining(state) <= 0:
            return False
        if not state.scorecards:
            return False
        for card in state.scorecards[: max(1, self.config.llm_adjudicate_top_k)]:
            s = card.scrape
            if not s or not (s.scraped and s.success and s.reachable and s.is_scrapable and s.looks_like_product_page):
                continue
            if card.llm_used or card.candidate.url in state.llm_judgements:
                continue
            # Exact/probable candidates, ambiguous variants, and rich weak candidates all deserve
            # a judgement because the judgement can steer repair inside the loop.
            if card.validation_status == "VERIFIED" or not card.hard_failures or card.title_score >= 0.45 or card.richness_score >= 0.45:
                return True
        return False

    def _should_request_llm_feedback(self, state: ProductSearchState) -> bool:
        if not self.config.enable_llm_search_feedback:
            return False
        if self._llm_feedback_count(state) >= self.config.llm_search_feedback_max_rounds:
            return False
        if self._next_planned_query(state, include_global=True, preferred_sources={"llm_search_feedback", "deterministic_feedback_fallback"}):
            return False
        # Keep at least one call for later adjudication unless at least one judgement already exists.
        if self._llm_calls_remaining(state) <= self._reserved_llm_calls(state):
            return False
        if not state.candidates and state.budget.organic_used >= 1:
            return True
        if not state.scrapes:
            return False

        # If any LLM judgement already accepted an exact candidate, no repair is needed.
        if any(j.accepted_for_final for j in state.llm_judgements.values()):
            return False

        # Ask for repair after explicit LLM rejection/insufficient evidence.
        if state.llm_judgements and any(j.decision in {"SIBLING_VARIANT", "WRONG_PRODUCT", "INSUFFICIENT_EVIDENCE", "NON_PRODUCT_PAGE", "UNSCRAPABLE", "LLM_FAILED"} for j in state.llm_judgements.values()):
            return True

        # Ask for repair when all scraped top candidates are unusable, hard-conflicted,
        # weak, not product pages, or non-scrapable.
        top = state.scorecards[:5]
        if top and all(self._card_is_loop_failure(c) for c in top if c.scrape):
            return True
        return False

    def _card_is_loop_failure(self, card) -> bool:
        s = card.scrape
        if not s:
            return False
        if not (s.scraped and s.success and s.reachable and s.is_scrapable and s.looks_like_product_page):
            return True
        if card.hard_failures:
            return True
        if card.validation_status != "VERIFIED":
            return True
        if (self.config.policy.require_llm_exact_match_for_final or self.config.llm_require_exact_match_for_final or self.config.enable_llm_adjudication):
            return not (card.llm_decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"} and card.llm_exact_product_match)
        return False

    def _should_use_ai_discovery(self, state: ProductSearchState) -> bool:
        if not state.candidates:
            return True
        if not state.scrapes:
            return False
        top = state.scorecards[:5]
        if not top:
            return False
        return all((not c.scrape) or (not c.scrape.is_scrapable) or c.hard_failures or c.validation_status != "VERIFIED" for c in top)

    def _llm_feedback_count(self, state: ProductSearchState) -> int:
        return sum(1 for p in state.llm_search_plans if p.stage == "search_feedback")

    def _requested_retailer_first_active(self, state: ProductSearchState) -> bool:
        return bool(
            self.config.policy.requested_retailer_first
            and state.task.retailer_name
            and not self._requested_retailer_has_exact(state)
            and not self._requested_retailer_should_escape(state)
        )

    def _requested_retailer_has_exact(self, state: ProductSearchState) -> bool:
        return any(
            c.retailer_check == "MATCHED" and self._is_verified_usable(c)
            for c in state.scorecards
        )

    def _requested_retailer_should_escape(self, state: ProductSearchState) -> bool:
        if not state.task.retailer_name:
            return False
        metrics = requested_retailer_metrics(
            state,
            min_scrapes_for_escape=self.config.policy.requested_retailer_min_scrapes_for_escape,
            min_richness_for_evidence=self.config.policy.requested_retailer_min_richness_for_evidence,
        )
        # Do not escape before the first requested retailer search has happened or while
        # there are still requested-retailer candidates waiting for scrape evidence.
        if metrics.requested_retailer_scrapability_status in {"NOT_PROVIDED", "NOT_ATTEMPTED", "CANDIDATES_FOUND_NOT_SCRAPED", "SCRAPABILITY_CHECK_IN_PROGRESS"}:
            return False
        if metrics.requested_retailer_scrapability_status == "SCRAPABLE_RICH_BUT_NOT_EXACT":
            # If the requested retailer was scrapable/rich but no exact product was found,
            # escape once all known requested-retailer candidates have been mined.
            return self._next_unscraped_url(state, scope="requested_retailer") is None
        return metrics.should_escape

    def _country_alternative_allowed(self, state: ProductSearchState) -> bool:
        if not state.task.retailer_name:
            return True
        return self._requested_retailer_should_escape(state) or self._country_alternative_search_done(state)

    def _country_alternative_search_done(self, state: ProductSearchState) -> bool:
        return any(
            r.action.action_type == ActionType.ORGANIC_SEARCH
            and r.action.metadata.get("scope") in {"country_alternative", "country"}
            and r.action.metadata.get("scope") != "requested_retailer"
            for r in state.actions_taken
        )

    def _next_unscraped_url(self, state: ProductSearchState, *, scope: str) -> str | None:
        urls = self._next_unscraped_urls(state, scope=scope, limit=1)
        return urls[0] if urls else None

    def _next_unscraped_urls(self, state: ProductSearchState, *, scope: str, limit: int) -> list[str]:
        scraped = set(state.scrapes)
        ranked = [card.candidate for card in state.scorecards] or state.candidates
        remaining_budget = max(0, getattr(state.budget, "max_scrapes", 0) - getattr(state.budget, "scrape_used", 0))
        cap = max(1, min(limit, remaining_budget or limit))
        urls: list[str] = []
        for candidate in ranked:
            if candidate.url in scraped or candidate.url in urls:
                continue
            is_country = self.country_profiles.domain_matches_country(candidate.url, state.task.country_code)
            is_requested = candidate_matches_requested_retailer(candidate, state.task.retailer_name)
            if scope == "requested_retailer" and is_requested:
                urls.append(candidate.url)
            elif scope == "country_alternative" and is_country and not is_requested:
                urls.append(candidate.url)
            elif scope == "country" and is_country:
                urls.append(candidate.url)
            elif scope == "global" and not is_country:
                urls.append(candidate.url)
            if len(urls) >= cap:
                break
        return urls

    def _next_country_language_index(self, state: ProductSearchState) -> int | None:
        done = {
            int(record.action.metadata.get("language_index"))
            for record in state.actions_taken
            if record.action.action_type == ActionType.ORGANIC_SEARCH
            and record.action.metadata.get("kind") == "country_language"
            and record.action.metadata.get("language_index") is not None
        }
        total = self.query_builder.country_language_count(state.task)
        reserve_for_fallback = 1 if self.config.policy.allow_global_fallback else 0
        max_language_searches = max(1, self.config.budget.max_organic_searches - reserve_for_fallback)
        for idx in range(min(total, max_language_searches)):
            if idx not in done:
                return idx
        return None

    def _global_search_done(self, state: ProductSearchState) -> bool:
        return any(
            r.action.action_type == ActionType.ORGANIC_SEARCH
            and r.action.metadata.get("scope") == "global"
            for r in state.actions_taken
        )

    def _ai_discovery_done(self, state: ProductSearchState) -> bool:
        return any(r.action.action_type == ActionType.AI_MODE_SEARCH and r.action.metadata.get("kind") == "ai_discovery" for r in state.actions_taken)
