from __future__ import annotations

import json

import pytest

from product_evidence_harness.adaptive_search import (
    AdaptiveSearchError,
    BudgetAwareSearchPlanner,
    SearchAction,
    SearchHandle,
    SearchObservation,
    SerpAPIMultiEngineClient,
    SerpAPIResponseParser,
)
from product_evidence_harness.contracts import ProductQuery


def product(**overrides) -> ProductQuery:
    values = {
        "row_id": "ROW-1",
        "main_text": "LEGO Star Wars R2-D2 75379",
        "country_code": "GB",
        "retailer_name": None,
        "ean": None,
        "language_code": "en",
    }
    values.update(overrides)
    return ProductQuery(**values)


def test_google_shopping_parser_keeps_direct_urls_and_followup_handles() -> None:
    action = SearchAction(
        engine="google_shopping",
        purpose="resolve_product",
        query="LEGO 75379",
        country_code="GB",
    )
    payload = {
        "search_metadata": {"id": "s1", "status": "Success"},
        "shopping_results": [
            {
                "position": 1,
                "title": "LEGO Star Wars R2-D2 75379",
                "product_link": "https://shop.example/products/lego-75379?utm_source=google",
                "product_id": "12345",
                "immersive_product_page_token": "TOKEN-123",
                "thumbnail": "https://images.example/75379.jpg",
            }
        ],
    }

    observation = SerpAPIResponseParser().parse(action, payload)

    assert [item.url for item in observation.results] == [
        "https://shop.example/products/lego-75379"
    ]
    assert {(item.kind, item.value) for item in observation.handles} >= {
        ("product_id", "12345"),
        ("immersive_product_page_token", "TOKEN-123"),
        ("image_url", "https://images.example/75379.jpg"),
    }


def test_immersive_product_parser_extracts_store_links() -> None:
    action = SearchAction(
        engine="google_immersive_product",
        purpose="expand_stores",
        page_token="TOKEN-123",
    )
    payload = {
        "search_metadata": {"id": "s2", "status": "Success"},
        "product_results": {
            "title": "LEGO R2-D2 75379",
            "stores": [
                {
                    "name": "Toy Shop",
                    "link": "https://toy.example/p/75379?ref=google",
                    "price": "£89.99",
                },
                {
                    "name": "Other Shop",
                    "link": "https://other.example/product/75379",
                },
            ],
        },
    }

    observation = SerpAPIResponseParser().parse(action, payload)

    assert {item.url for item in observation.results} == {
        "https://toy.example/p/75379",
        "https://other.example/product/75379",
    }


def test_ai_mode_parser_collects_references_and_shopping_links() -> None:
    action = SearchAction(
        engine="google_ai_mode",
        purpose="disambiguate",
        query="exact LEGO 75379 retailer page",
    )
    payload = {
        "search_metadata": {"id": "s3", "status": "Success"},
        "reconstructed_markdown": "The exact set is model 75379.",
        "references": [
            {
                "title": "LEGO official",
                "link": "https://www.lego.com/en-gb/product/r2-d2-75379",
            }
        ],
        "shopping_results": [
            {
                "title": "LEGO R2-D2",
                "product_link": "https://retailer.example/item/75379",
            }
        ],
    }

    observation = SerpAPIResponseParser().parse(action, payload)

    assert {item.url for item in observation.results} == {
        "https://www.lego.com/en-gb/product/r2-d2-75379",
        "https://retailer.example/item/75379",
    }
    assert "model 75379" in observation.answer_summary


def test_lens_action_requires_a_real_image_url() -> None:
    with pytest.raises(AdaptiveSearchError, match="requires image_url"):
        SerpAPIMultiEngineClient._validate_action(
            SearchAction(
                engine="google_lens",
                purpose="visual_match",
                query="LEGO 75379",
            )
        )


def test_immersive_action_requires_a_real_page_token() -> None:
    with pytest.raises(AdaptiveSearchError, match="requires page_token"):
        SerpAPIMultiEngineClient._validate_action(
            SearchAction(
                engine="google_immersive_product",
                purpose="expand_stores",
            )
        )


def test_deterministic_planner_uses_exact_ean_first() -> None:
    planner = BudgetAwareSearchPlanner(require_llm=False)

    action = planner.deterministic_fallback(
        product=product(ean="5702017584379"),
        credit_number=1,
        observations=[],
        handles=[],
        used_signatures=set(),
        available_engines=("google", "google_shopping", "google_ai_mode"),
    )

    assert action.engine == "google"
    assert '"5702017584379"' in action.query


def test_deterministic_planner_expands_immersive_token() -> None:
    planner = BudgetAwareSearchPlanner(require_llm=False)
    handles = [
        SearchHandle(
            kind="immersive_product_page_token",
            value="TOKEN-123",
            source_engine="google_shopping",
        )
    ]

    action = planner.deterministic_fallback(
        product=product(),
        credit_number=2,
        observations=[],
        handles=handles,
        used_signatures=set(),
        available_engines=(
            "google",
            "google_shopping",
            "google_ai_mode",
            "google_immersive_product",
        ),
    )

    assert action.engine == "google_immersive_product"
    assert action.page_token == "TOKEN-123"


def test_deterministic_planner_prefers_requested_native_retailer() -> None:
    planner = BudgetAwareSearchPlanner(require_llm=False)

    action = planner.deterministic_fallback(
        product=product(retailer_name="Amazon UK"),
        credit_number=1,
        observations=[],
        handles=[],
        used_signatures=set(),
        available_engines=("amazon", "google", "google_shopping"),
    )

    assert action.engine == "amazon"


def test_planner_prompt_is_compact_and_does_not_include_raw_payload() -> None:
    planner = BudgetAwareSearchPlanner(require_llm=False, max_context_candidates=3)
    observation = SearchObservation(
        action=SearchAction(
            engine="google_shopping",
            purpose="resolve_product",
            query="LEGO 75379",
        ),
        status="Success",
        search_id="s1",
        results=[],
        handles=[],
        raw_payload={"large_secret_response": "X" * 5000},
    )

    prompt = planner._prompt(
        product=product(),
        credit_number=2,
        credits_remaining=2,
        observations=[observation],
        handles=[],
        candidates=[],
        rejection_summary={},
        available_engines=("google", "google_shopping", "google_ai_mode"),
    )

    parsed = json.loads(prompt)
    assert "large_secret_response" not in prompt
    assert parsed["budget"]["maximum_total_credits"] == 3
    assert len(prompt) < 8000
