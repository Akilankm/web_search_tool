from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

from serp_hybrid_url_finder.io_utils import CSVProductIO
from serp_hybrid_url_finder.models import ProductURLMatch
from serp_hybrid_url_finder.pipeline import HybridProductURLFinderPipeline


@dataclass
class ProductURLBatchRunner:
    """Batch-safe CSV runner: one bad row never kills the full batch."""

    pipeline: HybridProductURLFinderPipeline

    def run_csv(
        self,
        *,
        input_csv: str | Path,
        output_csv: str | Path,
        trace_output_dir: Optional[str | Path] = None,
    ) -> list[ProductURLMatch]:
        products = CSVProductIO.read_products(input_csv)
        logger.info("Loaded {} product row(s)", len(products))
        matches: list[ProductURLMatch] = []
        trace_root = Path(trace_output_dir) if trace_output_dir else None
        for idx, product in enumerate(products, start=1):
            logger.info("Running row {}/{} | row_id={}", idx, len(products), product.row_id)
            trace_dir = trace_root / product.row_id if trace_root else None
            result = self.pipeline.run(product, return_trace=False, trace_output_dir=trace_dir.parent if trace_dir else None)
            matches.append(result)  # type: ignore[arg-type]
            CSVProductIO.write_matches(output_csv, matches)
        return matches
