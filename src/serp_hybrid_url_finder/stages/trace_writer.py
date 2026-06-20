from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from serp_hybrid_url_finder.models import PipelineTrace


@dataclass(frozen=True)
class TraceWriter:
    root_dir: Path | str

    def write(self, trace: PipelineTrace) -> Path:
        row_id = self._safe_name(trace.product_query.row_id or trace.product_signature.fingerprint)
        out = Path(self.root_dir) / row_id
        out.mkdir(parents=True, exist_ok=True)
        self._write_json(out / "00_input.json", trace.product_query.to_dict())
        self._write_json(out / "01_product_signature.json", trace.product_signature.to_dict())
        self._write_json(out / "02_country_context.json", trace.country_context.to_dict())
        self._write_json(out / "03_retailer_resolution.json", trace.retailer_resolution.to_dict())
        self._write_json(out / "04_search_plan.json", trace.search_plan.to_dict())
        self._write_json(out / "05_organic_responses.json", [response.to_dict() for response in trace.organic_responses])
        self._write_json(out / "06_candidates.json", [candidate.to_dict() for candidate in trace.candidates])
        self._write_json(out / "07_ai_validation.json", {"query": trace.ai_validation_query, "response": trace.ai_validation_response.to_dict(), "evidence": trace.ai_validation_evidence.to_dict()})
        self._write_json(out / "08_scrapes.json", {url: scrape.to_dict() for url, scrape in trace.scrapes.items()})
        for idx, scrape in enumerate(trace.scrapes.values(), start=1):
            (out / f"08_scrape_{idx:02d}.md").write_text(scrape.markdown_excerpt or "", encoding="utf-8")
        self._write_json(out / "09_verifications.json", {url: verification.to_dict() for url, verification in trace.verifications.items()})
        self._write_json(out / "10_ranked_candidates.json", [candidate.to_dict() for candidate in trace.scored_candidates])
        self._write_json(out / "11_final_decision.json", trace.best_match.to_dict())
        self._write_json(out / "trace.json", trace.to_dict())
        return out

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value or "row")[:120]
