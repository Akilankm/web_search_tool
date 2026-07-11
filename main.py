"""Run the one-credit, feature-aware product evidence workflow for one product."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from product_evidence_harness import (  # noqa: E402
    FeatureAwareProductEvidenceHarness,
    HarnessConfig,
    LLMFeatureReasoner,
    ProductQuery,
    SerpAPIConfig,
    configure_logging,
    load_feature_schema,
    validate_runtime_environment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one-credit product URL discovery and feature-aware evidence extraction.")
    parser.add_argument("--row-id", default="single-001")
    parser.add_argument("--main-text", required=True)
    parser.add_argument("--country-code", required=True)
    parser.add_argument("--feature-schema", required=True, help="JSON/CSV/XLSX feature schema")
    parser.add_argument("--ean", default=None)
    parser.add_argument("--retailer-name", default=None)
    parser.add_argument("--language-code", default=None)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    # Fail before any paid request if secrets, transport settings, file permissions,
    # or one-credit cost controls are unsafe or ambiguous.
    environment = validate_runtime_environment(args.env_file)

    product = ProductQuery(
        row_id=args.row_id,
        main_text=args.main_text,
        country_code=args.country_code,
        retailer_name=args.retailer_name,
        ean=args.ean,
        language_code=args.language_code,
    )
    schema = load_feature_schema(args.feature_schema)
    serp_config = SerpAPIConfig.from_env(
        country_code=product.country_code,
        language_code=product.language_code or "en",
        env_file=args.env_file,
        no_cache=False,
    )
    config = HarnessConfig.from_env(args.env_file)
    reasoner = None
    if environment.llm_feature_reasoning_enabled:
        reasoner = LLMFeatureReasoner.from_env(
            max_calls=int(os.getenv("PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT", "2"))
        )

    result = FeatureAwareProductEvidenceHarness(
        serp_config=serp_config,
        config=config,
        feature_reasoner=reasoner,
    ).run(
        product,
        feature_schema=schema,
        return_trace=True,
    )
    summary = {
        "row_id": product.row_id,
        "environment_checks": list(environment.checks_passed),
        "llm_feature_reasoning_enabled": environment.llm_feature_reasoning_enabled,
        "serpapi_requests_used": result.best_match.organic_calls_used,
        "product_url": result.best_match.product_url,
        "best_available_url": result.best_match.best_available_url,
        "url_status": result.best_match.url_decision_status,
        "coding_status": result.evidence_set.status if result.evidence_set else "FEATURE_SCHEMA_NOT_EVALUATED",
        "selected_evidence_urls": list(result.evidence_set.selected_urls) if result.evidence_set else [],
        "artifact_dir": result.artifact_dir,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
