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
    """Convert optional external data to an integer without leaking ``int(None)``.

    Environment variables, Streamlit session state, browser payloads and external
    API records are all untrusted numeric boundaries. In non-strict mode, null,
    blank or malformed values fall back to ``default``. In strict mode, a clear
    ``ValueError`` is raised instead of the low-level Python ``TypeError``.
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
        integer = int(default)

    if minimum is not None:
        integer = max(minimum, integer)
    if maximum is not None:
        integer = min(maximum, integer)
    return integer
