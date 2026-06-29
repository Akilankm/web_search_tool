from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class ReviewFeedbackRecord:
    """Structured human-review feedback for future rule/ranking improvements."""

    row_id: str
    review_status: str
    accepted_url: str = ""
    rejected_url: str = ""
    correct_url: str = ""
    correct_brand: str = ""
    correct_manufacturer: str = ""
    correct_variant_notes: str = ""
    review_reason: str = ""
    reviewer_notes: str = ""
    quality_tier_at_review: str = ""
    failure_taxonomy_at_review: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewFeedbackStore:
    """Append-only JSONL store for reviewed outcomes.

    This is deliberately simple and local-file based. It gives the harness a
    foundation for self-improvement without introducing model training or any
    AzureML dependency.
    """

    path: str | Path

    def append(self, record: ReviewFeedbackRecord) -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def read_all(self) -> list[ReviewFeedbackRecord]:
        p = Path(self.path)
        if not p.exists():
            return []
        records: list[ReviewFeedbackRecord] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            payload["failure_taxonomy_at_review"] = tuple(payload.get("failure_taxonomy_at_review") or ())
            records.append(ReviewFeedbackRecord(**payload))
        return records

    def summarize(self) -> dict[str, Any]:
        records = self.read_all()
        reason_counts = Counter(r.review_reason or "UNKNOWN" for r in records)
        accepted_domains = Counter(_domain(r.accepted_url or r.correct_url) for r in records if (r.accepted_url or r.correct_url))
        rejected_domains = Counter(_domain(r.rejected_url) for r in records if r.rejected_url)
        failure_counts: Counter[str] = Counter()
        for r in records:
            failure_counts.update(r.failure_taxonomy_at_review)
        return {
            "reviewed_count": len(records),
            "review_reason_counts": dict(reason_counts),
            "accepted_domain_counts": dict(accepted_domains),
            "rejected_domain_counts": dict(rejected_domains),
            "failure_taxonomy_counts": dict(failure_counts),
        }


@dataclass
class RetailerDomainMemory:
    """Local retailer/domain operational memory.

    Tracks observed retailer/domain behavior across reviewed or completed runs:
    accepted domains, rejected domains, blocked/thin pages, and exact matches.
    It is intentionally a deterministic memory layer, not a trained model.
    """

    stats: dict[str, dict[str, Counter]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))

    def record(self, *, retailer_name: str, country_code: str, domain: str, outcome: str) -> None:
        key = self._key(retailer_name, country_code)
        self.stats[key]["domains"][domain] += 1
        self.stats[key]["outcomes"][outcome] += 1

    def preferred_domains(self, *, retailer_name: str, country_code: str, limit: int = 5) -> list[str]:
        key = self._key(retailer_name, country_code)
        return [d for d, _ in self.stats.get(key, {}).get("domains", Counter()).most_common(limit)]

    def to_dict(self) -> dict[str, Any]:
        return {
            key: {section: dict(counter) for section, counter in value.items()}
            for key, value in self.stats.items()
        }

    @classmethod
    def from_feedback(cls, records: list[ReviewFeedbackRecord]) -> "RetailerDomainMemory":
        memory = cls()
        for record in records:
            if record.correct_url:
                memory.record(retailer_name="UNKNOWN", country_code="UNKNOWN", domain=_domain(record.correct_url), outcome="accepted_review_url")
            if record.rejected_url:
                memory.record(retailer_name="UNKNOWN", country_code="UNKNOWN", domain=_domain(record.rejected_url), outcome="rejected_review_url")
        return memory

    @staticmethod
    def _key(retailer_name: str, country_code: str) -> str:
        return f"{(retailer_name or 'UNKNOWN').strip().lower()}::{(country_code or 'UNKNOWN').strip().upper()}"


def _domain(url: str) -> str:
    parsed = urlparse(url or "")
    return (parsed.netloc or url).lower().removeprefix("www.")
