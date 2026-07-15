from __future__ import annotations

import json
from dataclasses import replace
from typing import Sequence

from src.product_evidence_harness.adaptive_search import BudgetAwareSearchPlanner, SearchAction, SearchEngine
from src.product_evidence_harness.contracts import ProductQuery, URLCandidate
from src.product_evidence_harness.ranker import ProductURLRanker
from src.product_evidence_harness.selector import FinalSelector
from src.product_evidence_harness.source_authority import (
    SourceAuthorityPolicy,
    SourceTier,
    marketplace_name,
    source_tier,
    tier_from_signals,
)
from src.product_evidence_harness.three_stage_pipeline import ThreeStageProductEvidenceHarness


def _identity(product: ProductQuery) -> str:
    return " ".join(item for item in (product.ean or "", product.main_text) if item).strip()


def _query(product: ProductQuery, target: str) -> str:
    identity = _identity(product)
    if target.startswith("REQUESTED_RETAILER"):
        return f'"{identity}" "{product.retailer_name or ""}" product page'
    if target == "LOCAL_MANUFACTURER":
        return f'"{identity}" official manufacturer product {product.country_code}'
    if target == "GLOBAL_MANUFACTURER":
        return f'"{identity}" official global manufacturer product page'
    if target == "MAJOR_COUNTRY_RETAILER":
        return f'"{identity}" major retailer product {product.country_code}'
    if target == "OTHER_LOCAL_WEBSITE":
        return f'"{identity}" product {product.country_code} -amazon -ebay'
    if target == "OTHER_GLOBAL_WEBSITE":
        return f'"{identity}" exact product page -amazon -ebay'
    return f'"{identity}" product amazon ebay'


def _engine_allowed(engine: str, target: str) -> bool:
    if target.startswith("REQUESTED_RETAILER"):
        return engine in {"google", "google_shopping", "google_ai_mode", "amazon", "ebay", "walmart", "home_depot"}
    if target in {"LOCAL_MANUFACTURER", "GLOBAL_MANUFACTURER"}:
        return engine in {"google", "google_ai_mode"}
    if target in {"MAJOR_COUNTRY_RETAILER", "OTHER_LOCAL_WEBSITE"}:
        return engine in {"google", "google_shopping", "google_ai_mode", "google_immersive_product"}
    return engine in {"google", "google_shopping", "google_ai_mode", "google_immersive_product", "google_lens"}


def _hierarchy_action(
    product: ProductQuery,
    target: str,
    available_engines: Sequence[str],
    reason: str,
) -> SearchAction:
    native = ""
    requested = (product.retailer_name or "").lower().replace(" ", "")
    for name in ("amazon", "ebay", "walmart", "home_depot"):
        if name.replace("_", "") in requested and name in available_engines:
            native = name
            break
    if target.startswith("REQUESTED_RETAILER") and native:
        engine = native
    elif target == "MAJOR_COUNTRY_RETAILER" and SearchEngine.GOOGLE_SHOPPING.value in available_engines:
        engine = SearchEngine.GOOGLE_SHOPPING.value
    elif target == "OTHER_GLOBAL_WEBSITE" and SearchEngine.GOOGLE_AI_MODE.value in available_engines:
        engine = SearchEngine.GOOGLE_AI_MODE.value
    else:
        engine = SearchEngine.GOOGLE.value if SearchEngine.GOOGLE.value in available_engines else available_engines[0]
    return SearchAction(
        engine=engine,
        purpose=f"source_hierarchy_{target.lower()}",
        query=_query(product, target),
        scope="global" if target in {"GLOBAL_MANUFACTURER", "OTHER_GLOBAL_WEBSITE", "MARKETPLACE_LAST_RESORT"} else "country",
        language_code=product.language_code or "en",
        country_code=product.country_code,
        expected_signals=(f"SOURCE_TIER:{target}", "DIRECT_EXACT_PRODUCT_URL"),
        reason=f"Target the highest unresolved internal source tier: {target}. {reason}".strip(),
        planner_source="deterministic_fallback",
    )


