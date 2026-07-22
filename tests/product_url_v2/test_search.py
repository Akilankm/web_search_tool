from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pytest

from product_url_v2 import (
    DeterministicProductInterpreter,
    InformationGainSearchPlanner,
    ProductInput,
    SearchAction,
    SearchCampaign,
    SearchEngine,
    SearchHandle,
    SearchObservation,
    SearchPurpose,
    SearchResultRecord,
    SearchScope,
    SerpAPIResponseParserV2,
)


def _product(*, ean: str | None = "196214141070") -> ProductInput:
    return ProductInput(
        row_id="PKM-SEARCH",
        main_text="PKM ME04 WACHSENDES CHAOS BOOSTER",
        country_code="CH",
        ean=ean,
        language_code="de",
    )


def _interpret(product: ProductInput):
    return DeterministicProductInterpreter().interpret(product)


def test_credit_one_uses_exact_gtin_and_model_anchors() -> None:
    product = _product()
    action = InformationGainSearchPlanner().choose(
        product=product,
        interpretation=_interpret(product),
        credit_number=1,
        observations=(),
        handles=(),
        used_signatures=set(),
    )

    assert action.purpose is SearchPurpose.ESTABLISH_IDENTITY
    assert action.engine is SearchEngine.GOOGLE
    assert action.scope is SearchScope.COUNTRY
    assert '"196214141070"' in action.query
    assert '"ME04"' in action.query
    assert product.main_text in action.query


def test_credit_two_targets_highest_pack_configuration_uncertainty() -> None:
    product = _product(ean=None)
    action = InformationGainSearchPlanner().choose(
        product=product,
        interpretation=_interpret(product),
        credit_number=2,
        observations=(),
        handles=(),
        used_signatures=set(),
    )

    assert action.purpose is SearchPurpose.RESOLVE_UNCERTAINTY
    assert action.engine is SearchEngine.GOOGLE
    assert "single booster pack" in action.target_uncertainty.lower()
    assert "ME04" in action.query
    assert "pack" in action.query.lower()


def test_available_immersive_token_is_used_for_uncertainty_resolution() -> None:
    product = _product(ean=None)
    handle = SearchHandle(
        kind="immersive_product_page_token",
        value="TOKEN-123",
        source_engine=SearchEngine.GOOGLE_SHOPPING,
        title="ME04 Wachsendes Chaos",
    )
    action = InformationGainSearchPlanner().choose(
        product=product,
        interpretation=_interpret(product),
        credit_number=2,
        observations=(),
        handles=(handle,),
        used_signatures=set(),
    )

    assert action.engine is SearchEngine.GOOGLE_IMMERSIVE_PRODUCT
    assert action.page_token == "TOKEN-123"
    assert action.purpose is SearchPurpose.RESOLVE_UNCERTAINTY


def test_final_credit_is_always_mandatory_url_recovery() -> None:
    product = _product(ean=None)
    action = InformationGainSearchPlanner().choose(
        product=product,
        interpretation=_interpret(product),
        credit_number=3,
        observations=(),
        handles=(),
        used_signatures=set(),
    )

    assert action.purpose is SearchPurpose.MANDATORY_URL_RECOVERY
    assert action.scope is SearchScope.GLOBAL
    assert action.engine is SearchEngine.GOOGLE_AI_MODE
    assert "direct official manufacturer or retailer product page URL" in action.query


def test_same_immersive_token_cannot_consume_credit_two_and_three() -> None:
    product = _product(ean=None)
    planner = InformationGainSearchPlanner()
    handle = SearchHandle(
        kind="immersive_product_page_token",
        value="TOKEN-123",
        source_engine=SearchEngine.GOOGLE_SHOPPING,
    )
    second = planner.choose(
        product=product,
        interpretation=_interpret(product),
        credit_number=2,
        observations=(),
        handles=(handle,),
        used_signatures=set(),
    )
    third = planner.choose(
        product=product,
        interpretation=_interpret(product),
        credit_number=3,
        observations=(),
        handles=(handle,),
        used_signatures={second.signature},
    )

    assert second.engine is SearchEngine.GOOGLE_IMMERSIVE_PRODUCT
    assert third.signature != second.signature
    assert third.engine is SearchEngine.GOOGLE_AI_MODE
    assert third.purpose is SearchPurpose.MANDATORY_URL_RECOVERY


