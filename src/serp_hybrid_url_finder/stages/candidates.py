from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

from loguru import logger

from serp_hybrid_url_finder.config import ProductURLPipelinePolicy
from serp_hybrid_url_finder.constants import URL_REGEX, URL_SOURCE_AI_DECLARED_FINAL, URL_SOURCE_AI_REFERENCE, URL_SOURCE_AI_TEXT, URL_SOURCE_ORGANIC, URL_TRAILING_CHARS_TO_STRIP
from serp_hybrid_url_finder.models import AIMatchEvidence, OrganicSearchResponse, SerpAIResponse, URLCandidate

_URL_PATTERN = re.compile(URL_REGEX, re.IGNORECASE)


@dataclass(frozen=True)
class CandidateCollector:
    policy: ProductURLPipelinePolicy

    def collect_from_organic(self, responses: list[OrganicSearchResponse]) -> list[URLCandidate]:
        records: dict[str, dict[str, Any]] = {}
        for response in responses:
            for result in response.results:
                normalized = self._normalize_url(result.url)
                if not normalized or self._is_blocked(normalized):
                    continue
                domain = self._domain(normalized)
                record = records.setdefault(
                    normalized,
                    {
                        "url": normalized,
                        "title": "",
                        "snippet": "",
                        "domain": domain,
                        "source_types": set(),
                        "best_position": None,
                        "organic_count": 0,
                        "ai_reference_count": 0,
                        "ai_declared_final": False,
                        "query_sources": set(),
                    },
                )
                record["title"] = self._best_text(record["title"], result.title)
                record["snippet"] = self._best_text(record["snippet"], result.snippet)
                record["source_types"].add(URL_SOURCE_ORGANIC)
                record["organic_count"] += 1
                record["query_sources"].add(response.query)
                if result.position is not None:
                    pos = int(result.position)
                    record["best_position"] = pos if record["best_position"] is None else min(record["best_position"], pos)
        candidates = [self._to_candidate(record) for record in records.values()]
        logger.info("Collected {} organic candidate(s)", len(candidates))
        return candidates

    def merge_ai_evidence(
        self,
        existing: list[URLCandidate],
        response: SerpAIResponse,
        evidence: AIMatchEvidence,
    ) -> list[URLCandidate]:
        records = {candidate.url: self._candidate_to_record(candidate) for candidate in existing}
        if evidence.final_url:
            self._merge_url(records, evidence.final_url, title="AI final recommendation", snippet=evidence.confidence_reason, source_type=URL_SOURCE_AI_DECLARED_FINAL, ai_declared_final=True)
        for url in evidence.additional_urls:
            self._merge_url(records, url, title="AI additional URL", snippet=evidence.confidence_reason, source_type=URL_SOURCE_AI_TEXT)
        for ref in response.references:
            self._merge_url(records, ref.link, title=ref.title, snippet=ref.snippet, source_type=URL_SOURCE_AI_REFERENCE, ai_reference_count=1)
        for url in self._urls_from_text(response.markdown):
            self._merge_url(records, url, title="AI markdown URL", snippet=response.markdown[:1000], source_type=URL_SOURCE_AI_TEXT)
        for url in self._urls_from_objects(response.text_blocks):
            self._merge_url(records, url, title="AI text-block URL", snippet="", source_type=URL_SOURCE_AI_TEXT)
        candidates = [self._to_candidate(record) for record in records.values()]
        logger.info("Candidate pool after AI merge: {}", len(candidates))
        return candidates

    def to_ai_candidate_text(self, candidates: list[URLCandidate], *, max_candidates: int) -> str:
        ranked = sorted(candidates, key=lambda c: (c.ai_declared_final, c.ai_reference_count, c.organic_count, -(c.best_position or 999)), reverse=True)[:max_candidates]
        lines: list[str] = []
        for idx, candidate in enumerate(ranked, start=1):
            lines.append(f"{idx}. URL: {candidate.url}")
            lines.append(f"   domain: {candidate.domain}")
            lines.append(f"   title: {candidate.title[:220]}")
            lines.append(f"   snippet: {candidate.snippet[:350]}")
            lines.append(f"   sources: {', '.join(candidate.source_types)}; best_position={candidate.best_position}; organic_count={candidate.organic_count}")
        return "\n".join(lines)

    def _merge_url(self, records: dict[str, dict[str, Any]], url: str, *, title: str, snippet: str, source_type: str, ai_reference_count: int = 0, ai_declared_final: bool = False) -> None:
        normalized = self._normalize_url(url)
        if not normalized or self._is_blocked(normalized):
            return
        record = records.setdefault(
            normalized,
            {
                "url": normalized,
                "title": "",
                "snippet": "",
                "domain": self._domain(normalized),
                "source_types": set(),
                "best_position": None,
                "organic_count": 0,
                "ai_reference_count": 0,
                "ai_declared_final": False,
                "query_sources": set(),
            },
        )
        record["title"] = self._best_text(record["title"], title)
        record["snippet"] = self._best_text(record["snippet"], snippet)
        record["source_types"].add(source_type)
        record["ai_reference_count"] += ai_reference_count
        record["ai_declared_final"] = bool(record["ai_declared_final"] or ai_declared_final)

    def _is_blocked(self, url: str) -> bool:
        lower = url.lower()
        if any(lower.endswith(ext) for ext in self.policy.blocked_url_extensions):
            return True
        domain = self._domain(url)
        return any(fragment in domain for fragment in self.policy.blocked_domain_fragments)

    @staticmethod
    def _normalize_url(url: str) -> str | None:
        clean = (url or "").strip().rstrip(URL_TRAILING_CHARS_TO_STRIP)
        if not clean:
            return None
        parsed = urlparse(clean)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        parsed = parsed._replace(fragment="")
        return urlunparse(parsed)

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower().replace("www.", "")

    @staticmethod
    def _best_text(current: str, new: str) -> str:
        return new if len(new or "") > len(current or "") else current

    @staticmethod
    def _urls_from_text(text: str) -> list[str]:
        return [match.group(0).rstrip(URL_TRAILING_CHARS_TO_STRIP) for match in _URL_PATTERN.finditer(text or "")]

    def _urls_from_objects(self, value: Any) -> list[str]:
        urls: list[str] = []
        if isinstance(value, str):
            return self._urls_from_text(value)
        if isinstance(value, dict):
            for item in value.values():
                urls.extend(self._urls_from_objects(item))
        elif isinstance(value, list):
            for item in value:
                urls.extend(self._urls_from_objects(item))
        return urls

    @staticmethod
    def _candidate_to_record(candidate: URLCandidate) -> dict[str, Any]:
        return {
            "url": candidate.url,
            "title": candidate.title,
            "snippet": candidate.snippet,
            "domain": candidate.domain,
            "source_types": set(candidate.source_types),
            "best_position": candidate.best_position,
            "organic_count": candidate.organic_count,
            "ai_reference_count": candidate.ai_reference_count,
            "ai_declared_final": candidate.ai_declared_final,
            "query_sources": set(candidate.query_sources),
        }

    @staticmethod
    def _to_candidate(record: dict[str, Any]) -> URLCandidate:
        return URLCandidate(
            url=record["url"],
            title=record.get("title", ""),
            snippet=record.get("snippet", ""),
            domain=record.get("domain", ""),
            source_types=tuple(sorted(record.get("source_types", set()))),
            best_position=record.get("best_position"),
            organic_count=int(record.get("organic_count") or 0),
            ai_reference_count=int(record.get("ai_reference_count") or 0),
            ai_declared_final=bool(record.get("ai_declared_final")),
            query_sources=tuple(sorted(record.get("query_sources", set()))),
        )
