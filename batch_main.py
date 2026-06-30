"""Batch runner for the Exact Product Discovery Harness.

Usage:
  python batch_main.py --input data/products.xlsx --output outputs/final_submission.csv --workers 4

The runner reads all columns as strings to protect EAN/GTIN identifiers. It
creates one harness per worker call to avoid shared crawl/browser/session state.

Batch outputs:
  - final_submission.csv: compact file to submit/share.
  - review_queue.csv: rows that need human review.
  - batch_summary.md: human-readable run summary.
  - output/<row_id>/: markdown evidence packet + trace.json for each product.
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
from product_evidence_harness.production_url import ProductionURLGate  # noqa: E402
from product_evidence_harness.tournament_artifacts import TournamentArtifactWriter  # noqa: E402
from product_evidence_harness.tournament_enterprise import TournamentEnterpriseEvidenceEngine  # noqa: E402


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


def process(product, env_file: str) -> dict[str, Any]:
    try:
        harness, config = build_harness(product, env_file)
        trace = harness.run(product, return_trace=True)
        row_dir = Path(config.output_dir) / product.row_id
        row = TournamentArtifactWriter(config.output_dir, country_profiles=harness.country_profiles).final_submission_row(trace.state, product_dir=row_dir)
        row.update(TournamentEnterpriseEvidenceEngine().assess(trace.state).final_submission_extras())
        production_assessment = ProductionURLGate().assess_url_in_state(trace.state, row.get("product_url") or "")
        if production_assessment:
            row.update({
                "production_url_ready": production_assessment.production_ready,
                "production_url_status": production_assessment.status,
                "browser_openable": production_assessment.browser_openable,
                "highly_scrapable": production_assessment.highly_scrapable,
                "exact_product_url_match": production_assessment.exact_product_match,
                "production_url_score": production_assessment.score,
                "production_url_reasons": "|".join(production_assessment.reasons),
            })
        else:
            row.update({
                "production_url_ready": False,
                "production_url_status": "PRODUCT_URL_NOT_ASSESSED_OR_NO_SCORECARD",
                "browser_openable": False,
                "highly_scrapable": False,
                "exact_product_url_match": False,
                "production_url_score": 0.0,
                "production_url_reasons": "NO_SCORECARD_FOR_SELECTED_PRODUCT_URL",
            })
        row["enterprise_assessment_path"] = str(row_dir / "enterprise_assessment.json")
        row["evidence_graph_path"] = str(row_dir / "evidence_graph.json")
        row["product_coding_input_path"] = str(row_dir / "product_coding_input.json")
        row["review_feedback_template_path"] = str(row_dir / "review_feedback_template.json")
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
            "enterprise_assessment_path": "",
            "evidence_graph_path": "",
            "product_coding_input_path": "",
            "review_feedback_template_path": "",
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
    failure_counts: Counter[str] = Counter()
    for r in rows:
        for failure in str(r.get("failure_taxonomy") or "").split("|"):
            if failure:
                failure_counts[failure] += 1

    metrics = {
        "total_rows": total,
        "product_url_count": product_url,
        "production_ready_product_url_count": production_ready,
        "browser_openable_product_url_count": browser_openable,
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
        "failure_taxonomy": dict(failure_counts),
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Batch Product URL Discovery Summary",
        "",
        "## Outcome Metrics",
        f"- **Total rows:** `{total}`",
        f"- **Operational product URLs:** `{product_url}`",
        f"- **Production-ready product URLs:** `{production_ready}`",
        f"- **Browser-openable product URLs:** `{browser_openable}`",
        f"- **Highly scrapable product URLs:** `{highly_scrapable}`",
        f"- **Exact product URL matches:** `{exact_product_url}`",
        f"- **Verified exact URLs:** `{exact}`",
        f"- **Coding-ready rows:** `{coding_ready}`",
        f"- **Needs review:** `{needs_review}`",
        f"- **Errors:** `{errors}`",
        f"- **Selected from requested retailer:** `{requested_retailer}`",
        f"- **Selected from same-country alternative retailer:** `{country_alt}`",
        f"- **Selected from global fallback:** `{global_fallback}`",
        "",
        "## Resource Usage",
        f"- **SerpAPI calls:** `{serp_calls}`",
        f"- **LLM calls:** `{llm_calls}`",
        f"- **scrape calls:** `{scrapes}`",
        "",
    ]
    lines.extend(_counter_lines("Production URL Status Distribution", production_counts))
    lines.extend(_counter_lines("Quality Tier Distribution", tier_counts))
    lines.extend(_counter_lines("Coding Readiness Distribution", readiness_counts))
    lines.extend(_counter_lines("Failure Taxonomy", failure_counts))
    lines.extend([
        "## Review Queue",
        "Rows marked `needs_review=true` are written to `review_queue.csv`.",
        "",
        "## Enterprise Evidence Artifacts",
        "Each row now includes `enterprise_assessment.json`, `evidence_graph.json`, `product_coding_input.json`, `review_feedback_template.json`, and `quality_assessment.md`.",
        "",
        "## Dashboard Data",
        "Machine-readable batch metrics are written to `metrics.json`.",
    ])
    (output_dir / "batch_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    products = CSVProductIO.read_products(Path(args.input))
    print(f"[bold cyan]Loaded {len(products)} products[/bold cyan]")
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(process, p, args.env_file) for p in products]
        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing"):
            rows.append(future.result())

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    if "ean" in df.columns:
        df["ean"] = df["ean"].astype("string")
    df.to_csv(out, index=False)

    review = df[(df.get("needs_review", True).astype(str).str.lower().isin(["true", "1", "yes"])) | (df.get("status", "").astype(str) == "error")]
    review.to_csv(out.parent / "review_queue.csv", index=False)
    write_batch_summary(out.parent, rows)

    print(f"[bold green]Wrote final submission CSV: {out}[/bold green]")
    print(f"[bold yellow]Wrote review queue: {out.parent / 'review_queue.csv'}[/bold yellow]")
    print(f"[bold cyan]Wrote batch summary: {out.parent / 'batch_summary.md'}[/bold cyan]")
    print(f"[bold cyan]Wrote metrics JSON: {out.parent / 'metrics.json'}[/bold cyan]")


if __name__ == "__main__":
    main()
