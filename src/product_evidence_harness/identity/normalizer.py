from __future__ import annotations

import re
import unicodedata
from typing import Iterable

TOKEN_REGEX = r"[a-zA-Z0-9À-ž]+"


def fold_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def segment_compact_text(text: str) -> str:
    """Segment compact ecommerce strings without relying on product-specific rules.

    Examples:
    - ABC123RED -> ABC 123 RED
    - 1001KARTENA5FLIEDER -> 1001 KARTEN A5 FLIEDER
    - LEGOFRIENDS41731 -> LEGOFRIENDS 41731
    """
    t = str(text or "")
    # common paper/model formats: text + A5/B6 + text
    t = re.sub(r"([A-Za-zÀ-ž]+)([ABCabc][0-9]{1,2})([A-Za-zÀ-ž]+)", r"\1 \2 \3", t)
    t = re.sub(r"(\d)([A-Za-zÀ-ž])", r"\1 \2", t)
    t = re.sub(r"([A-Za-zÀ-ž])([0-9])", r"\1 \2", t)
    t = re.sub(r"[_/|]+", " ", t)
    t = re.sub(r"[-]+", " ", t)
    # Rejoin paper/format codes split by the generic letter-digit rules.
    t = re.sub(r"\b([ABCabc])\s+([0-9]{1,2})\b", r"\1\2", t)
    t = re.sub(r"\b(\d+(?:[.,]\d+)?)\s+(mm|cm|m|inch|in|ml|l|g|kg)\b", r"\1\2", t, flags=re.I)
    return " ".join(t.split())


def compact_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", fold_text(text))


def tokens(text: str, *, min_len: int = 2, keep_formats: bool = True) -> list[str]:
    segmented = segment_compact_text(text)
    out: list[str] = []
    for tok in re.findall(TOKEN_REGEX, fold_text(segmented)):
        is_format = bool(re.fullmatch(r"[abc]\d{1,2}", tok))
        if len(tok) < min_len and not (keep_formats and is_format):
            continue
        out.append(tok)
    return list(dict.fromkeys(out))


def contains_token(text: str, token: str) -> bool:
    f = fold_text(text)
    t = fold_text(token)
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", f))


def quoted(text: str) -> str:
    text = " ".join(str(text or "").split())
    return f'"{text}"' if text else ""


def join_unique(values: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = " ".join(str(value or "").split())
        if not clean:
            continue
        key = fold_text(clean)
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return tuple(out)
