from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.product_evidence_harness.contracts import OrganicSearchResponse, SerpAIResponse, URLCandidate
from src.product_evidence_harness.url_utils import domain_of, normalize_url, urls_from_text


@dataclass
class CandidateStore:
    max_pool_size: int = 40

    def merge_organic(self, existing: list[URLCandidate], response: OrganicSearchResponse) -> list[URLCandidate]:
        records = {c.url: self._record(c) for c in existing}
        for result in response.results:
            url = normalize_url(result.url)
            if not url:
                continue
            rec = records.setdefault(url, self._empty_record(url))
            rec["title"] = self._best(rec["title"], result.title)
            rec["snippet"] = self._best(rec["snippet"], result.snippet)
            section = (result.source or "organic_results").strip().lower().replace(" ", "_")
            rec["source_types"].add(f"serp_{section}")
            rec["organic_count"] += 1
            rec["query_sources"].add(response.query)
            if result.position is not None:
                rec["best_position"] = min(rec["best_position"] or int(result.position), int(result.position))
        return self._candidates(records)

    def merge_ai(self, existing: list[URLCandidate], response: SerpAIResponse) -> list[URLCandidate]:
        records = {c.url: self._record(c) for c in existing}
        final_url = self._extract_final_url(response.markdown)
        if final_url:
            self._merge(records, final_url, title="AI Mode declared FINAL_URL", snippet=response.markdown, source_type="ai_declared_final", ai_declared_final=True)
        for ref in response.references:
            self._merge(records, ref.link, title=ref.title, snippet=ref.snippet, source_type="ai_reference", ai_reference_count=1)
        for url in urls_from_text(response.markdown):
            self._merge(records, url, title="AI Mode markdown URL", snippet=response.markdown, source_type="ai_markdown")
        for url in self._urls_from_objects(response.text_blocks):
            self._merge(records, url, title="AI Mode block URL", snippet=response.markdown, source_type="ai_block")
        return self._candidates(records)

    def _merge(self, records: dict[str, dict[str, Any]], url: str, *, title: str, snippet: str, source_type: str, ai_reference_count: int = 0, ai_declared_final: bool = False) -> None:
        normalized = normalize_url(url)
        if not normalized:
            return
        rec = records.setdefault(normalized, self._empty_record(normalized))
        rec["title"] = self._best(rec["title"], title)
        rec["snippet"] = self._best(rec["snippet"], snippet)
        rec["source_types"].add(source_type)
        rec["ai_reference_count"] += ai_reference_count
        rec["ai_declared_final"] = rec["ai_declared_final"] or ai_declared_final

    def _extract_final_url(self, markdown: str) -> str | None:
        for line in (markdown or "").splitlines():
            if "FINAL_URL" in line.upper():
                parts = line.split(":", 1)
                if len(parts) == 2 and "NO_MATCH" not in parts[1].upper():
                    urls = urls_from_text(parts[1])
                    return urls[0] if urls else None
        return None

    def _urls_from_objects(self, obj: Any) -> list[str]:
        found: list[str] = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key.lower() in {"url", "link", "source", "href"} and isinstance(value, str):
                    found.extend(urls_from_text(value))
                else:
                    found.extend(self._urls_from_objects(value))
        elif isinstance(obj, list):
            for item in obj:
                found.extend(self._urls_from_objects(item))
        elif isinstance(obj, str):
            found.extend(urls_from_text(obj))
        return list(dict.fromkeys(found))

    def _empty_record(self, url: str) -> dict[str, Any]:
        return {
            "url": url,
            "title": "",
            "snippet": "",
            "domain": domain_of(url),
            "source_types": set(),
            "query_sources": set(),
            "best_position": None,
            "organic_count": 0,
            "ai_reference_count": 0,
            "ai_declared_final": False,
            "lifecycle_status": "DISCOVERED",
        }

    def _record(self, candidate: URLCandidate) -> dict[str, Any]:
        return {
            "url": candidate.url,
            "title": candidate.title,
            "snippet": candidate.snippet,
            "domain": candidate.domain,
            "source_types": set(candidate.source_types),
            "query_sources": set(candidate.query_sources),
            "best_position": candidate.best_position,
            "organic_count": candidate.organic_count,
            "ai_reference_count": candidate.ai_reference_count,
            "ai_declared_final": candidate.ai_declared_final,
            "lifecycle_status": candidate.lifecycle_status,
        }

    def _candidates(self, records: dict[str, dict[str, Any]]) -> list[URLCandidate]:
        candidates = [
            URLCandidate(
                url=r["url"],
                title=r["title"],
                snippet=r["snippet"],
                domain=r["domain"],
                source_types=tuple(sorted(r["source_types"])),
                query_sources=tuple(sorted(r["query_sources"])),
                best_position=r["best_position"],
                organic_count=r["organic_count"],
                ai_reference_count=r["ai_reference_count"],
                ai_declared_final=r["ai_declared_final"],
                lifecycle_status=r["lifecycle_status"],
            )
            for r in records.values()
        ]
        return sorted(
            candidates,
            key=lambda c: (
                c.ai_declared_final,
                len(c.source_types),
                c.organic_count,
                c.ai_reference_count,
                -(c.best_position or 999),
            ),
            reverse=True,
        )[: self.max_pool_size]

    @staticmethod
    def _best(old: str, new: str) -> str:
        return new if len(new or "") > len(old or "") else old
