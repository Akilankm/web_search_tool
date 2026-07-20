from __future__ import annotations

import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.product_evidence_harness.notebook_runtime import (
    DEFAULT_FEATURE_SET,
    api_json,
    check_health,
    host_artifact_dir,
    submit_product,
    validate_result_contract,
    TERMINAL_STATUSES,
)

REQUIRED_BATCH_COLUMNS = ("main_text", "country_code")
OPTIONAL_BATCH_COLUMNS = ("row_id", "ean", "retailer_name", "language_code")
CANONICAL_BATCH_COLUMNS = (
    "row_id",
    "main_text",
    "ean",
    "retailer_name",
    "country_code",
    "language_code",
)

_COLUMN_ALIASES = {
    "row_id": "row_id",
    "rowid": "row_id",
    "id": "row_id",
    "main_text": "main_text",
    "maintext": "main_text",
    "product_text": "main_text",
    "product_description": "main_text",
    "description": "main_text",
    "ean": "ean",
    "gtin": "ean",
    "ean_gtin": "ean",
    "retailer": "retailer_name",
    "retailer_name": "retailer_name",
    "merchant": "retailer_name",
    "country": "country_code",
    "country_code": "country_code",
    "market": "country_code",
    "language": "language_code",
    "language_code": "language_code",
    "locale": "language_code",
}


@dataclass(slots=True)
class BatchRunReport:
    run_id: str
    output_dir: Path
    normalized_input_df: pd.DataFrame
    results_df: pd.DataFrame
    failures_df: pd.DataFrame
    artifact_index_df: pd.DataFrame
    summary: dict[str, Any]

    @property
    def elapsed_seconds(self) -> float:
        return float(self.summary.get("elapsed_seconds") or 0.0)


def _canonical_column(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return _COLUMN_ALIASES.get(normalized, normalized)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "<na>"} else text


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def load_batch_csv(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path).expanduser().resolve()
    if not csv_path.is_file():
        raise FileNotFoundError(f"Batch CSV was not found: {csv_path}")
    return pd.read_csv(csv_path, dtype=str, keep_default_na=False)


