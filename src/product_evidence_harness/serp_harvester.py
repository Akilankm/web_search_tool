from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

from src.product_evidence_harness.contracts import OrganicSearchResult
from src.product_evidence_harness.url_utils import normalize_url


@dataclass(frozen=True, slots=True)
class GoogleSERPHarvester:
    """Harvest external candidate URLs from one Google SerpAPI response.

    The harvester never follows pagination or SerpAPI links. It extracts useful
    external URLs already present in the paid response so the search budget stays
    at one request per product.
    """

    allowed_sections: tuple[str, ...] = (
        "organic_results",
        "shopping_results",
        "inline_shopping_results",
        "product_results",
        "product_sites",
        "local_results",
        "knowledge_graph",
        "related_questions",
        "images_results",
    )

    def harvest(self, payload: dict[str, Any], *, query: str, search_id: str | None, status: str) -> list[OrganicSearchResult]:
        harvested: list[OrganicSearchResult] = []
        for section in self.allowed_sections:
            value = payload.get(section)
            if value is None:
                continue
            for item in self._records(value):
                for url, title, snippet, position in self._urls_from_record(item):
                    normalized = normalize_url(url)
                    if not normalized or not self._is_external_candidate(normalized):
                        continue
                    harvested.append(
                        OrganicSearchResult(
                            url=normalized,
                            title=title,
                            snippet=snippet,
                            displayed_link=str(item.get("displayed_link") or ""),
                            source=section,
                            position=position,
                            query=query,
                            search_id=search_id,
                            search_status=status,
                        )
                    )
        return sorted(
            harvested,
            key=lambda item: (
                self._section_priority(item.source),
                -(item.position or 999),
                len(item.title) + len(item.snippet),
            ),
            reverse=True,
        )

    def _records(self, value: Any) -> Iterable[dict[str, Any]]:
        if isinstance(value, dict):
            yield value
            for nested in value.values():
                yield from self._records(nested)
        elif isinstance(value, list):
            for item in value:
                yield from self._records(item)

    def _urls_from_record(self, item: dict[str, Any]) -> Iterable[tuple[str, str, str, int | None]]:
        title = str(item.get("title") or item.get("name") or item.get("product_title") or "")
        snippet = str(item.get("snippet") or item.get("description") or item.get("source") or "")
        position = self._position(item.get("position") or item.get("rank"))
        for key in ("link", "url", "website", "product_link", "source_link"):
            value = item.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                yield value, title, snippet, position

    @staticmethod
    def _position(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_external_candidate(url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if not host:
            return False
        blocked_hosts = {
            "serpapi.com",
            "google.com",
            "googleusercontent.com",
            "gstatic.com",
            "youtube.com",
            "youtu.be",
        }
        if host in blocked_hosts or any(host.endswith("." + blocked) for blocked in blocked_hosts):
            return False
        return True

    @staticmethod
    def _section_priority(section: str) -> int:
        priorities = {
            "organic_results": 100,
            "product_results": 95,
            "product_sites": 92,
            "shopping_results": 90,
            "inline_shopping_results": 88,
            "knowledge_graph": 80,
            "local_results": 70,
            "related_questions": 55,
            "images_results": 35,
        }
        return priorities.get(section, 0)
