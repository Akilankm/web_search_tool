from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from src.product_evidence_harness.candidate_store import CandidateStore
from src.product_evidence_harness.config import TournamentConfig
from src.product_evidence_harness.contracts import (
    ActionType,
    AgentAction,
    AgentActionRecord,
    CandidateScorecard,
    OrganicSearchResponse,
    ProductSearchState,
    ScrapeResult,
)
from src.product_evidence_harness.evidence_extractor import EvidenceExtractor
from src.product_evidence_harness.identity_verifier import ProductIdentityVerifier
from src.product_evidence_harness.production_url import ProductionURLAssessment, ProductionURLGate
from src.product_evidence_harness.query_builder import QueryBuilder
from src.product_evidence_harness.ranker import ProductURLRanker
from src.product_evidence_harness.scraper import CrawlScraper
from src.product_evidence_harness.serp_clients import GoogleOrganicSearchClient


@dataclass(frozen=True)
class TournamentQuery:
    query: str
    scope: str
    language_code: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TournamentRound:
    batch_index: int
    winner_url: str | None
    winner_score: float
    production_ready: bool
    status: str
    runner_up_url: str | None = None
    margin: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TournamentResult:
    enabled: bool
    search_credit_limit: int
    search_credits_used: int
    raw_candidate_count: int
    preflight_candidate_count: int
    scraped_candidate_count: int
    champion_url: str | None = None
    champion_score: float = 0.0
    champion_status: str = "NO_PRODUCTION_READY_CHAMPION"
    champion_production_ready: bool = False
    runner_up_url: str | None = None
    champion_margin: float = 0.0
    best_review_candidate_url: str | None = None
    best_review_candidate_score: float = 0.0
    best_review_candidate_status: str = "NO_REVIEW_CANDIDATE"
    search_exhausted: bool = False
    candidate_pool_exhausted: bool = False
    scrape_budget_exhausted: bool = False
    queries: tuple[TournamentQuery, ...] = ()
    rounds: tuple[TournamentRound, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "search_credit_limit": self.search_credit_limit,
            "search_credits_used": self.search_credits_used,
            "raw_candidate_count": self.raw_candidate_count,
            "preflight_candidate_count": self.preflight_candidate_count,
            "scraped_candidate_count": self.scraped_candidate_count,
            "champion_url": self.champion_url,
            "champion_score": self.champion_score,
            "champion_status": self.champion_status,
            "champion_production_ready": self.champion_production_ready,
            "runner_up_url": self.runner_up_url,
            "champion_margin": self.champion_margin,
            "best_review_candidate_url": self.best_review_candidate_url,
            "best_review_candidate_score": self.best_review_candidate_score,
            "best_review_candidate_status": self.best_review_candidate_status,
            "search_exhausted": self.search_exhausted,
            "candidate_pool_exhausted": self.candidate_pool_exhausted,
            "scrape_budget_exhausted": self.scrape_budget_exhausted,
            "queries": [q.to_dict() for q in self.queries],
            "rounds": [r.to_dict() for r in self.rounds],
        }