def test_parser_preserves_all_external_results_but_only_promotes_product_like_urls() -> None:
    action = SearchAction(
        credit_number=1,
        engine=SearchEngine.GOOGLE,
        purpose=SearchPurpose.ESTABLISH_IDENTITY,
        scope=SearchScope.COUNTRY,
        query='"ME04" product',
        country_code="CH",
        language_code="de",
    )
    payload = {
        "search_metadata": {"id": "SEARCH-1", "status": "Success"},
        "organic_results": [
            {
                "position": 1,
                "title": "Pokémon ME04 Wachsendes Chaos Booster Pack",
                "link": "https://www.toytans.ch/de/pokemon-booster/2692-pokemon-me04-wachsendes-chaos-booster-pack-de-196214141070.html?utm_source=google",
                "snippet": "German single booster pack",
            },
            {
                "position": 2,
                "title": "Kaufland",
                "link": "https://www.kaufland.at/",
                "snippet": "Homepage",
            },
            {
                "position": 3,
                "title": "Google intermediary",
                "link": "https://www.google.com/search?q=me04",
            },
        ],
        "shopping_results": [
            {
                "title": "ME04 product cluster",
                "immersive_product_page_token": "TOKEN-ABC",
            }
        ],
    }

    observation = SerpAPIResponseParserV2().parse(action, payload)

    assert observation.search_id == "SEARCH-1"
    assert len(observation.results) == 2
    assert len(observation.direct_candidates) == 1
    assert observation.direct_candidates[0].url.startswith("https://toytans.ch/")
    assert "utm_source" not in observation.direct_candidates[0].url
    assert observation.results[1].url == "https://kaufland.at/"
    assert observation.results[1].structurally_product_like is False
    assert observation.handles[0].value == "TOKEN-ABC"


@dataclass
class RecordingClient:
    calls: list[SearchAction] = field(default_factory=list)

    def execute(self, action: SearchAction, product: ProductInput) -> SearchObservation:
        self.calls.append(action)
        handles = (
            SearchHandle(
                kind="immersive_product_page_token",
                value="TOKEN-CAMPAIGN",
                source_engine=action.engine,
                title="ME04",
            ),
        ) if action.credit_number == 1 else ()
        result = SearchResultRecord(
            url=(
                "https://www.toytans.ch/de/pokemon-booster/2692-pokemon-me04-wachsendes-chaos-booster-pack-de-196214141070.html"
                if action.credit_number != 2
                else "https://zadoys.ch/en/products/pokemon-mega-series-wachsendes-chaos-me04-booster-bundle-de"
            ),
            title=f"Candidate from credit {action.credit_number}",
            snippet="direct product page",
            source_section=f"{action.engine.value}:test",
            position=action.credit_number,
            query=action.query or action.purpose.value,
            structurally_product_like=True,
        )
        return SearchObservation(
            action=action,
            status="SUCCESS",
            search_id=f"S-{action.credit_number}",
            raw_result_count=1,
            results=(result,),
            handles=handles,
        )


def test_campaign_executes_complete_budget_and_deduplicates_direct_urls() -> None:
    product = _product(ean=None)
    client = RecordingClient()
    campaign = SearchCampaign(client, InformationGainSearchPlanner())

    result = campaign.run(product, _interpret(product))

    assert result.credits_used == 3
    assert len(result.actions) == 3
    assert [item.purpose for item in result.actions] == [
        SearchPurpose.ESTABLISH_IDENTITY,
        SearchPurpose.RESOLVE_UNCERTAINTY,
        SearchPurpose.MANDATORY_URL_RECOVERY,
    ]
    assert result.actions[1].engine is SearchEngine.GOOGLE_IMMERSIVE_PRODUCT
    assert result.actions[2].engine is SearchEngine.GOOGLE_AI_MODE
    assert len({item.signature for item in result.actions}) == 3
    assert len(result.direct_candidates) == 2
    assert result.handles[0].value == "TOKEN-CAMPAIGN"


class InvalidFinalReasoner:
    def choose_search_action(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "engine": "google",
            "purpose": "RESOLVE_UNCERTAINTY",
            "scope": "global",
            "query": "not a recovery action",
            "rationale": "invalid final purpose",
        }


def test_invalid_reasoner_final_action_falls_back_to_mandatory_recovery() -> None:
    product = _product(ean=None)
    planner = InformationGainSearchPlanner(reasoner=InvalidFinalReasoner())

    action = planner.choose(
        product=product,
        interpretation=_interpret(product),
        credit_number=3,
        observations=(),
        handles=(),
        used_signatures=set(),
    )

    assert action.planner_source == "DETERMINISTIC"
    assert action.purpose is SearchPurpose.MANDATORY_URL_RECOVERY


def test_required_reasoner_rejects_invalid_final_action() -> None:
    product = _product(ean=None)
    planner = InformationGainSearchPlanner(
        reasoner=InvalidFinalReasoner(),
        require_reasoner=True,
    )

    with pytest.raises(ValueError, match="final credit"):
        planner.choose(
            product=product,
            interpretation=_interpret(product),
            credit_number=3,
            observations=(),
            handles=(),
            used_signatures=set(),
        )


def test_reasoning_payload_contains_hypotheses_uncertainties_and_credit_rule() -> None:
    product = _product(ean=None)
    interpretation = _interpret(product)
    planner = InformationGainSearchPlanner()
    payload = planner.reasoning_payload(
        product=product,
        context=__import__("product_url_v2").build_search_context(interpretation),
        credit_number=3,
        observations=(),
        handles=(),
        used_signatures=set(),
    )

    assert payload["search_context"]["hypothesis_summaries"]
    assert payload["search_context"]["unresolved_discriminators"]
    assert payload["credit"]["final_credit_requires_mandatory_url_recovery"] is True
    assert any("Do not invent URLs" in rule for rule in payload["rules"])
