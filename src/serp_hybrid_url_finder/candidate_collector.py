from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, List
from urllib.parse import urlparse

from loguru import logger

from src.serp_hybrid_url_finder.constants import (
    AI_FINAL_URL_LINE_REGEX,
    AI_NO_MATCH_VALUE,
    BLOCKED_DOMAINS,
    BLOCKED_EXTENSIONS,
    URL_OBJECT_LINK_KEYS,
    URL_REGEX,
    URL_SOURCE_AI_DECLARED_FINAL,
    URL_SOURCE_AI_MARKDOWN,
    URL_SOURCE_AI_REFERENCE,
    URL_SOURCE_AI_TEXT_BLOCK,
    URL_SOURCE_ORGANIC_1,
    URL_SOURCE_ORGANIC_2,
    URL_TRAILING_CHARS_TO_STRIP,
    VALID_URL_SCHEMES,
)
from src.serp_hybrid_url_finder.models import OrganicSearchResponse, SerpAIResponse, URLCandidate

_URL_PATTERN = re.compile(URL_REGEX, re.IGNORECASE)
_FINAL_URL_PATTERN = re.compile(AI_FINAL_URL_LINE_REGEX, re.IGNORECASE)


@dataclass(frozen=True)
class CandidateCollector:
    """Collects and deduplicates URL candidates from organic and AI outputs."""

    blocked_domains: tuple[str, ...] = BLOCKED_DOMAINS

    def collect_from_organic(
        self,
        responses: list[OrganicSearchResponse],
    ) -> list[URLCandidate]:
        records: dict[str, dict[str, Any]] = {}

        for response_idx, response in enumerate(responses, start=1):
            source_type = URL_SOURCE_ORGANIC_1 if response_idx == 1 else URL_SOURCE_ORGANIC_2
            for result in response.results:
                normalized = self._normalize_url(result.url)
                if not normalized or self._is_blocked(normalized):
                    continue

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

                record["title"] = self._best_text(record["title"], result.title)
                record["snippet"] = self._best_text(record["snippet"], result.snippet)
                record["source_types"].add(source_type)
                record["organic_count"] += 1
                record["query_sources"].add(response.query)

                if result.position is not None:
                    if record["best_position"] is None:
                        record["best_position"] = int(result.position)
                    else:
                        record["best_position"] = min(record["best_position"], int(result.position))

        candidates = [self._to_candidate(record) for record in records.values()]
        logger.info("Collected {} organic candidate(s)", len(candidates))
        return candidates

    def merge_ai_response(
        self,
        existing: list[URLCandidate],
        response: SerpAIResponse,
    ) -> list[URLCandidate]:
        records = {candidate.url: self._candidate_to_record(candidate) for candidate in existing}

        final_url = self._extract_declared_final_url(response.markdown)
        if final_url:
            self._merge_url(
                records,
                final_url,
                title="AI Mode declared FINAL_URL",
                snippet=response.markdown,
                source_type=URL_SOURCE_AI_DECLARED_FINAL,
                ai_declared_final=True,
            )

        for ref in response.references:
            self._merge_url(
                records,
                ref.link,
                title=ref.title,
                snippet=ref.snippet,
                source_type=URL_SOURCE_AI_REFERENCE,
                ai_reference_count=1,
            )

        for url in self._urls_from_text(response.markdown):
            self._merge_url(
                records,
                url,
                title="AI Mode markdown URL",
                snippet=response.markdown,
                source_type=URL_SOURCE_AI_MARKDOWN,
            )

        for url in self._urls_from_objects(response.text_blocks):
            self._merge_url(
                records,
                url,
                title="AI Mode text block URL",
                snippet=response.markdown,
                source_type=URL_SOURCE_AI_TEXT_BLOCK,
            )

        candidates = [self._to_candidate(record) for record in records.values()]
        logger.info("Merged AI response; candidate pool size={}", len(candidates))
        return candidates

    def to_ai_candidate_text(
        self,
        candidates: list[URLCandidate],
        *,
        max_candidates: int,
    ) -> str:
        ranked = sorted(
            candidates,
            key=lambda c: (
                c.ai_declared_final,
                c.organic_count,
                -(c.best_position or 999),
                c.ai_reference_count,
            ),
            reverse=True,
        )[:max_candidates]

        lines: list[str] = []
        for idx, candidate in enumerate(ranked, start=1):
            lines.append(f"{idx}. url: {candidate.url}")
            lines.append(f"   title: {candidate.title[:300]}")
            lines.append(f"   snippet: {candidate.snippet[:600]}")
            lines.append(f"   domain: {candidate.domain}")
            lines.append(f"   source_types: {', '.join(candidate.source_types)}")
            lines.append(f"   best_organic_position: {candidate.best_position}")
            lines.append("")

        return "\n".join(lines).strip()

    def _merge_url(
        self,
        records: dict[str, dict[str, Any]],
        url: str,
        *,
        title: str,
        snippet: str,
        source_type: str,
        ai_reference_count: int = 0,
        ai_declared_final: bool = False,
    ) -> None:
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

    def _candidate_to_record(self, candidate: URLCandidate) -> dict[str, Any]:
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

    def _to_candidate(self, record: dict[str, Any]) -> URLCandidate:
        return URLCandidate(
            url=record["url"],
            title=record["title"],
            snippet=record["snippet"],
            domain=record["domain"],
            source_types=tuple(sorted(record["source_types"])),
            best_position=record["best_position"],
            organic_count=int(record["organic_count"]),
            ai_reference_count=int(record["ai_reference_count"]),
            ai_declared_final=bool(record["ai_declared_final"]),
            query_sources=tuple(sorted(record["query_sources"])),
        )

    def _extract_declared_final_url(self, markdown: str) -> str:
        if not markdown:
            return ""
        match = _FINAL_URL_PATTERN.search(markdown)
        if not match:
            return ""
        value = match.group(1).strip().rstrip(URL_TRAILING_CHARS_TO_STRIP)
        if value.upper() == AI_NO_MATCH_VALUE:
            return ""
        return value

    def _urls_from_text(self, text: str) -> Iterable[str]:
        if not text:
            return []
        return _URL_PATTERN.findall(text)

    def _urls_from_objects(self, obj: Any) -> Iterable[str]:
        found: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                found.extend(_URL_PATTERN.findall(value))
                if value.startswith("http://") or value.startswith("https://"):
                    found.append(value)
            elif isinstance(value, dict):
                for key, child in value.items():
                    if key.lower() in URL_OBJECT_LINK_KEYS and isinstance(child, str):
                        found.append(child)
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(obj)
        return found

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""

        clean = url.strip().rstrip(URL_TRAILING_CHARS_TO_STRIP)
        parsed = urlparse(clean)

        if parsed.scheme not in VALID_URL_SCHEMES:
            return ""
        if not parsed.netloc:
            return ""
        if parsed.path.lower().endswith(BLOCKED_EXTENSIONS):
            return ""
        return clean

    def _is_blocked(self, url: str) -> bool:
        domain = self._domain(url)
        if any(domain == blocked or domain.endswith(f".{blocked}") for blocked in self.blocked_domains):
            return True
        return urlparse(url).path.lower().endswith(BLOCKED_EXTENSIONS)

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc.lower().replace("www.", "")

    def _best_text(self, current: str, new: str) -> str:
        if not current:
            return new or ""
        if new and len(new) > len(current):
            return new
        return current
