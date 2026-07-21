from __future__ import annotations

from typing import Any


def safe_int(
    value: Any,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    field_name: str = "value",
    strict: bool = False,
) -> int:
    """Convert untrusted external data to an integer safely.

    Environment variables, Streamlit state, browser payloads, LLM responses and
    search-planner counters may be null, blank or malformed. Non-strict mode
    falls back to ``default``. Strict mode raises a field-specific ``ValueError``
    instead of leaking a low-level ``TypeError`` such as ``int(None)``.
    """

    candidate = value
    if candidate is None or (isinstance(candidate, str) and not candidate.strip()):
        if strict:
            raise ValueError(f"{field_name} must be an integer; received an empty value")
        candidate = default

    if isinstance(candidate, bool):
        if strict:
            raise ValueError(f"{field_name} must be an integer, not a boolean")
        candidate = default

    try:
        integer = int(candidate)
    except (TypeError, ValueError, OverflowError) as exc:
        if strict:
            raise ValueError(f"{field_name} must be an integer; received {candidate!r}") from exc
        try:
            integer = int(default)
        except (TypeError, ValueError, OverflowError) as default_exc:
            raise ValueError(
                f"{field_name} has an invalid fallback integer: {default!r}"
            ) from default_exc

    if minimum is not None:
        integer = max(minimum, integer)
    if maximum is not None:
        integer = min(maximum, integer)
    return integer


def safe_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    field_name: str = "value",
    strict: bool = False,
) -> float:
    """Convert untrusted external data to a finite float safely."""

    candidate = value
    if candidate is None or (isinstance(candidate, str) and not candidate.strip()):
        if strict:
            raise ValueError(f"{field_name} must be numeric; received an empty value")
        candidate = default

    if isinstance(candidate, bool):
        if strict:
            raise ValueError(f"{field_name} must be numeric, not a boolean")
        candidate = default

    try:
        number = float(candidate)
    except (TypeError, ValueError, OverflowError) as exc:
        if strict:
            raise ValueError(f"{field_name} must be numeric; received {candidate!r}") from exc
        try:
            number = float(default)
        except (TypeError, ValueError, OverflowError) as default_exc:
            raise ValueError(
                f"{field_name} has an invalid fallback number: {default!r}"
            ) from default_exc

    if number != number or number in {float("inf"), float("-inf")}:
        if strict:
            raise ValueError(f"{field_name} must be a finite number")
        number = float(default)

    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number
