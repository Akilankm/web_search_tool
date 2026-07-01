"""Batch runner for the Exact Product Discovery Harness.

Usage:
  python batch_main.py --input data/products.xlsx --output outputs/final_submission.csv --workers 4

The runner reads all columns as strings to protect EAN/GTIN identifiers. It
creates one harness per worker call to avoid shared crawl/browser/session state.

Batch outputs:
  - final_submission.csv: compact file to submit/share.
  - review_queue.csv: rows that need human review.
  - batch_summary.md: human-readable run summary.
  - output/<row_id>/: concise review packet for each product.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pandas as pd  # noqa: E402
from rich import print  # noqa: E402
from tqdm.auto import tqdm  # noqa: E402

from product_evidence_harness import (  # noqa: E402
    CSVProductIO,
    HarnessConfig,
    ProductEvidenceHarness,
    SerpAPIConfig,
    configure_logging,
)
from product_evidence_harness.artifacts import ArtifactWriter  # noqa: E402
from product_evidence_harness.elite import EnterpriseEvidenceEngine  # noqa: E402
from product_evidence_harness.production_url import ProductionURLGate  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run exact-product URL discovery for a batch file.")
    parser.add_argument("--input", required=True, help="CSV/XLSX with row_id, main_text, country_code, optional ean, retailer_name")
    parser.add_argument("--output", default="outputs/final_submission.csv", help="Submission-ready final CSV path")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def build_harness(product, env_file: str) -> tuple[ProductEvidenceHarness, HarnessConfig]:
    config = HarnessConfig.from_env(env_file)
    serp_config = SerpAPIConfig.from_env(
        country_code=product.country_code,
        language_code=product.language_code or "en",
        env_file=env_file,
        no_cache=False,
    )
    return ProductEvidenceHarness(serp_config=serp_config, config=config), config


def _production_fields(production_assessment) -> dict[str, Any]:
    if not production_assessment:
        return {
            "production_url_ready": False,
            "production_url_status": "PRODUCT_URL_NOT_ASSESSED_OR_NO_SCORECARD",
            "browser_openable": False,
            "highly_scrapable": False,
            "exact_product_url_match": False,
            "production_url_score": 0.0,
            "production_url_reasons": "NO_SCORECARD_FOR_SELECTED_PRODUCT_URL",
            "rendered_page_check_passed": False,
            "rendered_page_type": "UNKNOWN_PAGE",
            "rendered_product_visible": False,
            "rendered_content_related": False,
            "rendered_match_confidence": 0.0,
            "rendered_verdict": "NOT_EVALUATED",
            "rendered_mismatch_reasons": "NO_SCORECARD_FOR_SELECTED_PRODUCT_URL",
            "rendered_visible_title": "",
            "rendered_visible_product_name": "",
            "rendered_screenshot_path": "",
            "rendered_screenshot_captured": False,
            "rendered_llm_used": False,
        }
    return {
        "production_url_ready": production_assessment.production_ready,
        "production_url_status": production_assessment.status,
        "browser_openable": production_assessment.browser_openable,
        "highly_scrapable": production_assessment.highly_scrapable,
        "exact_product_url_match": production_assessment.exact_product_match,
        "production_url_score": production_assessment.score,
        "production_url_reasons": "|".join(production_assessment.reasons),
        "rendered_page_check_passed": production_assessment.rendered_page_check_passed,
        "rendered_page_type": production_assessment.rendered_page_type,
        "rendered_product_visible": production_assessment.rendered_product_visible,
        "rendered_content_related": production_assessment.rendered_content_related,
        "rendered_match_confidence": production_assessment.rendered_match_confidence,
        "rendered_verdict": production_assessment.rendered_verdict,
        "rendered_mismatch_reasons": "|".join(production_assessment.rendered_mismatch_reasons),
        "rendered_visible_title": production_assessment.rendered_visible_title,
        "rendered_visible_product_name": production_assessment.rendered_visible_product_name,
        "rendered_screenshot_path": production_assessment.rendered_screenshot_path or "",
        "rendered_screenshot_captured": production_assessment.rendered_screenshot_captured,
        "rendered_llm_used": production_assessment.rendered_llm_used,
    }


def process(product, env_file: str) -> dict[str, Any]:
    try:
        harness, config = build_harness(product, env_file)
        trace = harness.run(product, return_trace=True)
        row_dir = Path(config.output_dir) / product.row_id
        row = ArtifactWriter(config.output_dir, country_profiles=harness.country_profiles).final_submission_row(trace.state, product_dir=row_dir)
        row.update(EnterpriseEvidenceEngine().assess(trace.state).final_submission_extras())
        production_assessment = ProductionURLGate().assess_url_in_state(trace.state, row.get("product_url") or "")
        row.update(_production_fields(production_assessment))
        row["review_summary_path"] = str(row_dir / "review_summary.md")
        row["review_decision_path"] = str(row_dir / "review_decision.json")
        row["candidate_decisions_path"] = str(row_dir / "candidate_decisions.csv")
        row["product_coding_input_path"] = str(row_dir / "product_coding_input.json")
        row["status"] = "success"
        row["error"] = None
        return row
    except Exception as exc:
        return {
            "row_id": product.row_id,
            "main_text": product.main_text,
            "country_code": product.country_code,
            "retailer_name": product.retailer_name,
            "ean": product.ean,
            "product_url": None,
            "verified_exact_url": None,
            "best_available_url": None,
            "best_reference_url": None,
            "url_decision_status": "ERROR",
            "selection_scope": "ERROR",
            "is_exact_product_match": False,
            "is_scrapable": False,
            "needs_review": True,
            "confidence": 0.0,
            "production_url_ready": False,
            "production_url_status": "RUN_ERROR",
            "browser_openable": False,
            "highly_scrapable": False,
            "exact_product_url_match": False,
            "production_url_score": 0.0,
            "production_url_reasons": "RUN_ERROR",
            "rendered_page_check_passed": False,
            "rendered_page_type": "RUN_ERROR",
            "rendered_product_visible": False,
            "rendered_content_related": False,
            "rendered_match_confidence": 0.0,
            "rendered_verdict": "RUN_ERROR",
            "rendered_mismatch_reasons": "RUN_ERROR",
            "rendered_visible_title": "",
            "rendered_visible_product_name": "",
            "rendered_screenshot_path": "",
            "rendered_screenshot_captured": False,
            "rendered_llm_used": False,
            "quality_tier": "E",
            "quality_tier_reason": "Run failed before final decision.",
            "coding_readiness_status": "NEEDS_REVIEW",
            "coding_readiness_score": 0.0,
            "identity_confidence": 0.0,
            "scrapability_confidence": 0.0,
            "country_confidence": 0.0,
            "retailer_confidence": 0.0,
            "variant_confidence": 0.0,
            "source_consensus_score": 0.0,
            "failure_taxonomy": "RUN_ERROR",
            "candidate_urls": "",
            "candidate_count": 0,
            "scraped_candidate_count": 0,
            "serp_calls_used": 0,
            "llm_calls_used": 0,
            "scrape_calls_used": 0,
            "final_justification": "Run failed before final decision.",
            "row_report_path": "",
            "review_summary_path": "",
            "review_decision_path": "",
            "candidate_decisions_path": "",
            "product_coding_input_path": "",
            "status": "error",
            "error": str(exc),
        }


def _counter_lines(title: str, counter: Counter) -> list[str]:
    lines = [f"## {title}", ""]
    if not counter:
        lines.append("No values recorded.")
        lines.append("")
        return lines
    lines.extend(["| Value | Count |", "|---|---:|"])
    for key, count in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        lines.append(f"| `{key or 'BLANK'}` | {count} |")
    lines.append("")
    return lines


def write_batch_summary(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    exact = sum(1 for r in rows if str(r.get("verified_exact_url") or "").strip())
    product_url = sum(1 for r in rows if str(r.get("product_url") or "").strip())
    production_ready = sum(1 for r in rows if str(r.get("production_url_ready")).lower() in {"true", "1", "yes"})
    browser_openable = sum(1 for r in rows if str(r.get("browser_openable")).lower() in {"true", "1", "yes"})
    rendered_passed = sum(1 for r in rows if str(r.get("rendered_page_check_passed")).lower() in {"true", "1", "yes"})
    highly_scrapable = sum(1 for r in rows if str(r.get("highly_scrapable")).lower() in {"true", "1", "yes"})
    exact_product_url = sum(1 for r in rows if str(r.get("exact_product_url_match")).lower() in {"true", "1", "yes"})
    coding_ready = sum(1 for r in rows if r.get("coding_readiness_status") == "CODING_READY")
    needs_review = sum(1 for r in rows if str(r.get("needs_review")).lower() in {"true", "1", "yes"} or r.get("status") == "error")
    errors = sum(1 for r in rows if r.get("status") == "error")
    requested_retailer = sum(1 for r in rows if str(r.get("selected_from_requested_retailer")).lower() in {"true", "1", "yes"})
    country_alt = sum(1 for r in rows if str(r.get("selected_from_other_country_retailer")).lower() in {"true", "1", "yes"})
    global_fallback = sum(1 for r in rows if str(r.get("selected_from_global_fallback")).lower() in {"true", "1", "yes"})
    serp_calls = sum(int(float(r.get("serp_calls_used") or 0)) for r in rows)
    llm_calls = sum(int(float(r.get("llm_calls_used") or 0)) for r in rows)
    scrapes = sum(int(float(r.get("scrape_calls_used") or 0)) for r in rows)
    tier_counts = Counter(str(r.get("quality_tier") or "UNKNOWN") for r in rows)
    readiness_counts = Counter(str(r.get("coding_readiness_status") or "UNKNOWN") for r in rows)
    production_counts = Counter(str(r.get("production_url_status") or "UNKNOWN") for r in rows)
    rendered_counts = Counter(str(r.get("rendered_page_type") or "UNKNOWN") for r in rows)
    rendered_verdict_counts = Counter(str(r.get("rendered_verdict") or "UNKNOWN") for r in rows)
    failure_counts: Counter[str] = Counter()
    for r in rows:
        for failure in str(r.get("failure_taxonomy") or "").split("|"):
            if failure:
                failure_counts[failure] += 1
        for failure in str(r.get("rendered_mismatch_reasons") or "").split("|"):
            if failure:
                failure_counts[failure] += 1

    metrics = {
        "total_rows": total,
        "product_url_count": product_url,
        "production_ready_product_url_count": production_ready,
        "browser_openable_product_url_count": browser_openable,
        "rendered_page_check_passed_count": rendered_passed,
        "highly_scrapable_product_url_count": highly_scrapable,
        "exact_product_url_match_count": exact_product_url,
        "verified_exact_count": exact,
        "coding_ready_count": coding_ready,
        "needs_review_count": needs_review,
        "error_count": errors,
        "requested_retailer_selected_count": requested_retailer,
        "country_alternative_selected_count": country_alt,
        "global_fallback_selected_count": global_fallback,
        "serp_calls": serp_calls,
        "llm_calls": llm_calls,
        "scrape_calls": scrapes,
        "quality_tiers": dict(tier_counts),
        "coding_readiness": dict(readiness_counts),
        "production_url_status": dict(production_counts),
        "rendered_page_type": dict(rendered_counts),
        "rendered_verdict": dict(rendered_verdict_counts),
        "failure_taxonomy": dict(failure_counts),
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Batch Product URL Discovery Summary",
        "",
        "## Executive metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total rows | {total} |",
        f"| Rows with product_url | {product_url} |",
        f"| Production-ready URLs | {production_ready} |",
        f"| Browser-openable URLs | {browser_openable} |",
        f"| Rendered product-content checks passed | {rendered_passed} |",
        f"| Highly scrapable URLs | {highly_scrapable} |",
        f"| Exact product URL matches | {exact_product_url} |",
        f"| Coding-ready rows | {coding_ready} |",
        f"| Needs review | {needs_review} |",
        f"| Errors | {errors} |",
        f"| Requested retailer selected | {requested_retailer} |",
        f"| Other country retailer selected | {country_alt} |",
        f"| Global fallback selected | {global_fallback} |",
        f"| SerpAPI organic calls | {serp_calls} |",
        f"| LLM calls | {llm_calls} |",
        f"| Scrape calls | {scrapes} |",
        "",
    ]
    lines.extend(_counter_lines("Production URL status", production_counts))
    lines.extend(_counter_lines("Rendered page type", rendered_counts))
    lines.extend(_counter_lines("Rendered verdict", rendered_verdict_counts))
    lines.extend(_counter_lines("Coding readiness", readiness_counts))
    lines.extend(_counter_lines("Quality tiers", tier_counts))
    lines.extend(_counter_lines("Failure taxonomy", failure_counts))
    (output_dir / "batch_summary.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    products = CSVProductIO().read_products(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[bold]Running batch[/bold] rows={len(products)} workers={args.workers}")
    rows: list[dict[str, Any]] = []
    if args.workers <= 1:
        for product in tqdm(products):
            rows.append(process(product, args.env_file))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            future_map = {pool.submit(process, product, args.env_file): product for product in products}
            for future in tqdm(as_completed(future_map), total=len(future_map)):
                rows.append(future.result())

    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    review = df[(df["needs_review"].astype(str).str.lower().isin(["true", "1", "yes"])) | (df["status"] == "error")]
    review.to_csv(output_path.parent / "review_queue.csv", index=False)
    write_batch_summary(output_path.parent, rows)
    print(f"[green]Wrote[/green] {output_path}")
    print(f"[yellow]Review queue[/yellow] {output_path.parent / 'review_queue.csv'} rows={len(review)}")


if __name__ == "__main__":
    main()
