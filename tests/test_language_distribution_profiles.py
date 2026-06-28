from __future__ import annotations

import json

from product_evidence_harness import HarnessBudgetConfig, HarnessConfig, ProductEvidenceHarness, ProductQuery, SerpAPIConfig
from product_evidence_harness.contracts import OrganicSearchResponse, OrganicSearchResult, ScrapeResult, SerpAIResponse
from product_evidence_harness.country_profiles import CountryProfileRegistry


class EmptyOrganicThenFrench:
    def __init__(self):
        self.calls = []

    def search(self, query, *, product=None):
        self.calls.append(query)
        if len(self.calls) == 1:
            return OrganicSearchResponse(query=query, search_id="de", status="Success", results=[])
        return OrganicSearchResponse(
            query=query,
            search_id="fr",
            status="Success",
            results=[OrganicSearchResult(url="https://shop.ch/fr/product/acme-jouet", title="Acme Jouet", snippet="acheter Acme", position=1, query=query)],
        )


class EmptyAI:
    def search(self, query, *, product=None):
        return SerpAIResponse(query=query, status="Success", search_id="ai", markdown="")


class GoodScraper:
    def scrape(self, url, *, product=None):
        return ScrapeResult(
            url=url,
            scraped=True,
            success=True,
            reachable=True,
            is_scrapable=True,
            status_code=200,
            final_url=url,
            title="Acme Jouet",
            h1="Acme Jouet",
            page_product_name="Acme Jouet",
            richness_score=0.7,
            looks_like_product_page=True,
            verification_text="Acme Jouet 1234567890123 acheter",
        )


def test_ch_profile_exposes_language_distribution_priority():
    profile = CountryProfileRegistry.load().get("CH")
    assert [lp.language_code for lp in profile.language_profiles[:4]] == ["de", "fr", "it", "rm"]
    assert profile.language_profiles[0].distribution_weight == 0.62
    assert profile.language_profiles[1].priority == 2
    assert profile.retailer_domains == ()


def test_second_country_language_search_gets_metadata_in_outputs(tmp_path):
    organic = EmptyOrganicThenFrench()
    harness = ProductEvidenceHarness(
        serp_config=SerpAPIConfig(api_key="test"),
        config=HarnessConfig(
            budget=HarnessBudgetConfig(max_organic_searches=3, max_ai_mode_searches=0, max_scrapes=1, max_iterations=5),
            output_dir=str(tmp_path),
            write_outputs=True,
        ),
        organic_client=organic,
        ai_client=EmptyAI(),
        scraper=GoodScraper(),
    )
    trace = harness.run(ProductQuery(row_id="ch-row", main_text="Acme Jouet", country_code="CH", ean="1234567890123"), return_trace=True)
    assert trace.best_match.product_url == "https://shop.ch/fr/product/acme-jouet"
    assert len(organic.calls) == 2
    assert "kaufen" in organic.calls[0]
    assert "acheter" in organic.calls[1]

    trace_json = json.loads((tmp_path / "ch-row" / "trace.json").read_text(encoding="utf-8"))
    query_actions = [a for a in trace_json["actions"] if a["action"]["action_type"] == "organic_search"]
    assert query_actions[0]["action"]["metadata"]["language_code"] == "de"
    assert query_actions[1]["action"]["metadata"]["language_code"] == "fr"
    assert query_actions[1]["action"]["metadata"]["language_distribution_weight"] == 0.23

    search_plan_md = (tmp_path / "ch-row" / "search_plan.md").read_text(encoding="utf-8")
    assert "`de`" in search_plan_md
    assert "`fr`" in search_plan_md