@dataclass
class CandidateTournamentEngine:
    config: TournamentConfig
    query_builder: QueryBuilder
    organic_client: GoogleOrganicSearchClient
    candidate_store: CandidateStore
    scraper: CrawlScraper
    verifier: ProductIdentityVerifier
    ranker: ProductURLRanker
    evidence_extractor: EvidenceExtractor
    production_gate: ProductionURLGate

    def run(self, state: ProductSearchState) -> TournamentResult:
        if not self.config.enabled:
            result = TournamentResult(False, self.config.max_serp_credits, 0, len(state.candidates), 0, len(state.scrapes))
            setattr(state, "tournament_result", result)
            return result

        logger.info("Tournament mode | row_id={} | max_serp_credits={}", state.task.row_id, self.config.max_serp_credits)
        executed = self._execute_searches(state)
        state.scorecards = self.ranker.score(product=state.task, candidates=state.candidates, scrapes=state.scrapes, verifications=state.verifications)
        ranked_candidates = self._rank_all_candidates(state.scorecards)

        rounds: list[TournamentRound] = []
        for batch_index, batch in enumerate(self._batches(ranked_candidates), start=1):
            if not state.budget.can_scrape():
                break
            self._scrape_batch(state, [c.candidate.url for c in batch], batch_index=batch_index)
            state.scorecards = self.ranker.score(product=state.task, candidates=state.candidates, scrapes=state.scrapes, verifications=state.verifications)
            batch_urls = {c.candidate.url for c in batch}
            refreshed = [c for c in state.scorecards if c.candidate.url in batch_urls]
            winner, assessment = self._winner(refreshed)
            runner_up = self._runner_up(refreshed, winner.candidate.url if winner else None)
            runner_score = self.production_gate.assess_card(runner_up).score if runner_up else 0.0
            margin = round((assessment.score if assessment else 0.0) - runner_score, 4)
            rounds.append(TournamentRound(
                batch_index=batch_index,
                winner_url=winner.candidate.url if winner else None,
                winner_score=assessment.score if assessment else 0.0,
                production_ready=assessment.production_ready if assessment else False,
                status=assessment.status if assessment else "NO_BATCH_WINNER",
                runner_up_url=runner_up.candidate.url if runner_up else None,
                margin=margin,
            ))
            ready_card, ready_assessment = self.production_gate.best_production_card(state)
            if ready_card and ready_assessment and ready_assessment.production_ready:
                state.termination_reason = "tournament_production_ready_champion_found"
                if not self.config.early_stop or margin >= self.config.early_stop_margin:
                    break

        champion_card, champion_assessment = self.production_gate.best_production_card(state)
        review_card, review_assessment = self._winner(state.scorecards)
        runner_up = self._runner_up(state.scorecards, champion_card.candidate.url if champion_card else review_card.candidate.url if review_card else None)
        runner_score = self.production_gate.assess_card(runner_up).score if runner_up else 0.0
        champion_score = champion_assessment.score if champion_assessment else 0.0
        result = TournamentResult(
            enabled=True,
            search_credit_limit=self.config.max_serp_credits,
            search_credits_used=len(executed),
            raw_candidate_count=len(state.candidates),
            preflight_candidate_count=len(ranked_candidates),
            scraped_candidate_count=len(state.scrapes),
            champion_url=champion_card.candidate.url if champion_card else None,
            champion_score=champion_score,
            champion_status=champion_assessment.status if champion_assessment else "NO_PRODUCTION_READY_CHAMPION",
            champion_production_ready=bool(champion_assessment and champion_assessment.production_ready),
            runner_up_url=runner_up.candidate.url if runner_up else None,
            champion_margin=round(champion_score - runner_score, 4) if champion_card else 0.0,
            best_review_candidate_url=review_card.candidate.url if review_card else None,
            best_review_candidate_score=review_assessment.score if review_assessment else 0.0,
            best_review_candidate_status=review_assessment.status if review_assessment else "NO_REVIEW_CANDIDATE",
            search_exhausted=len(executed) >= self.config.max_serp_credits or not state.budget.can_search_organic(),
            candidate_pool_exhausted=len(state.scrapes) >= len(ranked_candidates),
            scrape_budget_exhausted=not state.budget.can_scrape(),
            queries=tuple(executed),
            rounds=tuple(rounds),
        )
        setattr(state, "tournament_result", result)
        logger.info("Tournament done | row_id={} | champion={} | status={} | review_candidate={} | serp_used={} | scraped={}/{}", state.task.row_id, result.champion_url, result.champion_status, result.best_review_candidate_url, result.search_credits_used, result.scraped_candidate_count, result.preflight_candidate_count)
        return result

    def write_artifacts(self, result: TournamentResult, product_dir: Path) -> None:
        product_dir.mkdir(parents=True, exist_ok=True)
        (product_dir / "tournament_bracket.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (product_dir / "tournament_bracket.md").write_text(self._markdown(result) + "\n", encoding="utf-8")
        with (product_dir / "batch_winners.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["batch_index", "winner_url", "winner_score", "production_ready", "status", "runner_up_url", "margin"])
            writer.writeheader()
            for row in result.rounds:
                writer.writerow(row.to_dict())

    def _execute_searches(self, state: ProductSearchState) -> list[TournamentQuery]:
        executed: list[TournamentQuery] = []
        for item in self._queries(state):
            if len(executed) >= self.config.max_serp_credits or not state.budget.can_search_organic():
                break
            state.budget.consume_organic()
            response = self._search(item, state)
            state.queries.append(item.query)
            state.organic_responses.append(response)
            state.candidates = self.candidate_store.merge_organic(state.candidates, response)[: self.config.candidate_pool]
            executed.append(item)
            self._record_search_action(state, item, response, iteration=len(executed))
        return executed

    def _queries(self, state: ProductSearchState) -> list[TournamentQuery]:
        task = state.task
        raw: list[TournamentQuery] = []
        if task.retailer_name:
            raw.append(TournamentQuery(self.query_builder.requested_retailer_search(task), "requested_retailer", task.language_code, "requested_retailer"))
        raw.append(TournamentQuery(self.query_builder.country_language_search(task, language_index=0, include_retailer=False), "country", task.language_code, "country_identity"))
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

    def _search(self, item: TournamentQuery, state: ProductSearchState) -> OrganicSearchResponse:
        country_code = None if item.scope == "global" else state.task.country_code
        return self.organic_client.search(item.query, product=state.task, scope=item.scope, language_code=item.language_code, country_code=country_code)

    def _record_search_action(self, state: ProductSearchState, item: TournamentQuery, response: OrganicSearchResponse, *, iteration: int) -> None:
        state.actions_taken.append(AgentActionRecord(
            iteration=iteration,
            action=AgentAction(
                action_type=ActionType.ORGANIC_SEARCH,
                reason=item.reason,
                query=item.query,
                metadata={"scope": item.scope, "loop_phase": "tournament_search", "reason": item.reason, "language_code": item.language_code},
            ),
            success=response.status.lower() not in {"no results", "error", "failed"},
            output_summary={"result_count": len(response.results), "status": response.status, "scope": item.scope, "reason": item.reason},
            error=None if response.results else response.raw.get("error") if isinstance(response.raw, dict) else None,
        ))

    def _rank_all_candidates(self, cards: list[CandidateScorecard]) -> list[CandidateScorecard]:
        return sorted(cards, key=self._preflight_key, reverse=True)

    @staticmethod
    def _preflight_key(card: CandidateScorecard) -> tuple[float, ...]:
        url = card.candidate.url.lower()
        product_like = 1.0 if any(x in url for x in ("/product", "/produkt", "/p/", "/dp/", "sku", "articulo.mercadolibre", "/itm/", "/item/")) else 0.0
        return (card.ean_score, card.title_score, card.country_score, card.retailer_score, product_like, card.organic_score, card.final_confidence)

    def _batches(self, cards: list[CandidateScorecard]) -> list[list[CandidateScorecard]]:
        size = max(1, self.config.batch_size)
        return [cards[i:i + size] for i in range(0, len(cards), size)]

    def _scrape_batch(self, state: ProductSearchState, urls: list[str], *, batch_index: int) -> None:
        todo: list[str] = []
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
            iteration=1000 + batch_index,
            action=AgentAction(action_type=ActionType.SCRAPE_URL, reason="tournament_batch_scrape", metadata={"scope": "tournament", "loop_phase": "tournament_scrape", "batch_index": batch_index, "url_count": len(todo)}),
            success=any(s.success for s in scrapes),
            output_summary={"url_count": len(todo), "success_count": sum(1 for s in scrapes if s.success), "batch_index": batch_index},
        ))

    def _record_scrape(self, state: ProductSearchState, url: str, scrape: ScrapeResult) -> None:
        state.scrapes[url] = scrape
        state.evidence_cards.append(self.evidence_extractor.from_scrape(scrape))
        verification = self.verifier.verify(state.task, scrape, identity_graph=state.identity_graph)
        state.verifications[url] = verification
        state.detector_findings[url] = list(verification.detector_findings)

    def _winner(self, cards: list[CandidateScorecard]) -> tuple[CandidateScorecard | None, ProductionURLAssessment | None]:
        if not cards:
            return None, None
        assessed = [(card, self.production_gate.assess_card(card)) for card in cards]
        return sorted(assessed, key=lambda p: self._winner_key(p[0], p[1]), reverse=True)[0]

    @staticmethod
    def _winner_key(card: CandidateScorecard, a: ProductionURLAssessment) -> tuple[float, ...]:
        return (
            float(a.production_ready),
            float(a.browser_openable),
            float(a.highly_scrapable),
            float(a.critical_product_evidence_complete),
            float(a.exact_product_match),
            float(card.country_check in {"MATCHED", "NOT_PROVIDED"}),
            float(card.retailer_check == "MATCHED"),
            a.score,
            card.richness_score,
            card.title_score,
            card.final_confidence,
        )

    def _runner_up(self, cards: list[CandidateScorecard], champion_url: str | None) -> CandidateScorecard | None:
        rest = [c for c in cards if c.candidate.url != champion_url]
        return self._winner(rest)[0] if rest else None

    @staticmethod
    def _markdown(result: TournamentResult) -> str:
        lines = [
            "# Candidate Tournament Bracket",
            "",
            f"- **SerpAPI credits:** `{result.search_credits_used}/{result.search_credit_limit}`",
            f"- **Champion:** {result.champion_url or ''}",
            f"- **Champion status:** `{result.champion_status}`",
            f"- **Production ready:** `{result.champion_production_ready}`",
            f"- **Best review candidate:** {result.best_review_candidate_url or ''}",
            f"- **Best review candidate status:** `{result.best_review_candidate_status}`",
            f"- **Runner up:** {result.runner_up_url or ''}",
            f"- **Margin:** `{result.champion_margin}`",
            f"- **Search exhausted:** `{result.search_exhausted}`",
            f"- **Candidate pool exhausted:** `{result.candidate_pool_exhausted}`",
            f"- **Scrape budget exhausted:** `{result.scrape_budget_exhausted}`",
            "",
            "## Queries",
        ]
        for i, q in enumerate(result.queries, 1):
            lines.append(f"{i}. `{q.scope}` / `{q.reason}`: {q.query}")
        lines.extend(["", "## Rounds", "", "| Batch | Winner | Score | Production Ready | Status | Runner Up | Margin |", "|---:|---|---:|---|---|---|---:|"])
        for r in result.rounds:
            lines.append(f"| {r.batch_index} | {r.winner_url or ''} | {r.winner_score:.4f} | `{r.production_ready}` | `{r.status}` | {r.runner_up_url or ''} | {r.margin:.4f} |")
        return "\n".join(lines)
