"""Single-product runner for the Exact Product Discovery Harness.

Usage:
  python main.py --main-text "LEGO 41731 Heartlake International School" --country-code CH --ean 5702017415352

All credentials and budgets are loaded from .env / environment variables.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from product_evidence_harness import (  # noqa: E402
    HarnessConfig,
    ProductEvidenceHarness,
    ProductQuery,
    RichPrinter,
    SerpAPIConfig,
    configure_logging,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run exact-product URL discovery for one product row.")
    parser.add_argument("--row-id", default="single-001")
    parser.add_argument("--main-text", required=True)
    parser.add_argument("--country-code", required=True)
    parser.add_argument("--ean", default=None)
    parser.add_argument("--retailer-name", default=None)
    parser.add_argument("--language-code", default=None)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    product = ProductQuery(
        row_id=args.row_id,
        main_text=args.main_text,
        country_code=args.country_code,
        retailer_name=args.retailer_name,
        ean=args.ean,
        language_code=args.language_code,
    )
    serp_config = SerpAPIConfig.from_env(
        country_code=product.country_code,
        language_code=product.language_code or "en",
        env_file=args.env_file,
        no_cache=False,
    )
    config = HarnessConfig.from_env(args.env_file)
    harness = ProductEvidenceHarness(serp_config=serp_config, config=config)
    trace = harness.run(product, return_trace=True)
    printer = RichPrinter()
    printer.print_match(trace.best_match)
    printer.print_scorecards(trace.scored_candidates)
    print("Per-row artifact packet written under:", config.output_dir)
    print("Default row files: final_row.csv, report.md, search_plan.md, candidate_review.md, scrape_evidence.md, retailer_scrapability.md, final_decision.md, decision_trace.md, trace.json")


if __name__ == "__main__":
    main()
