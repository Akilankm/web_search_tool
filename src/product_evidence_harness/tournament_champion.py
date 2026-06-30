from __future__ import annotations

from dataclasses import replace

from src.product_evidence_harness.contracts import ActionType, AgentAction, AgentActionRecord, CandidateScorecard, ProductSearchState
from src.product_evidence_harness.gtin import is_valid_gtin
from src.product_evidence_harness.production_url import ProductionURLAssessment
from src.product_evidence_harness.tournament import CandidateTournamentEngine, TournamentQuery


class ChampionContractTournamentEngine(CandidateTournamentEngine):
    """Tournament engine aligned to the product_url == champion contract."""

    def _queries(self, state: ProductSearchState) -> list[TournamentQuery]:
        task = state.task if not state.task.ean or is_valid_gtin(state.task.ean) else replace(state.task, ean=None)
        raw: list[TournamentQuery] = []
        if task.retailer_name:
            raw.append(TournamentQuery(self.query_builder.requested_retailer_search(task), "country", task.language_code, "requested_retailer"))
        if task.ean:
            raw.append(TournamentQuery(self.query_builder.country_language_search(task, language_index=0, include_retailer=False), "country", task.language_code, "ean_country"))
        raw.append(TournamentQuery(self.query_builder.country_alternative_search(task, language_index=0), "country", task.language_code, "country_alternatives"))
        if self.query_builder.country_language_count(task) > 1:
            meta = self.query_builder.country_language_metadata(task, 1)
            raw.append(TournamentQuery(self.query_builder.country_alternative_search(task, language_index=1), "country", meta.get("language_code"), "secondary_language"))
        raw.append(TournamentQuery(self.query_builder.global_fallback(task), "global", "en", "global_fallback"))
        out: list[TournamentQuery] = []
        seen: set[str] = set()
        for q in raw:
            key = q.query.strip().lower()
            if key and key not in seen:
                out.append(q)
                seen.add(key)
        return out[: self.config.max_serp_credits]

    def _execute_searches(self, state: ProductSearchState) -> list[TournamentQuery]:
        executed = []
        for item in self._queries(state):
            if len(executed) >= self.config.max_serp_credits or not state.budget.can_search_organic():
                break
            state.budget.consume_organic()
            response = self._search(item, state)
            state.queries.append(item.query)
            state.organic_responses.append(response)
            state.candidates = self.candidate_store.merge_organic(state.candidates, response)[: self.config.candidate_pool]
            state.candidates = self._tag_query_scope(state.candidates, item)
            executed.append(item)
            self._record_search_action(state, item, response)
            if len(state.candidates) >= self.config.candidate_pool:
                break
        return executed

    def _record_search_action(self, state: ProductSearchState, item: TournamentQuery, response) -> None:
        metadata_scope = "requested_retailer" if item.reason == "requested_retailer" else item.scope
        state.actions_taken.append(AgentActionRecord(
            iteration=len(state.actions_taken) + 1,
            action=AgentAction(
                action_type=ActionType.ORGANIC_SEARCH,
                reason=f"tournament_{item.reason}",
                query=item.query,
                metadata={
                    "scope": metadata_scope,
                    "search_scope": item.scope,
                    "loop_phase": "tournament",
                    "language_code": item.language_code,
                    "tournament_reason": item.reason,
                },
            ),
            success=response.status.lower() in {"success", "ok"} or bool(response.results),
            output_summary={
                "result_count": len(response.results),
                "candidate_count": len(state.candidates),
                "status": response.status,
                "scope": item.scope,
                "reason": item.reason,
            },
        ))

    @staticmethod
    def _tag_query_scope(candidates, item: TournamentQuery):
        tagged = []
        reason_tag = f"tournament_reason:{item.reason}"
        scope_tag = f"tournament_scope:{item.scope}"
        for candidate in candidates:
            if item.query in (candidate.query_sources or ()):
                tagged.append(replace(candidate, source_types=tuple(sorted(set(candidate.source_types or ()) | {reason_tag, scope_tag}))))
            else:
                tagged.append(candidate)
        return tagged

    def _scrape_batch(self, state: ProductSearchState, urls: list[str]) -> None:
        todo = []
        for url in urls:
            if url in state.scrapes:
                continue
            if not state.budget.can_scrape():
                break
            state.budget.consume_scrape()
            todo.append(url)
        if not todo:
            return
        scrapes = self.scraper.scrape_many(todo, product=state.task) if hasattr(self.scraper, "scrape_many") else [self.scraper.scrape(url, product=state.task) for url in todo]
        for url, scrape in zip(todo, scrapes):
            self._record_scrape(state, url, scrape)
        state.actions_taken.append(AgentActionRecord(
            iteration=len(state.actions_taken) + 1,
            action=AgentAction(action_type=ActionType.SCRAPE_URL, reason="tournament_batch_scrape", metadata={"scope": "tournament_batch", "loop_phase": "tournament"}),
            success=True,
            output_summary={"url_count": len(todo), "scraped_count": len(scrapes)},
        ))

    @staticmethod
    def _winner_key(card: CandidateScorecard, a: ProductionURLAssessment) -> tuple[float, ...]:
        exact_like = float(card.validation_status == "VERIFIED" or card.exact_product_check == "EXACT_MATCH" or card.title_score >= 0.75)
        variant_safe = float(card.variant_check != "CONFLICT")
        requested = float(card.retailer_check == "MATCHED")
        country = float(card.country_check in {"MATCHED", "NOT_PROVIDED"})
        return (
            float(a.production_ready),
            exact_like,
            card.title_score,
            variant_safe,
            requested,
            country,
            float(a.highly_scrapable),
            float(a.browser_openable),
            a.score,
            card.final_confidence,
            card.richness_score,
        )

    @staticmethod
    def _markdown(result) -> str:
        lines = [
            "# Candidate Tournament Bracket",
            "",
            "`product_url` is the tournament champion. Runner-ups are supporting evidence only.",
            "",
            f"- **SerpAPI credits:** `{result.search_credits_used}/{result.search_credit_limit}`",
            f"- **Champion:** {result.champion_url or ''}",
            f"- **Champion status:** `{result.champion_status}`",
            f"- **Production ready:** `{result.champion_production_ready}`",
            f"- **Runner up:** {result.runner_up_url or ''}",
            f"- **Margin:** `{result.champion_margin}`",
            "",
            "## Queries",
        ]
        for i, q in enumerate(result.queries, 1):
            lines.append(f"{i}. `{q.scope}` / `{q.reason}`: {q.query}")
        lines.extend(["", "## Rounds", "", "| Batch | Winner | Score | Production Ready | Status | Runner Up | Margin |", "|---:|---|---:|---|---|---|---:|"])
        for r in result.rounds:
            lines.append(f"| {r.batch_index} | {r.winner_url or ''} | {r.winner_score:.4f} | `{r.production_ready}` | `{r.status}` | {r.runner_up_url or ''} | {r.margin:.4f} |")
        return "\n".join(lines)
