from __future__ import annotations

import re
from dataclasses import dataclass

from src.product_evidence_harness.gtin import is_valid_gtin

GTIN_CANDIDATE_REGEX = re.compile(r"(?<!\d)(\d[\d\s.-]{6,20}\d)(?!\d)")

@dataclass(frozen=True)
class IdentifierEvidence:
    value: str
    kind: str
    valid: bool
    source: str

    def to_dict(self) -> dict:
        return {"value": self.value, "kind": self.kind, "valid": self.valid, "source": self.source}


def extract_gtin_evidence(text: str, *, source: str = "text", max_items: int = 20) -> tuple[IdentifierEvidence, ...]:
    out: list[IdentifierEvidence] = []
    seen: set[str] = set()
    for raw in GTIN_CANDIDATE_REGEX.findall(text or ""):
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) not in {8, 12, 13, 14} or digits in seen:
            continue
        seen.add(digits)
        kind = {8: "EAN8", 12: "UPC_A", 13: "EAN13", 14: "GTIN14"}.get(len(digits), "GTIN")
        out.append(IdentifierEvidence(digits, kind, is_valid_gtin(digits), source))
        if len(out) >= max_items:
            break
    return tuple(out)
