from __future__ import annotations

from product_evidence_harness.candidate_store import CandidateStore
from product_evidence_harness.contracts import OrganicSearchResponse
from product_evidence_harness.serp_harvester import GoogleSERPHarvester


def test_harvester_uses_multiple_sections_without_following_search_links():
    payload = {
        "organic_results": [
            {
                "position": 1,
                "title": "Acme Rocket",
                "link": "https://shop.example/product/rocket?utm_source=google",
                "snippet": "Exact product",
                "sitelinks": {
                    "inline": [
                        {
                            "title": "Specifications",
                            "link": "https://manufacturer.example/rocket/specifications",
                        }
                    ]
                },
            }
        ],
        "shopping_results": [
            {
                "position": 1,
                "title": "Acme Rocket offer",
                "link": "https://shop.example/product/rocket?ref=shopping",
            }
        ],
        "product_sites": [
            {
                "position": 1,
                "title": "Official product",
                "link": "https://manufacturer.example/rocket",
            }
        ],
        "related_questions": [
            {
                "question": "Where to buy?",
                "link": "https://serpapi.com/search.json?q=another-search",
            }
        ],
        "images_results": [
            {
                "title": "Video review",
                "link": "https://youtube.com/watch?v=123",
            }
        ],
    }

    harvested = GoogleSERPHarvester().harvest(payload, query="acme rocket", search_id="s1", status="Success")
    urls = {item.url for item in harvested}

    assert "https://shop.example/product/rocket" in urls
    assert "https://manufacturer.example/rocket" in urls
    assert "https://manufacturer.example/rocket/specifications" in urls
    assert all("serpapi.com" not in url for url in urls)
    assert all("youtube.com" not in url for url in urls)


def test_candidate_store_records_cross_module_support():
    results = GoogleSERPHarvester().harvest(
        {
            "organic_results": [{"position": 1, "title": "Acme", "link": "https://shop.example/p/1"}],
            "shopping_results": [{"position": 2, "title": "Acme offer", "link": "https://shop.example/p/1"}],
        },
        query="acme",
        search_id="s1",
        status="Success",
    )
    response = OrganicSearchResponse(query="acme", search_id="s1", status="Success", results=results)
    candidates = CandidateStore(max_pool_size=20).merge_organic([], response)

    assert len(candidates) == 1
    assert set(candidates[0].source_types) == {"serp_organic_results", "serp_shopping_results"}
    assert candidates[0].organic_count == 2
