from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any

from loguru import logger

from src.product_evidence_harness.config import HarnessConfig
from src.product_evidence_harness.contracts import CandidateScorecard, LLMCallRecord, LLMJudgement, ProductSearchState
from src.product_evidence_harness.llm.prompts import ALLOWED_DECISIONS, SYSTEM_PROMPT_EXACT_PRODUCT_JUDGE, build_adjudication_prompt
from src.product_evidence_harness.llm.service import LLMResponse, LLMService, get_llm_service


PAYLOAD_FULL_IMAGE = "full_text_with_image"
PAYLOAD_COMPACT_IMAGE = "compact_text_with_image"
PAYLOAD_COMPACT_TEXT = "compact_text_only"
PAYLOAD_MINIMAL_TEXT = "minimal_text_only"


@dataclass
class ExactProductLLMAdjudicator:
    """Budgeted exact-product judge using Azure OpenAI.

    Constraints enforced:
    - max N calls per product, default 4
    - one candidate per call
    - at most one image per call
    - payload reduction on gateway/model rejection
    - no raw image dump; image is used only if sent to LLM
    """

    config: HarnessConfig
    service: LLMService | None = None

    def __post_init__(self) -> None:
        if self.service is None:
            self.service = get_llm_service()

    def adjudicate_state(self, state: ProductSearchState) -> ProductSearchState:
        if not self.config.enable_llm_adjudication:
            return state
        max_calls = max(0, self.config.llm_max_calls_per_product - len(state.llm_call_records))
        if max_calls <= 0:
            logger.info("LLM adjudication skipped | row_id={} | no LLM call budget remaining", state.task.row_id)
            return state

        promising = self._promising_cards(state.scorecards)[: max(1, self.config.llm_adjudicate_top_k)]
        if not promising:
            logger.info("LLM adjudication skipped | row_id={} | no promising scraped candidates", state.task.row_id)
            return state

        calls_used = 0
        updated_cards: list[CandidateScorecard] = []
        judgement_by_url = dict(state.llm_judgements)
        for card in state.scorecards:
            if card not in promising:
                updated_cards.append(card)
                continue
            if calls_used >= max_calls:
                updated_cards.append(card)
                continue
            judgement, records, consumed = self._adjudicate_card(state, card, starting_call_index=len(state.llm_call_records) + calls_used + 1, calls_remaining=max_calls - calls_used)
            calls_used += consumed
            state.llm_call_records.extend(records)
            judgement_by_url[card.candidate.url] = judgement
            updated_cards.append(self._attach_judgement(card, judgement))
            # Stop early when a country-specific exact match is confirmed.
            if judgement.accepted_for_final and card.country_check in {"MATCHED", "NOT_PROVIDED"}:
                updated_cards.extend([c for c in state.scorecards if c not in promising and c not in updated_cards])
                break

        # Ensure cards not iterated because of early break are preserved, and keep rank order with LLM acceptance first.
        present = {c.candidate.url for c in updated_cards}
        for card in state.scorecards:
            if card.candidate.url not in present:
                updated_cards.append(card)
        state.scorecards = sorted(updated_cards, key=self._llm_sort_key, reverse=True)
        state.llm_judgements = judgement_by_url
        logger.info("LLM adjudication completed | row_id={} | calls_used={}", state.task.row_id, calls_used)
        return state

    def _promising_cards(self, cards: list[CandidateScorecard]) -> list[CandidateScorecard]:
        candidates = []
        for card in cards:
            s = card.scrape
            if not s or not s.scraped or not s.reachable or not s.success or not s.is_scrapable:
                continue
            if not s.looks_like_product_page:
                continue
            if card.hard_failures and card.verification and card.verification.variant_check == "CONFLICT":
                # Still allow LLM for top sibling ambiguity if text evidence is close.
                if card.title_score < 0.55:
                    continue
            candidates.append(card)
        return sorted(candidates, key=lambda c: (c.country_check == "MATCHED", c.final_confidence, c.richness_score), reverse=True)

    def _adjudicate_card(self, state: ProductSearchState, card: CandidateScorecard, *, starting_call_index: int, calls_remaining: int) -> tuple[LLMJudgement, list[LLMCallRecord], int]:
        assert card.scrape is not None
        image_url = self._select_one_image(card) if self.config.llm_use_images else None
        levels = []
        if image_url and self.config.llm_one_image_per_call:
            levels.extend([PAYLOAD_FULL_IMAGE, PAYLOAD_COMPACT_IMAGE])
        levels.extend([PAYLOAD_COMPACT_TEXT, PAYLOAD_MINIMAL_TEXT])
        if not self.config.llm_payload_reduction_enabled:
            levels = levels[:1]

        records: list[LLMCallRecord] = []
        last_error: str | None = None
        raw = ""
        for offset, level in enumerate(levels[:calls_remaining]):
            call_index = starting_call_index + offset
            use_image = level.endswith("with_image") and bool(image_url)
            prompt = build_adjudication_prompt(
                product=state.task,
                card=card,
                payload_level=level,
                image_url=image_url if use_image else None,
            )
            try:
                response = self.service.predict(
                    text=prompt,
                    system_prompt=SYSTEM_PROMPT_EXACT_PRODUCT_JUDGE,
                    image=image_url if use_image else None,
                    image_detail=self.config.llm_image_detail,
                    response_format={"type": "json_object"},
                    purpose="exact_product_adjudication_vision" if use_image else "exact_product_adjudication",
                )
                raw = response.content
                judgement = self._parse_response(
                    url=card.candidate.url,
                    raw=response.content,
                    call_index=call_index,
                    payload_level=level,
                    image_url=image_url if use_image else None,
                    gateway_retry=offset > 0,
                )
                records.append(self._record(state, card, call_index, level, use_image, image_url if use_image else None, True, judgement.decision, None, response))
                return judgement, records, offset + 1
            except Exception as exc:
                last_error = str(exc)
                logger.warning("LLM adjudication failed; trying smaller payload if budget remains | url={} | level={} | error={}", card.candidate.url, level, last_error)
                records.append(self._record(state, card, call_index, level, use_image, image_url if use_image else None, False, "LLM_FAILED", last_error, None))
                continue

        consumed = min(len(levels), calls_remaining)
        return LLMJudgement(
            url=card.candidate.url,
            decision="LLM_FAILED",
            exact_product_match=False,
            confidence=0.0,
            reject_reason="llm_call_failed_or_payload_rejected",
            final_explanation="LLM adjudication failed after payload reduction; candidate was not accepted by LLM.",
            payload_level=levels[min(consumed - 1, len(levels) - 1)] if consumed else "NONE",
            call_index=starting_call_index + max(0, consumed - 1),
            image_used=False,
            error=last_error,
            raw_response=raw,
        ), records, consumed

    def _parse_response(self, *, url: str, raw: str, call_index: int, payload_level: str, image_url: str | None, gateway_retry: bool) -> LLMJudgement:
        obj = self._loads_json(raw)
        decision = str(obj.get("decision") or "INSUFFICIENT_EVIDENCE").strip().upper()
        if decision not in ALLOWED_DECISIONS:
            decision = "INSUFFICIENT_EVIDENCE"
        confidence = self._float01(obj.get("confidence"))
        exact = bool(obj.get("exact_product_match")) and decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"}
        main_text_assessment = obj.get("main_text_assessment") if isinstance(obj.get("main_text_assessment"), dict) else {}
        ean_assessment = obj.get("ean_assessment") if isinstance(obj.get("ean_assessment"), dict) else {}
        variant_assessment = obj.get("variant_assessment") if isinstance(obj.get("variant_assessment"), dict) else {}
        scrape_assessment = obj.get("scrape_assessment") if isinstance(obj.get("scrape_assessment"), dict) else {}
        image_assessment = obj.get("image_assessment") if isinstance(obj.get("image_assessment"), dict) else {}
        return LLMJudgement(
            url=url,
            decision=decision,
            exact_product_match=exact,
            confidence=confidence,
            primary_identity_driver=str(obj.get("primary_identity_driver") or "UNKNOWN")[:120],
            main_text_status=str(main_text_assessment.get("status") or "UNKNOWN")[:50],
            ean_status=str(ean_assessment.get("status") or "UNKNOWN")[:50],
            variant_status=str(variant_assessment.get("status") or "UNKNOWN")[:50],
            scrape_usable=bool(scrape_assessment.get("usable_for_final")),
            image_used=bool(image_assessment.get("used")) or bool(image_url),
            image_url=image_url,
            image_status=str(image_assessment.get("status") or ("USED" if image_url else "NOT_USED"))[:80],
            recommended_next_action=str(obj.get("recommended_next_action") or "UNKNOWN")[:80],
            reject_reason=obj.get("reject_reason"),
            final_explanation=str(obj.get("final_explanation") or "")[:1000],
            payload_level=payload_level,
            call_index=call_index,
            gateway_retry=gateway_retry,
            raw_response=raw[:4000],
        )

    @staticmethod
    def _loads_json(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except Exception:
            m = re.search(r"\{.*\}", raw or "", flags=re.S)
            if m:
                return json.loads(m.group(0))
            raise ValueError("LLM did not return parseable JSON")

    @staticmethod
    def _float01(value: Any) -> float:
        try:
            x = float(value)
        except Exception:
            return 0.0
        return max(0.0, min(1.0, x))

    def _select_one_image(self, card: CandidateScorecard) -> str | None:
        if not card.scrape:
            return None
        noise = ("logo", "icon", "sprite", "payment", "paypal", "visa", "mastercard", "banner", "tracking", "pixel", "placeholder", "facebook", "instagram")
        for url in card.scrape.image_urls[:8]:
            folded = (url or "").lower()
            if not url.startswith(("http://", "https://", "data:")):
                continue
            if any(term in folded for term in noise):
                continue
            return url
        return None

    def _attach_judgement(self, card: CandidateScorecard, judgement: LLMJudgement) -> CandidateScorecard:
        reasons = list(card.ranking_reasons)
        if judgement.decision != "NOT_EVALUATED":
            reasons.append(f"llm_decision={judgement.decision}")
            if judgement.final_explanation:
                reasons.append("llm=" + judgement.final_explanation[:240])
        hard = list(card.hard_failures)
        warn = list(card.soft_warnings)
        if judgement.decision in {"SIBLING_VARIANT", "WRONG_PRODUCT", "NON_PRODUCT_PAGE", "UNSCRAPABLE"}:
            hard.append(judgement.reject_reason or judgement.decision)
        elif judgement.decision == "INSUFFICIENT_EVIDENCE":
            warn.append("LLM judged evidence insufficient for exact product")
        elif judgement.decision == "EXACT_MATCH_WITH_WARNING":
            warn.append(judgement.reject_reason or "LLM exact match with warning")
        return replace(
            card,
            hard_failures=tuple(dict.fromkeys(hard)),
            soft_warnings=tuple(dict.fromkeys(warn)),
            ranking_reasons=tuple(dict.fromkeys(reasons)),
            llm_judgement=judgement,
            llm_used=judgement.decision != "NOT_EVALUATED",
            llm_decision=judgement.decision,
            llm_confidence=judgement.confidence,
            llm_exact_product_match=judgement.exact_product_match,
            llm_reject_reason=judgement.reject_reason or "",
            llm_justification=judgement.final_explanation,
            final_confidence=round(max(card.final_confidence, judgement.confidence) if judgement.accepted_for_final else min(card.final_confidence, 0.74), 4),
            validation_status="VERIFIED" if judgement.accepted_for_final and not hard else card.validation_status,
            selected_with_warning=card.selected_with_warning or judgement.decision == "EXACT_MATCH_WITH_WARNING",
            primary_reject_reason=card.primary_reject_reason or (judgement.reject_reason or "" if not judgement.accepted_for_final else ""),
        )

    @staticmethod
    def _llm_sort_key(card: CandidateScorecard) -> tuple[float, ...]:
        llm_rank = 2 if card.llm_decision == "EXACT_MATCH" else 1 if card.llm_decision == "EXACT_MATCH_WITH_WARNING" else 0
        return (
            llm_rank,
            1 if card.country_check in {"MATCHED", "NOT_PROVIDED"} else 0,
            card.llm_confidence,
            1 if card.scrape and card.scrape.is_scrapable else 0,
            card.final_confidence,
        )

    def _record(self, state: ProductSearchState, card: CandidateScorecard, call_index: int, payload_level: str, image_used: bool, image_url: str | None, success: bool, decision: str, error: str | None, response: LLMResponse | None) -> LLMCallRecord:
        usage = response.usage if response else {}
        return LLMCallRecord(
            row_id=state.task.row_id,
            url=card.candidate.url,
            call_index=call_index,
            payload_level=payload_level,
            image_used=image_used,
            image_url=image_url,
            success=success,
            decision=decision,
            error=error,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
        )
