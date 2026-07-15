from __future__ import annotations

from pathlib import Path

from product_evidence_harness.adaptive_notebook_diagnostics import (
    build_adaptive_search_diagnostics,
    export_adaptive_search_tables,
)


def sample_result() -> dict:
    return {
        "search": {
            "policy": "ADAPTIVE_THREE_CREDIT_MULTI_ENGINE",
            "adaptive_search_contract_enforced": True,
            "serpapi_requests_used": 2,
            "serpapi_request_limit": 3,
            "engine_sequence": ["google_shopping", "google_immersive_product"],
            "planner_calls": 2,
            "planner_fallbacks": 0,
            "working_url_found_during_search": True,
            "stop_reason": "WORKING_EXACT_PRODUCT_URL_FOUND",
            "stages": [
                {
                    "serp_credit": 1,
                    "engine": "google_shopping",
                    "purpose": "resolve_product",
                    "planner_source": "llm",
                    "scope": "country",
                    "results_returned": 20,
                    "handles_discovered": 2,
                    "new_candidate_urls": 4,
                    "candidates_qualified": 2,
                    "candidates_scraped": 1,
                    "current_best_confidence": 0.65,
                    "working_url_found": False,
                },
                {
                    "serp_credit": 2,
                    "engine": "google_immersive_product",
                    "purpose": "expand_stores",
                    "planner_source": "llm",
                    "scope": "country",
                    "results_returned": 5,
                    "handles_discovered": 0,
                    "new_candidate_urls": 5,
                    "candidates_qualified": 3,
                    "candidates_scraped": 2,
                    "current_best_confidence": 0.91,
                    "working_url_found": True,
                    "early_stop": True,
                },
            ],
            "handles": [
                {
                    "kind": "immersive_product_page_token",
                    "value": "TOKEN-1234567890",
                    "source_engine": "google_shopping",
                    "title": "Exact product",
                }
            ],
        }
    }


def test_adaptive_diagnostics_build_credit_and_engine_tables() -> None:
    diagnostics = build_adaptive_search_diagnostics(sample_result())

    assert diagnostics.search_actions_df["engine"].tolist() == [
        "google_shopping",
        "google_immersive_product",
    ]
    assert diagnostics.search_engine_summary_df["credits_used"].sum() == 2
    assert diagnostics.search_engine_summary_df["new_candidate_urls"].sum() == 9
    assert diagnostics.search_handles_df["usable_for_followup"].all()
    assert "WORKING_EXACT_PRODUCT_URL_FOUND" in set(
        diagnostics.search_decision_rca_df["value"].astype(str)
    )


def test_adaptive_diagnostics_export_adds_search_sheets(tmp_path: Path) -> None:
    diagnostics = build_adaptive_search_diagnostics(sample_result())
    workbook = export_adaptive_search_tables(
        diagnostics,
        tmp_path / "single_product_diagnostics.xlsx",
    )

    assert workbook.is_file()
    import openpyxl

    sheet_names = set(openpyxl.load_workbook(workbook, read_only=True).sheetnames)
    assert {
        "adaptive_actions",
        "engine_summary",
        "search_handles",
        "search_rca",
    }.issubset(sheet_names)
