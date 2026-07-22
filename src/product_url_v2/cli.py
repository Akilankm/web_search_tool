from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from product_url_v2.config import load_config
from product_url_v2.metrics import BenchmarkCase, BenchmarkOutcome, calculate_metrics, release_failures
from product_url_v2.models import DeliveryStatus, ProductInput, to_jsonable
from product_url_v2.orchestrator import ProductURLOrchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="product-url", description="Resolve product text to an auditable direct product URL")
    parser.add_argument("--config", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    single = sub.add_parser("resolve")
    single.add_argument("--row-id", required=True)
    single.add_argument("--main-text", required=True)
    single.add_argument("--country-code", required=True)
    single.add_argument("--retailer-name")
    single.add_argument("--ean")
    single.add_argument("--language-code")
    single.add_argument("--feature-set", default="toy")

    batch = sub.add_parser("batch")
    batch.add_argument("--input", required=True)
    batch.add_argument("--output", required=True)
    batch.add_argument("--feature-set", default="toy")

    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--cases", required=True)
    benchmark.add_argument("--outcomes", required=True)
    benchmark.add_argument("--report")

    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == "benchmark":
        case_rows = list(csv.DictReader(Path(args.cases).open(encoding="utf-8-sig")))
        outcome_rows = list(csv.DictReader(Path(args.outcomes).open(encoding="utf-8-sig")))
        cases = [BenchmarkCase(str(row["row_id"]), str(row["expected_url"]), str(row.get("expected_product_id") or "")) for row in case_rows]
        outcomes = [BenchmarkOutcome(
            row_id=str(row["row_id"]),
            delivered_url=str(row.get("delivered_url") or "") or None,
            status=DeliveryStatus(str(row.get("status") or "FAILED")),
            correct_product=_csv_bool(row.get("correct_product")),
            direct_product_page=_csv_bool(row.get("direct_product_page")),
            expected_in_candidates=_csv_bool(row.get("expected_in_candidates")),
            latency_ms=int(float(row.get("latency_ms") or 0)),
            cost_units=float(row.get("cost_units") or 0),
        ) for row in outcome_rows]
        metrics = calculate_metrics(cases, outcomes)
        failures = release_failures(metrics, config.release_gates)
        report = {"metrics": to_jsonable(metrics), "release_passed": not failures, "failed_gates": list(failures)}
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        if args.report:
            Path(args.report).write_text(rendered + "\n", encoding="utf-8")
        return 0 if not failures else 3

    orchestrator = ProductURLOrchestrator(config)
    if args.command == "resolve":
        product = ProductInput(args.row_id, args.main_text, args.country_code, args.retailer_name, args.ean, args.language_code, args.feature_set)
        result = orchestrator.resolve(product)
        print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2))
        return 0 if result.decision.status.value in {"VERIFIED", "REVIEW_REQUIRED"} else 2

    rows = list(csv.DictReader(Path(args.input).open(encoding="utf-8-sig")))
    output_rows = []
    for index, row in enumerate(rows, start=1):
        product = ProductInput(
            row_id=str(row.get("row_id") or f"ROW-{index:06d}"),
            main_text=str(row.get("main_text") or row.get("MAIN_TEXT") or ""),
            country_code=str(row.get("country_code") or row.get("COUNTRY") or ""),
            retailer_name=row.get("retailer_name") or row.get("RETAILER") or None,
            ean=row.get("ean") or row.get("EAN") or None,
            language_code=row.get("language_code") or None,
            feature_set=args.feature_set,
        )
        result = orchestrator.resolve(product)
        output_rows.append({
            "row_id": product.row_id,
            "main_text": product.main_text,
            "country_code": product.country_code,
            "retailer_name": product.retailer_name or "",
            "ean": product.ean or "",
            "product_url": result.decision.selected_url or "",
            "delivery_status": result.decision.status.value,
            "confidence": result.decision.confidence,
            "coding_ready": result.decision.coding_ready,
            "justification": " ".join(result.decision.reasons),
            "artifact_dir": result.artifact_dir,
        })
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]) if output_rows else ["row_id"])
        writer.writeheader()
        writer.writerows(output_rows)
    return 0


def _csv_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "pass"}


if __name__ == "__main__":
    sys.exit(main())
