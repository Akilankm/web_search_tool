from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.product_evidence_harness.candidate_store import CandidateStore
from src.product_evidence_harness.contracts import ActionType, AgentAction, ProductSearchState
from src.product_evidence_harness.evidence_extractor import EvidenceExtractor
from src.product_evidence_harness.identity_verifier import ProductIdentityVerifier
from src.product_evidence_harness.llm.search_planner import LLMSearchPlanner
from src.product_evidence_harness.llm.adjudicator import ExactProductLLMAdjudicator
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.ranker import ProductURLRanker
from src.product_evidence_harness.scraper import CrawlScraper
from src.product_evidence_harness.serp_clients import GoogleAIModeClient, GoogleOrganicSearchClient


@dataclass
class HarnessExecutor:
    organic_client: GoogleOrganicSearchClient
    ai_client: GoogleAIModeClient
    scraper: CrawlScraper
    candidate_store: CandidateStore
    verifier: ProductIdentityVerifier
    ranker: ProductURLRanker
    evidence_extractor: EvidenceExtractor
    llm_search_planner: LLMSearchPlanner | None = None
    llm_adjudicator: ExactProductLLMAdjudicator | None = None

    def execute(self, action: AgentAction, state: ProductSearchState) -> dict:
        logger.info("Executing action | type={} | reason={}", action.action_type.value, action.reason)
        if action.action_type == ActionType.LLM_SEARCH_PLAN:
            return self._llm_search_plan(action, state)
        if action.action_type == ActionType.LLM_SEARCH_FEEDBACK:
            return self._llm_search_feedback(action, state)
        if action.action_type == ActionType.LLM_EXACT_ADJUDICATION:
            return self._llm_exact_adjudication(action, state)
        if action.action_type == ActionType.ORGANIC_SEARCH:
            return self._organic(action, state)
        if action.action_type == ActionType.AI_MODE_SEARCH:
            return self._ai(action, state)
        if action.action_type == ActionType.SCRAPE_URL:
            return self._scrape(action, state)
        if action.action_type == ActionType.FINISH:
            state.termination_reason = action.reason
            return {"finished": True, "reason": action.reason}
        raise ValueError(f"Unsupported action type: {action.action_type}")

    def refresh_scores(self, state: ProductSearchState) -> None:
        state.scorecards = self.ranker.score(
            product=state.task,
            candidates=state.candidates,
            scrapes=state.scrapes,
            verifications=state.verifications,
        )

    def _llm_search_plan(self, action: AgentAction, state: ProductSearchState) -> dict:
        if not self.llm_search_planner:
            raise ValueError("LLM search planner not configured")
        plan, record = self.llm_search_planner.plan_initial(state)
        state.llm_search_plans.append(plan)
        state.llm_call_records.append(record)
        # Feed the LLM identity interpretation back into the deterministic
        # identity graph. This closes the previous gap where LLM planned search
        # but detectors still used only the raw input text.
        state.identity_graph = ProductIdentityGraphBuilder().build(state.task, llm_plan=plan)
        state.planned_search_queries.extend(plan.queries)
        return {
            "stage": plan.stage,
            "success": plan.success,
            "queries_added": len(plan.queries),
            "expanded_main_text": plan.expanded_main_text,
            "reasoning": plan.reasoning,
            "error": plan.error,
        }

    def _llm_search_feedback(self, action: AgentAction, state: ProductSearchState) -> dict:
        if not self.llm_search_planner:
            raise ValueError("LLM search planner not configured")
        plan, record = self.llm_search_planner.plan_feedback(state)
        state.llm_search_plans.append(plan)
        state.llm_call_records.append(record)
        if plan.success:
            state.identity_graph = ProductIdentityGraphBuilder().build(state.task, llm_plan=plan)
        # Deduplicate against already executed or queued queries.
        existing = set(state.queries) | {q.query for q in state.planned_search_queries}
        added = []
        for q in plan.queries:
            if q.query not in existing:
                state.planned_search_queries.append(q)
                existing.add(q.query)
                added.append(q)
        return {
            "stage": plan.stage,
            "success": plan.success,
            "queries_added": len(added),
            "expanded_main_text": plan.expanded_main_text,
            "reasoning": plan.reasoning,
            "error": plan.error,
        }


    def _llm_exact_adjudication(self, action: AgentAction, state: ProductSearchState) -> dict:
        if not self.llm_adjudicator:
            raise ValueError("LLM adjudicator not configured")
        before = len(state.llm_judgements)
        calls_before = len(state.llm_call_records)
        self.llm_adjudicator.adjudicate_state(state)
        # Refresh rank order/reasons after LLM judgement attachment.
        state.scorecards = sorted(
            state.scorecards,
            key=lambda c: (
                1 if c.llm_decision == "EXACT_MATCH" else 0,
                1 if c.llm_decision == "EXACT_MATCH_WITH_WARNING" else 0,
                1 if c.country_check in {"MATCHED", "NOT_PROVIDED"} else 0,
                1 if not c.hard_failures else 0,
                c.final_confidence,
                c.richness_score,
            ),
            reverse=True,
        )
        return {
            "judgements_before": before,
            "judgements_after": len(state.llm_judgements),
            "llm_calls_added": len(state.llm_call_records) - calls_before,
        }

    def _organic(self, action: AgentAction, state: ProductSearchState) -> dict:
        state.budget.consume_organic()
        scope = str(action.metadata.get("scope") or "country")
        language_code = action.metadata.get("language_code")
        country_code = None if scope == "global" else state.task.country_code
        try:
            response = self.organic_client.search(action.query or "", product=state.task, scope=scope, language_code=language_code, country_code=country_code)
        except TypeError:
            # Test doubles / old adapters may not yet accept execution-context kwargs.
            response = self.organic_client.search(action.query or "", product=state.task)
        state.queries.append(action.query or "")
        state.organic_responses.append(response)
        before = len(state.candidates)
        state.candidates = self.candidate_store.merge_organic(state.candidates, response)
        self.refresh_scores(state)
        return {"query": action.query, "scope": scope, "language_code": language_code, "results": len(response.results), "candidates_before": before, "candidates_after": len(state.candidates)}

    def _ai(self, action: AgentAction, state: ProductSearchState) -> dict:
        state.budget.consume_ai()
        scope = str(action.metadata.get("scope") or "country")
        language_code = action.metadata.get("language_code")
        country_code = None if scope == "global" else state.task.country_code
        try:
            response = self.ai_client.search(action.query or "", product=state.task, scope=scope, language_code=language_code, country_code=country_code)
        except TypeError:
            response = self.ai_client.search(action.query or "", product=state.task)
        state.queries.append(action.query or "")
        state.ai_responses.append(response)
        before = len(state.candidates)
        state.candidates = self.candidate_store.merge_ai(state.candidates, response)
        self.refresh_scores(state)
        return {"scope": scope, "language_code": language_code, "references": len(response.references), "candidates_before": before, "candidates_after": len(state.candidates)}

    def _scrape(self, action: AgentAction, state: ProductSearchState) -> dict:
        if not action.url:
            raise ValueError("scrape action requires url")
        state.budget.consume_scrape()
        scrape = self.scraper.scrape(action.url, product=state.task)
        state.scrapes[action.url] = scrape
        evidence = self.evidence_extractor.from_scrape(scrape)
        state.evidence_cards.append(evidence)
        verification = self.verifier.verify(state.task, scrape, identity_graph=state.identity_graph)
        state.verifications[action.url] = verification
        state.detector_findings[action.url] = list(verification.detector_findings)
        self.refresh_scores(state)
        return {"url": action.url, "scrapable": scrape.is_scrapable, "identity": verification.identity_status, "richness": scrape.richness_score}