def normalize_batch_input(
    frame: pd.DataFrame,
    *,
    row_id_prefix: str = "BATCH",
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Batch input must be a pandas DataFrame")
    if frame.empty:
        raise ValueError("Batch input CSV contains no product rows")

    renamed: dict[str, str] = {}
    seen: dict[str, str] = {}
    for original in frame.columns:
        canonical = _canonical_column(original)
        if canonical in seen and seen[canonical] != original:
            raise ValueError(
                f"Multiple input columns map to '{canonical}': "
                f"{seen[canonical]!r} and {original!r}"
            )
        seen[canonical] = original
        renamed[original] = canonical

    normalized = frame.rename(columns=renamed).copy()
    missing = [column for column in REQUIRED_BATCH_COLUMNS if column not in normalized.columns]
    if missing:
        raise ValueError(
            "Batch CSV is missing mandatory columns: "
            + ", ".join(missing)
            + ". Accepted aliases include MAIN_TEXT/main_text and COUNTRY_CODE/country_code."
        )

    for column in CANONICAL_BATCH_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""

    for column in normalized.columns:
        normalized[column] = normalized[column].map(_clean_text)

    normalized["country_code"] = normalized["country_code"].str.upper()
    normalized["language_code"] = normalized["language_code"].str.lower()

    blank_main = normalized.index[normalized["main_text"] == ""].tolist()
    blank_country = normalized.index[normalized["country_code"] == ""].tolist()
    if blank_main or blank_country:
        details = []
        if blank_main:
            details.append(f"blank main_text rows={blank_main[:20]}")
        if blank_country:
            details.append(f"blank country_code rows={blank_country[:20]}")
        raise ValueError("Invalid batch input: " + "; ".join(details))

    generated = []
    for position, value in enumerate(normalized["row_id"], start=1):
        generated.append(value or f"{row_id_prefix}-{position:06d}")
    normalized["row_id"] = generated

    duplicated = normalized.loc[normalized["row_id"].duplicated(keep=False), "row_id"].tolist()
    if duplicated:
        raise ValueError(
            "row_id must be unique for artifact isolation. Duplicates: "
            + ", ".join(dict.fromkeys(duplicated))
        )

    canonical = list(CANONICAL_BATCH_COLUMNS)
    extras = [column for column in normalized.columns if column not in canonical]
    return normalized[canonical + extras].reset_index(drop=True)


def recommended_batch_parallelism() -> int:
    def _positive_int(name: str, default: int) -> int:
        try:
            return max(1, int(os.getenv(name, str(default))))
        except ValueError:
            return default

    agent_workers = _positive_int("AGENT_WORKERS", 2)
    browser_contexts = _positive_int("BROWSER_MAX_CONTEXTS", 3)
    return max(1, min(agent_workers, browser_contexts, 8))


def _product_payload(row: pd.Series) -> dict[str, Any]:
    return {
        "row_id": _clean_text(row.get("row_id")),
        "main_text": _clean_text(row.get("main_text")),
        "country_code": _clean_text(row.get("country_code")).upper(),
        "retailer_name": _clean_text(row.get("retailer_name")) or None,
        "ean": _clean_text(row.get("ean")) or None,
        "language_code": _clean_text(row.get("language_code")).lower() or None,
    }


def _wait_for_job_quiet(
    job_id: str,
    *,
    poll_seconds: int = 3,
) -> dict[str, Any]:
    while True:
        status = api_json("GET", f"/v1/jobs/{job_id}", timeout=30)
        if status.get("status") in TERMINAL_STATUSES:
            if status.get("status") == "FAILED":
                raise RuntimeError(
                    status.get("error")
                    or status.get("message")
                    or f"Product job failed: {job_id}"
                )
            return status
        time.sleep(poll_seconds)


def _result_record(
    *,
    row: pd.Series,
    result: dict[str, Any],
    job_id: str,
    elapsed_seconds: float,
    project_root: Path,
) -> dict[str, Any]:
    source_selection = dict(result.get("source_selection") or {})
    delivery = dict(result.get("url_delivery") or {})
    acceptance = dict(result.get("primary_url_acceptance") or {})
    search = dict(result.get("search") or {})
    judgement = dict(result.get("business_judgement_review") or {})
    visual = dict(judgement.get("visual_evidence_summary") or {})
    artifact_dir = host_artifact_dir(project_root, result)
    review_path = judgement.get("artifact_path")
    if artifact_dir and not review_path:
        review_path = artifact_dir / str(
            judgement.get("artifact_filename") or "business_judgement_review.md"
        )

    return {
        "row_id": row["row_id"],
        "main_text": row["main_text"],
        "ean": row["ean"],
        "retailer_name": row["retailer_name"],
        "country_code": row["country_code"],
        "language_code": row["language_code"],
        "job_id": job_id,
        "job_status": result.get("job_status"),
        "primary_url": result.get("primary_url"),
        "primary_url_role": result.get("primary_url_role"),
        "manufacturer_url": result.get("manufacturer_url"),
        "retailer_url": result.get("retailer_url"),
        "selection_reason": source_selection.get("selection_reason"),
        "selected_source_tier": source_selection.get("selected_source_tier_name"),
        "strict_primary_accepted": acceptance.get("accepted"),
        "strictly_verified": delivery.get("strictly_verified"),
        "url_delivered": delivery.get("delivered"),
        "search_credits_used": search.get("serpapi_requests_used"),
        "candidate_investigations": len(result.get("candidate_investigations") or []),
        "judgement_count": judgement.get("judgement_count"),
        "image_influenced_final_decision": visual.get("image_influenced_final_decision"),
        "artifact_dir": str(artifact_dir) if artifact_dir else result.get("artifact_dir"),
        "business_judgement_review_path": str(review_path) if review_path else "",
        "elapsed_seconds": round(elapsed_seconds, 2),
        "error": "",
    }


def _failure_record(
    *,
    row: pd.Series,
    job_id: str,
    elapsed_seconds: float,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "row_id": row["row_id"],
        "main_text": row["main_text"],
        "ean": row["ean"],
        "retailer_name": row["retailer_name"],
        "country_code": row["country_code"],
        "language_code": row["language_code"],
        "job_id": job_id,
        "job_status": "FAILED",
        "primary_url": "",
        "primary_url_role": "",
        "manufacturer_url": "",
        "retailer_url": "",
        "selection_reason": "",
        "selected_source_tier": "",
        "strict_primary_accepted": False,
        "strictly_verified": False,
        "url_delivered": False,
        "search_credits_used": 0,
        "candidate_investigations": 0,
        "judgement_count": 0,
        "image_influenced_final_decision": "",
        "artifact_dir": "",
        "business_judgement_review_path": "",
        "elapsed_seconds": round(elapsed_seconds, 2),
        "error": f"{type(exc).__name__}: {exc}",
    }


def run_batch_products(
    frame: pd.DataFrame,
    *,
    project_root: str | Path,
    feature_set: str = DEFAULT_FEATURE_SET,
    max_parallel: int | None = None,
    run_id: str | None = None,
    print_progress: bool = True,
) -> BatchRunReport:
    root = Path(project_root).resolve()
    normalized = normalize_batch_input(frame)
    check_health()

    configured_parallel = recommended_batch_parallelism()
    parallelism = configured_parallel if max_parallel is None else int(max_parallel)
    if parallelism < 1:
        raise ValueError("max_parallel must be at least 1")
    parallelism = min(parallelism, len(normalized), 8)

    run_id = run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    output_dir = root / "data" / "batch_runs" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    normalized.to_csv(output_dir / "batch_input_normalized.csv", index=False)

    started = time.monotonic()
    records: list[dict[str, Any]] = []

    def worker(row_dict: dict[str, Any]) -> dict[str, Any]:
        row = pd.Series(row_dict)
        job_id = ""
        item_started = time.monotonic()
        try:
            job_id = submit_product(_product_payload(row), feature_set)
            _wait_for_job_quiet(job_id)
            result = validate_result_contract(
                api_json("GET", f"/v1/jobs/{job_id}/result", timeout=120)
            )
            return _result_record(
                row=row,
                result=result,
                job_id=job_id,
                elapsed_seconds=time.monotonic() - item_started,
                project_root=root,
            )
        except Exception as exc:
            return _failure_record(
                row=row,
                job_id=job_id,
                elapsed_seconds=time.monotonic() - item_started,
                exc=exc,
            )

    rows = normalized.to_dict(orient="records")
    with ThreadPoolExecutor(max_workers=parallelism, thread_name_prefix="product-batch") as pool:
        future_to_row = {pool.submit(worker, row): row["row_id"] for row in rows}
        total = len(future_to_row)
        for completed, future in enumerate(as_completed(future_to_row), start=1):
            record = future.result()
            records.append(record)
            if print_progress:
                elapsed = max(time.monotonic() - started, 0.001)
                rate = completed / elapsed * 60.0
                print(
                    f"[{completed}/{total}] {record['row_id']} -> "
                    f"{record['job_status']} | {record['primary_url_role'] or 'NO_URL'} | "
                    f"{record['elapsed_seconds']:.1f}s | throughput={rate:.2f} products/min"
                )

    elapsed = time.monotonic() - started
    results_df = pd.DataFrame(records).sort_values("row_id").reset_index(drop=True)
    failures_df = results_df[results_df["job_status"] == "FAILED"].copy()
    artifact_index_df = results_df[
        [
            "row_id",
            "job_status",
            "primary_url",
            "primary_url_role",
            "artifact_dir",
            "business_judgement_review_path",
        ]
    ].copy()

    elapsed_series = pd.to_numeric(results_df["elapsed_seconds"], errors="coerce").dropna()
    search_series = pd.to_numeric(results_df["search_credits_used"], errors="coerce").fillna(0)
    status_counts = {
        str(key): int(value)
        for key, value in results_df["job_status"].value_counts(dropna=False).items()
    }
    summary = {
        "run_id": run_id,
        "feature_set": feature_set,
        "input_rows": int(len(normalized)),
        "max_parallel": int(parallelism),
        "recommended_parallelism": int(configured_parallel),
        "agent_workers_environment": os.getenv("AGENT_WORKERS", "2"),
        "browser_contexts_environment": os.getenv("BROWSER_MAX_CONTEXTS", "3"),
        "status_counts": status_counts,
        "successful_or_review_rows": int(
            results_df["job_status"].isin(["COMPLETED", "REVIEW_REQUIRED"]).sum()
        ),
        "failed_rows": int((results_df["job_status"] == "FAILED").sum()),
        "elapsed_seconds": round(elapsed, 2),
        "throughput_products_per_minute": round(len(normalized) / max(elapsed, 0.001) * 60.0, 3),
        "mean_product_elapsed_seconds": round(float(elapsed_series.mean()), 2)
        if not elapsed_series.empty
        else None,
        "p50_product_elapsed_seconds": round(float(elapsed_series.quantile(0.50)), 2)
        if not elapsed_series.empty
        else None,
        "p95_product_elapsed_seconds": round(float(elapsed_series.quantile(0.95)), 2)
        if not elapsed_series.empty
        else None,
        "total_serpapi_credits_used": int(search_series.sum()),
        "output_dir": str(output_dir),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    results_df.to_csv(output_dir / "batch_results.csv", index=False)
    failures_df.to_csv(output_dir / "batch_failures.csv", index=False)
    artifact_index_df.to_csv(output_dir / "batch_artifact_index.csv", index=False)
    _json_dump(output_dir / "batch_run_summary.json", summary)

    return BatchRunReport(
        run_id=run_id,
        output_dir=output_dir,
        normalized_input_df=normalized,
        results_df=results_df,
        failures_df=failures_df,
        artifact_index_df=artifact_index_df,
        summary=summary,
    )
