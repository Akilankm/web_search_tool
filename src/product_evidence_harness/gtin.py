from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

_VALID_GTIN_LENGTHS = {8, 12, 13, 14}
_GTIN_LABEL_RE = re.compile(
    r"\b(?:ean|gtin|gtin[-_ ]?8|gtin[-_ ]?12|gtin[-_ ]?13|gtin[-_ ]?14|upc|barcode|bar\s*code)\b\D{0,40}(\d[\d\s.-]{6,20}\d)",
    flags=re.I,
)
_DIGIT_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class GTINComparison:
    requested_raw: str | None
    requested_normalized: str | None
    requested_valid: bool
    page_gtins_valid: tuple[str, ...]
    page_gtins_ignored: tuple[str, ...]
    match: bool
    conflict: bool
    status: str
    reason: str


def digits_only(value: object | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return "".join(ch for ch in text if ch.isdigit())


def is_valid_gtin(value: object | None) -> bool:
    digits = digits_only(value)
    return len(digits) in _VALID_GTIN_LENGTHS and _check_digit_ok(digits)


def normalize_gtin(value: object | None) -> str | None:
    digits = digits_only(value)
    if not digits or not is_valid_gtin(digits):
        return None
    return digits


def equivalent_gtins(value: object | None) -> set[str]:
    normalized = normalize_gtin(value)
    if not normalized:
        return set()
    out = {normalized}
    # UPC-A can be rendered as EAN-13 with a leading zero.
    if len(normalized) == 12:
        ean13 = "0" + normalized
        if is_valid_gtin(ean13):
            out.add(ean13)
    if len(normalized) == 13 and normalized.startswith("0"):
        upc12 = normalized[1:]
        if is_valid_gtin(upc12):
            out.add(upc12)
    return out


def extract_labeled_gtins(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Extract GTIN-like values only from safe labeled contexts.

    This intentionally avoids treating arbitrary phone/contact/order numbers as
    product identifiers. Returned values are split into valid GTINs and ignored
    digit strings for diagnostics.
    """
    valid: list[str] = []
    ignored: list[str] = []
    seen_valid: set[str] = set()
    seen_ignored: set[str] = set()
    for match in _GTIN_LABEL_RE.finditer(text or ""):
        candidate = digits_only(match.group(1))
        if not candidate:
            continue
        normalized = normalize_gtin(candidate)
        if normalized:
            if normalized not in seen_valid:
                seen_valid.add(normalized)
                valid.append(normalized)
        else:
            if candidate not in seen_ignored:
                seen_ignored.add(candidate)
                ignored.append(candidate)
    return tuple(valid), tuple(ignored)


def sanitize_structured_gtins(values: Iterable[object]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    valid: list[str] = []
    ignored: list[str] = []
    seen_valid: set[str] = set()
    seen_ignored: set[str] = set()
    for value in values or []:
        digits = digits_only(value)
        if not digits:
            continue
        normalized = normalize_gtin(digits)
        if normalized:
            if normalized not in seen_valid:
                seen_valid.add(normalized)
                valid.append(normalized)
        else:
            if digits not in seen_ignored:
                seen_ignored.add(digits)
                ignored.append(digits)
    return tuple(valid), tuple(ignored)


def compare_expected_to_page_gtins(
    requested: object | None,
    *,
    structured_values: Iterable[object] = (),
    page_text: str = "",
) -> GTINComparison:
    raw = digits_only(requested)
    requested_normalized = normalize_gtin(raw)
    requested_valid = bool(requested_normalized)
    if not raw:
        return GTINComparison(None, None, False, (), (), False, False, "NOT_PROVIDED", "input EAN/GTIN not provided")

    structured_valid, structured_ignored = sanitize_structured_gtins(structured_values)
    labeled_valid, labeled_ignored = extract_labeled_gtins(page_text or "")

    valid = tuple(dict.fromkeys([*structured_valid, *labeled_valid]))
    ignored = tuple(dict.fromkeys([*structured_ignored, *labeled_ignored]))

    if not requested_valid:
        return GTINComparison(raw, None, False, valid, ignored, False, False, "INPUT_INVALID", f"input EAN/GTIN {raw} failed GTIN checksum/length validation")

    expected_equivalents = equivalent_gtins(requested_normalized)
    page_equivalents: set[str] = set()
    for gtin in valid:
        page_equivalents.update(equivalent_gtins(gtin))

    # Exact requested string can be present in the page even when not captured by
    # a safe label; this is a positive signal only, never used to create conflict.
    all_page_digits = "".join(_DIGIT_RE.findall(page_text or ""))
    requested_appears_anywhere = requested_normalized in all_page_digits or any(eq in all_page_digits for eq in expected_equivalents)

    match = bool(expected_equivalents & page_equivalents) or requested_appears_anywhere
    conflict = bool(valid) and not match
    if match:
        return GTINComparison(raw, requested_normalized, True, valid or (requested_normalized,), ignored, True, False, "MATCHED", f"input EAN/GTIN {raw} matched page GTIN evidence")
    if conflict:
        return GTINComparison(raw, requested_normalized, True, valid, ignored, False, True, "CONFLICT", f"input EAN/GTIN {raw} does not match valid page GTIN(s): {', '.join(valid)}")
    return GTINComparison(raw, requested_normalized, True, (), ignored, False, False, "ABSENT", f"input EAN/GTIN {raw} was not found as labeled/structured page evidence")


def _check_digit_ok(digits: str) -> bool:
    body, check = digits[:-1], digits[-1]
    total = 0
    # From the right of the body, weights alternate 3, 1, 3, 1...
    for idx, ch in enumerate(reversed(body), start=1):
        total += int(ch) * (3 if idx % 2 == 1 else 1)
    expected = (10 - (total % 10)) % 10
    return expected == int(check)
