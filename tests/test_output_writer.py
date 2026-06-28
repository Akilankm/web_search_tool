from __future__ import annotations

import csv
import json

from product_evidence_harness import HarnessBudgetConfig, HarnessConfig, ProductEvidenceHarness, ProductQuery, SerpAPIConfig
from product_evidence_harness.contracts import OrganicSearchResponse, OrganicSearchResult, ScrapeResult, SerpAIResponse


class FakeOrganic:
    def search(self, query, *, product=None):
        return OrganicSearchResponse(
            query=query,
            search_id="fake",
            status="Success",
            results=[OrganicSearchResult(url="https://shop.cz/product/acme-widget-18-ks", title="Acme Widget 18 ks", snippet="Buy Acme Widget 18 ks", position=1, query=query)],
        )


class FakeAI:
    def search(self, query, *, product=None):
        return SerpAIResponse(query=query, status="Success", search_id="ai", markdown="")


class FakeScraper:
    def scrape(self, url, *, product=None):
        return ScrapeResult(
            url=url,
            scraped=True,
            success=True,
            reachable=True,
            is_scrapable=True,
            status_code=200,
            final_url=url,
            title="Acme Widget 18 ks",
            h1="Acme Widget 18 ks",
            page_product_name="Acme Widget 18 ks",
            richness_score=0.8,
            word_count=200,
            markdown_chars=1000,
            looks_like_product_page=True,
            verification_text="Acme Widget 18 ks add to cart",
        )


def _build_harness(tmp_path, *, write_debug_csvs=False):
    return ProductEvidenceHarness(
        serp_config=SerpAPIConfig(api_key="test"),
        config=HarnessConfig(
            budget=HarnessBudgetConfig(max_organic_searches=1, max_ai_mode_searches=0, max_scrapes=1, max_iterations=3),
            output_dir=str(tmp_path),
            write_outputs=True,
            write_markdown_reports=True,
            write_trace_json=True,
            write_debug_csvs=write_debug_csvs,
        ),
        organic_client=FakeOrganic(),
        ai_client=FakeAI(),
        scraper=FakeScraper(),
    )


def test_row_artifact_packet_is_written_as_compact_csv_plus_markdown(tmp_path):
    harness = _build_harness(tmp_path)
    trace = harness.run(ProductQuery(row_id="row-001", main_text="Acme Widget 18 ks", country_code="CZ"), return_trace=True)

    row_dir = tmp_path / "row-001"
    expected = [
        "final_row.csv",
        "report.md",
        "search_plan.md",
        "candidate_review.md",
        "scrape_evidence.md",
        "retailer_scrapability.md",
        "final_decision.md",
        "decision_trace.md",
        "trace.json",
    ]
    for name in expected:
        assert (row_dir / name).exists(), name

    # Detailed row-level CSV dumps are disabled by default.
    for old_name in ["summary.csv", "candidates.csv", "scrapes.csv", "actions.csv", "queries.csv"]:
        assert not (row_dir / old_name).exists()

    with (row_dir / "final_row.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["product_url"] == trace.best_match.product_url
    assert rows[0]["resolution_status"] == "RESOLVED"
    assert rows[0]["row_report_path"].endswith("report.md")

    report = (row_dir / "report.md").read_text(encoding="utf-8")
    assert "# Product Discovery Report" in report
    assert "Final Decision" in report
    assert "Candidate Review" in report

    trace_json = json.loads((row_dir / "trace.json").read_text(encoding="utf-8"))
    assert trace_json["final_submission_row"]["row_id"] == "row-001"
    assert trace_json["candidates"][0]["candidate_id"] == "CAND-001"


def test_debug_csvs_are_available_when_enabled(tmp_path):
    harness = _build_harness(tmp_path, write_debug_csvs=True)
    harness.run(ProductQuery(row_id="row-002", main_text="Acme Widget 18 ks", country_code="CZ"), return_trace=True)

    debug_dir = tmp_path / "row-002" / "debug_csv"
    for name in ["best_url.csv", "summary.csv", "candidates.csv", "scrapes.csv", "actions.csv", "queries.csv"]:
        assert (debug_dir / name).exists(), name
