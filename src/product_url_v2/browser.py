from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests

from product_url_v2.config import BrowserConfig
from product_url_v2.models import BrowserEvidence, CandidateAssessment, GateStatus, SourceRole


@dataclass(slots=True)
class BrowserClient:
    config: BrowserConfig
    token: str = ""
    session: requests.Session | None = None

    @classmethod
    def from_env(cls, config: BrowserConfig) -> "BrowserClient":
        token = str(os.getenv("BROWSER_API_TOKEN") or "").strip()
        token_file = str(os.getenv("BROWSER_API_TOKEN_FILE") or "").strip()
        if not token and token_file and Path(token_file).is_file():
            token = Path(token_file).read_text(encoding="utf-8").strip()
        return cls(config=config, token=token)

    def health(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {"status": "disabled"}
        try:
            response = (self.session or requests).get(
                f"{self.config.base_url}/health",
                headers=self._headers(),
                timeout=min(15, self.config.timeout_seconds),
            )
            response.raise_for_status()
            data = response.json()
            return dict(data) if isinstance(data, Mapping) else {"status": "invalid"}
        except Exception as exc:
            return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}

    def investigate(self, url: str, row_id: str, candidate_id: str) -> BrowserEvidence:
        if not self.config.enabled:
            return BrowserEvidence(url=url, access=GateStatus.NOT_ASSESSED, error="browser disabled")
        try:
            response = (self.session or requests).post(
                f"{self.config.base_url}/investigate",
                headers=self._headers(),
                json={"url": url, "row_id": row_id, "candidate_id": candidate_id},
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, Mapping):
                raise ValueError("browser service returned non-object JSON")
            return BrowserEvidence(
                url=url,
                access=GateStatus(str(data.get("access") or "FAIL")),
                final_url=str(data.get("final_url") or ""),
                title=str(data.get("title") or ""),
                visible_text=str(data.get("visible_text") or "")[:200000],
                screenshot_path=str(data.get("screenshot_path") or ""),
                product_controls=tuple(str(item) for item in data.get("product_controls") or []),
                error=str(data.get("error") or ""),
            )
        except Exception as exc:
            return BrowserEvidence(url=url, access=GateStatus.NOT_ASSESSED, error=f"{type(exc).__name__}: {exc}")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}


def select_browser_candidates(
    candidates: Sequence[CandidateAssessment],
    limit: int,
) -> tuple[CandidateAssessment, ...]:
    if limit <= 0:
        return ()
    eligible = [
        item for item in candidates
        if item.browser_access is GateStatus.NOT_ASSESSED
        and item.direct_product_page is not GateStatus.FAIL
        and item.identity_match.value != "MISMATCH"
        and not item.conflicts
    ]
    ranked = sorted(
        eligible,
        key=lambda item: (
            item.identity_confidence,
            item.direct_page_score,
            item.source_authority,
            item.search_support,
            -(item.search_rank or 9999),
        ),
        reverse=True,
    )
    selected: list[CandidateAssessment] = []

    def add(predicate) -> None:
        for item in ranked:
            if len(selected) >= limit:
                return
            if item not in selected and predicate(item):
                selected.append(item)
                return

    add(lambda item: item.source_role in {SourceRole.LOCAL_MANUFACTURER, SourceRole.GLOBAL_MANUFACTURER})
    add(lambda item: item.source_role in {SourceRole.REQUESTED_RETAILER, SourceRole.COUNTRY_RETAILER})
    selected_domains = {item.domain for item in selected}
    add(lambda item: item.domain not in selected_domains)
    for item in ranked:
        if len(selected) >= limit:
            break
        if item not in selected:
            selected.append(item)
    return tuple(selected)
