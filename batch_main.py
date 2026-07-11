"""Batch runner for the one-credit, feature-aware product evidence workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import pandas as pd  # noqa: E402
from tqdm.auto import tqdm  # noqa: E402

from product_evidence_harness import (  # noqa: E402
    CSVProductIO,
    FeatureAwareProductEvidenceHarness,
    HarnessConfig,
    LLMFeatureReasoner,
    SerpAPIConfig,
    configure_logging,
    load_feature_schema,
    validate_runtime_environment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one SerpAPI search per product and extract evidence for a known feature schema.")
    parser.add_argument("--input", required=True, help="CSV/XLSX containing row_id, main_text, country_code and optional EAN/retailer")
    parser.add_argument("--feature-schema", required=True, help="JSON/CSV/XLSX feature schema")
    parser.add_argument("--output", default="outputs/final_submission.csv")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def process(product, schema, env_file: str, *, llm_enabled: bool, llm_max_calls: int) -> dict[str, Any]:
    try:
        config = HarnessConfig.from_env(env_file)
        serp_config = SerpAPIConfig.from_env(
            country_code=product.country_code,
            language_code=product.language_code or "en",
            env_file=env_file,
            no_cache=False,
        )
        reasoner = LLMFeatureReasoner.from_env(max_calls=llm_max_calls) if llm_enabled else None
        result = FeatureAwareProductEvidenceHarness(
            serp_config=serp_config,
            config=config,
            feature_reasoner=reasoner,
        ).run(
            product,
            feature_schema=schema,
            return_trace=True,
        )
        match = result.best_match
        evidence_set = result.evidence_set
        return {
            "row_id": product.row_id,
            "main_text": product.main_text,
            "country_code": product.country_code,
            "retailer_name": product.retailer_name,
            "ean": product.ean,
            "product_url": match.product_url,
            "best_available_url": match.best_available_url,
            "url_decision_status": match.url_decision_status,
            "is_exact_product_match": match.is_exact_product_match,
            "is_scrapable": match.is_scrapable,
            "confidence": match.confidence,
            "serpapi_requests_used": match.organic_calls_used,
            "scrape_calls_used": match.scrape_calls_used,
            "llm_feature_reasoning_enabled": llm_enabled,
            "coding_status": evidence_set.status if evidence_set else "FEATURE_SCHEMA_NOT_EVALUATED",
            "coding_ready": evidence_set.coding_ready if evidence_set else False,
            "primary_evidence_url": evidence_set.primary_url if evidence_set else None,
            "supplementary_urls": "|".join(evidence_set.supplementary_urls) if evidence_set else "",
            "selected_evidence_urls": "|".join(evidence_set.selected_urls) if evidence_set else "",
            "total_feature_coverage": evidence_set.total_coverage if evidence_set else 0.0,
            "required_feature_coverage": evidence_set.required_coverage if evidence_set else 0.0,
            "critical_feature_coverage": evidence_set.critical_coverage if evidence_set else 0.0,
            "missing_features": "|".join(evidence_set.missing_features) if evidence_set else "",
            "conflicting_features": "|".join(evidence_set.conflicting_features) if evidence_set else "",
            "artifact_dir": result.artifact_dir,
            "status": "success",
            "error": None,
        }
    except Exception as exc:
        return {
            "row_id": product.row_id,
            "main_text": product.main_text,
            "country_code": product.country_code,
            "retailer_name": product.retailer_name,
            "ean": product.ean,
            "product_url": None,
            "best_available_url": None,
            "url_decision_status": "ERROR",
            "is_exact_product_match": False,
            "is_scrapable": False,
            "confidence": 0.0,
            "serpapi_requests_used": 0,
            "scrape_calls_used": 0,
            "llm_feature_reasoning_enabled": llm_enabled,
            "coding_status": "ERROR",
            "coding_ready": False,
            "primary_evidence_url": None,
            "supplementary_urls": "",
            "selected_evidence_urls": "",
            "total_feature_coverage": 0.0,
            "required_feature_coverage": 0.0,
            "critical_feature_coverage": 0.0,
            "missing_features": "",
            "conflicting_features": "",
            "artifact_dir": "",
            "status": "error",
            "error": str(exc),
        }


def write_summary(output_dir: Path, rows: list[dict[str, Any]], *, environment_checks: tuple[str, ...]) -> None:
    total = len(rows)
    resolved = sum(bool(row.get("product_url")) for row in rows)
    coding_ready = sum(bool(row.get("coding_ready")) for row in rows)
    errors = sum(row.get("status") == "error" for row in rows)
    serp_calls = sum(int(row.get("serpapi_requests_used") or 0) for row in rows)
    summary = {
        "total_products": total,
        "resolved_product_urls": resolved,
        "coding_ready_products": coding_ready,
        "errors": errors,
        "serpapi_requests_used": serp_calls,
        "average_serpapi_requests_per_product": round(serp_calls / max(1, total), 4),
        "one_credit_contract_respected": all(int(row.get("serpapi_requests_used") or 0) <= 1 for row in rows),
        "environment_checks": list(environment_checks),
    }
    (output_dir / "metrics.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Batch summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Products | {total} |",
        f"| Product URLs resolved | {resolved} |",
        f"| Coding-ready products | {coding_ready} |",
        f"| Errors | {errors} |",
        f"| SerpAPI requests | {serp_calls} |",
        f"| One-credit contract respected | {summary['one_credit_contract_respected']} |",
        "",
    ]
    (output_dir / "batch_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    # Validate exactly once before creating worker threads or making paid calls.
    environment = validate_runtime_environment(args.env_file)
    llm_max_calls = int(os.getenv("PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT", "2"))

    products = CSVProductIO.read_products(args.input)
    schema = load_feature_schema(args.feature_schema)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    workers = max(1, int(args.workers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                process,
                product,
                schema,
                args.env_file,
                llm_enabled=environment.llm_feature_reasoning_enabled,
                llm_max_calls=llm_max_calls,
            ): product.row_id
            for product in products
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Products"):
            rows.append(future.result())

    frame = pd.DataFrame(rows)
    if "row_id" in frame.columns:
        frame = frame.sort_values("row_id")
    frame.to_csv(output_path, index=False)
    review = frame[(frame["coding_ready"] != True) | (frame["status"] == "error")]  # noqa: E712
    review.to_csv(output_path.parent / "review_queue.csv", index=False)
    write_summary(output_path.parent, rows, environment_checks=environment.checks_passed)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