def apply_source_authority_patches() -> None:
    if getattr(BudgetAwareSearchPlanner, "_source_authority_applied", False):
        return

    policy = SourceAuthorityPolicy()
    original_prompt = BudgetAwareSearchPlanner._prompt
    original_choose = BudgetAwareSearchPlanner.choose_action
    original_fallback = BudgetAwareSearchPlanner.deterministic_fallback
    original_preflight = ThreeStageProductEvidenceHarness._preflight_rank
    original_score = ProductURLRanker.score
    original_sort_key = ProductURLRanker._sort_key

    def prompt(self, **kwargs):
        product = kwargs["product"]
        target = getattr(self, "_source_authority_target", policy.next_target(product, kwargs.get("observations") or ()))
        payload = json.loads(original_prompt(self, **kwargs))
        payload["source_authority_policy"] = {
            "requested_retailer_override": bool(product.retailer_name),
            "hierarchy": list(policy.hierarchy(product)),
            "current_target_tier": target,
            "amazon_ebay_last_resort": not bool(product.retailer_name and marketplace_name(product.retailer_name)),
            "selection_rule": "Among exact working URLs, lower source tier wins before richness or confidence.",
        }
        payload["rules"] = [
            f"Target source tier {target}; do not route to a lower tier while this tier is unresolved.",
            "Amazon and eBay are last resort unless explicitly supplied as retailer_name.",
            *payload.get("rules", []),
        ]
        payload["output_schema"]["expected_signals"] = [f"SOURCE_TIER:{target}", "signal"]
        return json.dumps(payload, ensure_ascii=False)

    def choose(self, *, product, observations, handles, used_signatures=None, **kwargs):
        target = policy.next_target(product, observations)
        self._source_authority_target = target
        action = original_choose(
            self,
            product=product,
            observations=observations,
            handles=handles,
            used_signatures=used_signatures,
            **kwargs,
        )
        available = self._available_engines(product, handles)
        if not _engine_allowed(action.engine, target):
            action = _hierarchy_action(product, target, available, "The proposed engine did not match the target tier.")
        signals = tuple(item for item in action.expected_signals if not str(item).startswith("SOURCE_TIER:"))
        return replace(
            action,
            expected_signals=(f"SOURCE_TIER:{target}", *signals),
            reason=f"Source hierarchy target={target}. {action.reason}".strip(),
        )

    def fallback(self, *, product, observations, handles, available_engines, **kwargs):
        target = getattr(self, "_source_authority_target", policy.next_target(product, observations))
        try:
            return _hierarchy_action(
                product,
                target,
                available_engines,
                str(kwargs.get("fallback_reason") or "Guarded hierarchy fallback."),
            )
        except Exception:
            return original_fallback(
                self,
                product=product,
                observations=observations,
                handles=handles,
                available_engines=available_engines,
                **kwargs,
            )

    def preflight(self, product, candidates):
        return original_preflight(self, product, policy.tag_candidates(product, candidates))

    def score(self, *, product, candidates, scrapes, verifications):
        tagged = policy.tag_candidates(product, candidates, scrapes)
        return original_score(self, product=product, candidates=tagged, scrapes=scrapes, verifications=verifications)

    def sort_key(self, card):
        base = original_sort_key(self, card)
        return (base[0], base[1], 100 - source_tier(card.candidate), *base[2:])

    def select_exact(self, scorecards):
        for card in scorecards:
            tier = source_tier(card.candidate)
            global_allowed = self.policy.allow_global_fallback or tier == int(SourceTier.GLOBAL_MANUFACTURER)
            if tier in {int(SourceTier.OTHER_GLOBAL_WEBSITE), int(SourceTier.MARKETPLACE_LAST_RESORT)} and not global_allowed:
                continue
            if card.validation_status == "VERIFIED" and self._is_final_usable(card):
                return card
        return None

    def select_best(self, scorecards, *, allow_hard_rejected=False):
        candidates = list(scorecards) if allow_hard_rejected else [card for card in scorecards if not card.hard_failures]
        if not candidates:
            return None
        def key(card):
            scrape = card.scrape
            return (
                1 if card.llm_decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"} else 0,
                1 if not card.hard_failures else 0,
                100 - source_tier(card.candidate),
                1 if scrape and scrape.is_scrapable else 0,
                1 if scrape and scrape.looks_like_product_page else 0,
                card.richness_score,
                card.final_confidence,
            )
        return sorted(candidates, key=key, reverse=True)[0]

    BudgetAwareSearchPlanner._prompt = prompt
    BudgetAwareSearchPlanner.choose_action = choose
    BudgetAwareSearchPlanner.deterministic_fallback = fallback
    ThreeStageProductEvidenceHarness._preflight_rank = preflight
    ProductURLRanker.score = score
    ProductURLRanker._sort_key = sort_key
    FinalSelector._select_exact_card = select_exact
    FinalSelector._select_best_available_card = select_best

    import src.product_evidence_harness.adaptive_search_runtime as adaptive_runtime
    original_working = adaptive_runtime._working_url_found
    original_write = adaptive_runtime._write_adaptive_artifacts

    def hierarchy_working(self, match):
        if not original_working(self, match):
            return False
        product = ProductQuery(
            row_id=match.row_id,
            main_text=match.main_text,
            country_code=match.country_code,
            retailer_name=match.retailer_name,
            ean=match.ean,
        )
        decision = policy.classify(
            product,
            URLCandidate(url=match.product_url, title=match.main_text),
        )
        return decision.source_tier in {
            int(SourceTier.REQUESTED_RETAILER_LOCAL),
            int(SourceTier.REQUESTED_RETAILER_GLOBAL),
            int(SourceTier.LOCAL_MANUFACTURER),
            int(SourceTier.GLOBAL_MANUFACTURER),
        }

    def write_artifacts(root, **kwargs):
        trace = kwargs.get("trace") or []
        product = kwargs["product"]
        for row in trace:
            target = tier_from_signals(row.get("expected_signals") or ())
            row["target_source_tier"] = target or "UNKNOWN"
        original_write(root, **kwargs)
        result_path = root / "result.json"
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        search = payload.setdefault("search", {})
        search.update(
            {
                "source_authority_hierarchy_enforced": True,
                "requested_retailer_override": bool(product.retailer_name),
                "source_hierarchy": list(policy.hierarchy(product)),
                "amazon_ebay_last_resort": not bool(product.retailer_name and marketplace_name(product.retailer_name)),
                "target_source_tiers": [row.get("target_source_tier") for row in trace],
            }
        )
        result_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        trace_path = root / "adaptive_search_trace.json"
        if trace_path.is_file():
            trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))
            trace_payload["search"] = search
            trace_path.write_text(json.dumps(trace_payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        review_path = root / "review.md"
        if review_path.is_file():
            review_path.write_text(
                review_path.read_text(encoding="utf-8")
                + "\n## Source-authority hierarchy\n\n"
                + " → ".join(policy.hierarchy(product))
                + "\n\nAmazon and eBay are last resort unless explicitly requested.\n",
                encoding="utf-8",
            )

    adaptive_runtime._working_url_found = hierarchy_working
    adaptive_runtime._write_adaptive_artifacts = write_artifacts
    BudgetAwareSearchPlanner._source_authority_applied = True
