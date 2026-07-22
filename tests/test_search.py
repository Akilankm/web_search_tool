from product_url_v2.config import RuntimeConfig
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import ProductInput, SearchAction, SearchObservation, SearchResult
from product_url_v2.search import InformationGainSearchPlanner, is_product_like_url, parse_serpapi_response


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, action, product):
        self.calls.append(action)
        token = "TOKEN-1" if action.credit_number == 1 else "TOKEN-1" if action.credit_number == 2 else ""
        url = f"https://shop.example/products/item-{action.credit_number}"
        return SearchObservation(action, "SUCCESS", (SearchResult(url, "Item", "", "fixture", action.engine, action.query, action.credit_number, True, token),))


def test_search_budget_has_three_distinct_billable_actions() -> None:
    product = ProductInput("P1", "PKM ME04 WACHSENDES CHAOS BOOSTER", "CH", ean="196214141070", language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    client = FakeClient()
    campaign = InformationGainSearchPlanner(RuntimeConfig()).run(product, interpretation, client)
    assert [item.purpose for item in campaign.actions] == ["ESTABLISH_IDENTITY", "RESOLVE_UNCERTAINTY", "MANDATORY_URL_RECOVERY"]
    assert len({item.signature for item in campaign.actions}) == 3
    assert "196214141070" in campaign.actions[0].query
    assert campaign.actions[2].engine == "google_ai_mode"


def test_serp_parser_keeps_homepage_for_audit_but_not_candidate() -> None:
    action = SearchAction(1, "google", "ESTABLISH_IDENTITY", "country", query="item")
    observation = parse_serpapi_response(action, {
        "organic_results": [
            {"position": 1, "title": "Homepage", "link": "https://www.kaufland.at/"},
            {"position": 2, "title": "Product", "link": "https://www.toytans.ch/de/pokemon-booster/2692-pokemon-me04-wachsendes-chaos-booster-pack-de-196214141070.html"},
        ]
    })
    assert len(observation.results) == 2
    assert [item.product_like for item in observation.results] == [False, True]


def test_structural_product_url_filter() -> None:
    assert is_product_like_url("https://shop.example/products/exact-item")
    assert not is_product_like_url("https://shop.example/")
    assert not is_product_like_url("https://shop.example/search?q=item")


def test_last_credit_is_always_url_recovery_for_reduced_profile() -> None:
    from product_url_v2.config import SearchConfig
    product = ProductInput("P2", "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK", "DE")
    interpretation = DeterministicProductInterpreter().interpret(product)
    planner = InformationGainSearchPlanner(RuntimeConfig(search=SearchConfig(credit_limit=2)))
    campaign = planner.run(product, interpretation, FakeClient())
    assert campaign.actions[-1].purpose == "MANDATORY_URL_RECOVERY"
