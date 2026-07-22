from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from product_url_v2.models import CandidateAssessment, ResolutionResult, to_jsonable


class ArtifactWriter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def prepare(self, row_id: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / row_id
        path.mkdir(parents=True, exist_ok=True)
        # Agent and browser containers use distinct UIDs but a shared runtime GID.
        # The setgid directory keeps browser screenshots and agent artifacts in the
        # same writable group without running either service as root.
        path.chmod(0o2775)
        return path

    def write_intermediate(
        self,
        row_id: str,
        *,
        input_payload: Mapping[str, Any] | None = None,
        interpretation: Any = None,
        search: Any = None,
        candidates: Sequence[CandidateAssessment] | None = None,
    ) -> Path:
        path = self.prepare(row_id)
        if input_payload is not None:
            self._json(path / "input.json", input_payload)
        if interpretation is not None:
            self._json(path / "interpretation.json", interpretation)
        if search is not None:
            self._json(path / "search.json", search)
        if candidates is not None:
            self._json(path / "candidates.json", candidates)
            self._candidate_csv(path / "candidates.csv", candidates)
        return path

    def finalize(self, result: ResolutionResult) -> Path:
        path = self.prepare(result.product.row_id)
        self._json(path / "decision.json", result.decision)
        self._json(path / "result.json", result)
        self._audit(path / "audit.md", result)
        return path

    @staticmethod
    def _json(path: Path, value: Any) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(to_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
        path.chmod(0o664)

    @staticmethod
    def _candidate_csv(path: Path, candidates: Sequence[CandidateAssessment]) -> None:
        columns = [
            "candidate_id", "url", "domain", "source_role", "identity_match",
            "identity_confidence", "direct_product_page", "direct_page_score",
            "browser_access", "text_extractable", "coding_evidence_complete",
            "country_match", "retailer_match", "source_authority", "conflicts", "warnings",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for item in candidates:
                data = to_jsonable(item)
                writer.writerow({key: " | ".join(data[key]) if isinstance(data.get(key), list) else data.get(key) for key in columns})
        path.chmod(0o664)

    @staticmethod
    def _audit(path: Path, result: ResolutionResult) -> None:
        lines = [
            f"# Product URL resolution audit — {result.product.row_id}",
            "",
            f"- Runtime contract: `{result.runtime_contract}`",
            f"- Input: `{result.product.main_text}`",
            f"- Country: `{result.product.country_code}`",
            f"- Delivery status: `{result.decision.status.value}`",
            f"- Selected URL: {result.decision.selected_url or 'None'}",
            f"- Confidence: {result.decision.confidence:.3f}",
            f"- Elapsed: {result.elapsed_ms} ms",
            "",
            "## Decision reasons",
            "",
            *[f"- {item}" for item in result.decision.reasons],
            "",
            "## Warnings",
            "",
            *([f"- {item}" for item in result.decision.warnings] or ["- None"]),
            "",
            "## Stage trace",
            "",
            "| # | Stage | Event | Message |",
            "|---:|---|---|---|",
            *[f"| {item.sequence} | {item.stage.value} | {item.event_type} | {item.message.replace('|', '/')} |" for item in result.events],
            "",
            "## Candidate decisions",
            "",
            "| Candidate | Identity | Direct page | Browser | Coding | URL |",
            "|---|---|---|---|---|---|",
            *[f"| {item.candidate_id} | {item.identity_match.value} ({item.identity_confidence:.3f}) | {item.direct_product_page.value} | {item.browser_access.value} | {item.coding_evidence_complete.value} | {item.url} |" for item in result.candidates],
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        path.chmod(0o664)
