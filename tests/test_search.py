from product_url_v2.config import RuntimeConfig, SearchConfig
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import ProductInput, SearchAction, SearchObservation, SearchResult
from product_url_v2.search import (
    InformationGainSearchPlanner,
    canonical_url,
    explicit_identifier_from_url,
    is_product_like_url,
    parse_serpapi_response,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, action, product):
        self.calls.append(action)
        url = f"https://shop.example/products/item-{action.credit_number}"
        return SearchObservation(
            action,
            "SUCCESS",
            (SearchResult(url, "Item", "", "fixture", action.engine, action.query, action.credit_number, True),),
        )


def test_exact_identifier_search_uses_manufacturer_then_retailer_then_global() -> None:
    ean = "196214141070"
    product = ProductInput("P1", "PKM ME04 WACHSENDES CHAOS BOOSTER", "CH", ean=ean, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    client = FakeClient()
    campaign = InformationGainSearchPlanner(RuntimeConfig()).run(product, interpretation, client)

    assert [item.purpose for item in campaign.actions] == [
        "EXACT_IDENTIFIER_MANUFACTURER",
        "EXACT_IDENTIFIER_COUNTRY_RETAILER",
        "EXACT_IDENTIFIER_GLOBAL_RECOVERY",
    ]
    assert len({item.signature for item in campaign.actions}) == 3
    assert all(ean in item.query for item in campaign.actions)
    assert campaign.actions[0].scope == "country"
    assert campaign.actions[1].engine == "google_shopping"
    assert campaign.actions[2].scope == "global"


def test_serp_parser_keeps_homepage_for_audit_but_not_candidate() -> None:
    action = SearchAction(1, "google", "EXACT_IDENTIFIER_MANUFACTURER", "country", query="item")
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
    assert is_product_like_url("https://shop.example/detail/ISBN-9783311706717/title")
    assert not is_product_like_url("https://shop.example/")
    assert not is_product_like_url("https://shop.example/search?q=item")


def test_reduced_profile_keeps_identifier_locked_final_recovery() -> None:
    ean = "9783311706717"
    product = ProductInput("P2", "MENSCH TÖTE DICH NICHT!", "CH", ean=ean, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    planner = InformationGainSearchPlanner(RuntimeConfig(search=SearchConfig(credit_limit=2)))
    campaign = planner.run(product, interpretation, FakeClient())

    assert campaign.actions[0].purpose == "EXACT_IDENTIFIER_MANUFACTURER"
    assert campaign.actions[-1].purpose == "EXACT_IDENTIFIER_GLOBAL_RECOVERY"
    assert all(ean in item.query for item in campaign.actions)


def test_tracking_parameter_is_removed_from_canonical_url() -> None:
    raw = "https://schreibers.ch/detail/ISBN-2244067996519/title?srsltid=abc&utm_source=google&keep=yes"
    canonical = canonical_url(raw)

    assert "srsltid" not in canonical
    assert "utm_source" not in canonical
    assert "keep=yes" in canonical


def test_explicit_identifier_is_read_from_url_path() -> None:
    url = "https://schreibers.ch/detail/ISBN-2244067996519/Gurt-Philipp/title"
    assert explicit_identifier_from_url(url) == ("2244067996519",)
