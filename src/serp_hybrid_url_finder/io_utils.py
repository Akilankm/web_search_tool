from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List

from loguru import logger

from src.serp_hybrid_url_finder.models import ProductQuery, ProductURLMatch


class CSVProductIO:
    """Small CSV utility for notebook batch execution."""

    @staticmethod
    def read_products(path: str | Path) -> List[ProductQuery]:
        rows: list[ProductQuery] = []
        with Path(path).open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                main_text = (row.get("main_text") or "").strip()
                country_code = (row.get("country_code") or row.get("country") or "").strip()

                if not main_text:
                    logger.warning("Skipping row {}: missing required main_text", idx)
                    continue
                if not country_code:
                    logger.warning("Skipping row {}: missing required country_code", idx)
                    continue

                rows.append(
                    ProductQuery(
                        row_id=(row.get("row_id") or row.get("id") or str(idx)).strip(),
                        main_text=main_text,
                        country_code=country_code,
                        ean=(row.get("ean") or row.get("EAN") or "").strip() or None,
                        retailer_name=(row.get("retailer_name") or row.get("retailer") or "").strip() or None,
                    )
                )
        return rows

    @staticmethod
    def write_matches(path: str | Path, matches: Iterable[ProductURLMatch]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        items = list(matches)
        if not items:
            path.write_text("", encoding="utf-8")
            return

        fieldnames = list(items[0].to_dict().keys())
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in items:
                writer.writerow(item.to_dict())
