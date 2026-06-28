from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.product_evidence_harness.contracts import ProductQuery, ProductURLMatch


_COLUMN_ALIASES = {
    "row_id": ["row_id", "ROW_ID", "ID", "id", "serial_id", "SERIAL_ID"],
    "main_text": ["MAIN_TEXT", "main_text", "Main Text", "product_text", "PRODUCT_TEXT"],
    "country_code": ["COUNTRY", "country", "COUNTRY_CODE", "country_code", "Country Code"],
    "retailer_name": ["RETAILER", "retailer", "RETAILER_NAME", "retailer_name", "Retailer Name"],
    "ean": ["EAN", "ean", "GTIN", "gtin", "barcode", "BARCODE"],
    "language_code": ["LANGUAGE", "language", "LANGUAGE_CODE", "language_code", "lang", "hl"],
    "region": ["REGION", "region", "market", "MARKET"],
}


def _get(row: Any, logical_name: str, default: Any = None) -> Any:
    for col in _COLUMN_ALIASES[logical_name]:
        try:
            value = row.get(col)
        except Exception:
            value = None
        if value is not None and str(value).strip() != "":
            return value
    return default


@dataclass(frozen=True)
class CSVProductIO:
    @staticmethod
    def read_products(path: str | Path) -> list[ProductQuery]:
        df = pd.read_csv(path, dtype=str, keep_default_na=False) if str(path).lower().endswith(".csv") else pd.read_excel(path, dtype=str, keep_default_na=False)
        products: list[ProductQuery] = []
        for idx, row in df.iterrows():
            products.append(ProductQuery(
                row_id=str(_get(row, "row_id", f"row-{idx+1}")),
                main_text=_get(row, "main_text"),
                country_code=_get(row, "country_code"),
                retailer_name=_get(row, "retailer_name"),
                ean=_get(row, "ean"),
                language_code=_get(row, "language_code"),
                region=_get(row, "region"),
            ))
        return products

    @staticmethod
    def write_matches(path: str | Path, matches: Iterable[ProductURLMatch]) -> None:
        """Write a compact final-submission CSV from match objects.

        For full row evidence, use the per-row markdown artifact packet written by
        ProductEvidenceHarness/ArtifactWriter.
        """
        rows = []
        for m in matches:
            rows.append({
                "row_id": m.row_id,
                "main_text": m.main_text,
                "country_code": m.country_code,
                "ean": m.ean,
                "retailer_name": m.retailer_name,
                "product_url": m.product_url,
                "verified_exact_url": m.verified_exact_url,
                "best_available_url": m.best_available_url,
                "best_reference_url": m.best_reference_url,
                "url_decision_status": m.url_decision_status,
                "selection_scope": m.selection_scope,
                "selected_domain": m.selected_domain,
                "selected_retailer_name": m.selected_retailer_name,
                "is_exact_product_match": m.is_exact_product_match,
                "is_scrapable": m.is_scrapable,
                "needs_review": m.needs_review,
                "confidence": m.confidence,
                "requested_retailer_attempted": m.requested_retailer_attempted,
                "requested_retailer_scrapability_status": m.requested_retailer_scrapability_status,
                "requested_retailer_escape_reason": m.requested_retailer_escape_reason,
                "selected_from_requested_retailer": m.selected_from_requested_retailer,
                "selected_from_other_country_retailer": m.selected_from_other_country_retailer,
                "selected_from_global_fallback": m.selected_from_global_fallback,
                "organic_calls_used": m.organic_calls_used,
                "ai_mode_calls_used": m.ai_mode_calls_used,
                "llm_calls_used": m.llm_calls_used,
                "scrape_calls_used": m.scrape_calls_used,
                "llm_decision": m.llm_decision,
                "final_justification": m.justification or m.llm_justification or m.match_reason,
            })
        pd.DataFrame(rows).astype({"ean": "string"}, errors="ignore").to_csv(path, index=False)
