from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class EvidenceRichnessBreakdown:
    title: float = 0.0
    description: float = 0.0
    specs: float = 0.0
    identifiers: float = 0.0
    brand: float = 0.0
    manufacturer: float = 0.0
    price: float = 0.0
    images: float = 0.0
    availability: float = 0.0
    final_score: float = 0.0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def score_richness(*, title: str = "", description: str = "", specs: dict | None = None, identifiers: tuple | list = (), brand: str = "", manufacturer: str = "", has_price: bool = False, image_count: int = 0, availability: str = "") -> EvidenceRichnessBreakdown:
    specs = specs or {}
    b = EvidenceRichnessBreakdown(
        title=0.08 if title else 0.0,
        description=min(0.18, len(description or "") / 1000 * 0.18),
        specs=min(0.18, len(specs) / 6 * 0.18),
        identifiers=0.14 if identifiers else 0.0,
        brand=0.08 if brand else 0.0,
        manufacturer=0.06 if manufacturer else 0.0,
        price=0.08 if has_price else 0.0,
        images=min(0.12, image_count / 3 * 0.12),
        availability=0.06 if availability else 0.0,
    )
    total = round(min(1.0, sum(v for k, v in b.__dict__.items() if k != "final_score")), 4)
    return EvidenceRichnessBreakdown(**{k: v for k, v in b.__dict__.items() if k != "final_score"}, final_score=total)
