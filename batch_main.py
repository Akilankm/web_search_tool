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
import sys
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
        row = ArtifactWriter(config.output_dir, country_profiles=harness.country_profiles).final_submission_row(trace.state, product_dir=row_dir)
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
            "candidate_urls": "",
            "candidate_count": 0,
            "scraped_candidate_count": 0,
            "serp_calls_used": 0,
            "llm_calls_used": 0,
            "scrape_calls_used": 0,
            "final_justification": "Run failed before final decision.",
            "row_report_path": "",
            "status": "error",
            "error": str(exc),
        }


def write_batch_summary(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    exact = sum(1 for r in rows if str(r.get("verified_exact_url") or "").strip())
    needs_review = sum(1 for r in rows if str(r.get("needs_review")).lower() in {"true", "1", "yes"} or r.get("status") == "error")
    errors = sum(1 for r in rows if r.get("status") == "error")
    requested_retailer = sum(1 for r in rows if str(r.get("selected_from_requested_retailer")).lower() in {"true", "1", "yes"})
    country_alt = sum(1 for r in rows if str(r.get("selected_from_other_country_retailer")).lower() in {"true", "1", "yes"})
    global_fallback = sum(1 for r in rows if str(r.get("selected_from_global_fallback")).lower() in {"true", "1", "yes"})
    serp_calls = sum(int(float(r.get("serp_calls_used") or 0)) for r in rows)
    llm_calls = sum(int(float(r.get("llm_calls_used") or 0)) for r in rows)
    scrapes = sum(int(float(r.get("scrape_calls_used") or 0)) for r in rows)

    lines = [
        "# Batch Product URL Discovery Summary",
        "",
        "## Outcome Metrics",
        f"- **Total rows:** `{total}`",
        f"- **Verified exact URLs:** `{exact}`",
        f"- **Needs review:** `{needs_review}`",
        f"- **Errors:** `{errors}`",
        f"- **Selected from requested retailer:** `{requested_retailer}`",
        f"- **Selected from same-country alternative retailer:** `{country_alt}`",
        f"- **Selected from global fallback:** `{global_fallback}`",
        "",
        "## Resource Usage",
        f"- **SerpAPI calls:** `{serp_calls}`",
        f"- **LLM calls:** `{llm_calls}`",
        f"- **crawl4ai scrape calls:** `{scrapes}`",
        "",
        "## Review Queue",
        "Rows marked `needs_review=true` are written to `review_queue.csv`.",
        "",
        "## Artifact Model",
        "Each product row has a markdown evidence packet under the configured `PRODUCT_HARNESS_OUTPUT_DIR`.",
    ]
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


if __name__ == "__main__":
    main()
