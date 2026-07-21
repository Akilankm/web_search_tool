from __future__ import annotations

import pytest

from src.product_evidence_harness.numeric_safety import safe_int


def test_safe_int_uses_default_for_null_blank_and_malformed_values() -> None:
    assert safe_int(None, 6) == 6
    assert safe_int("", 6) == 6
    assert safe_int("   ", 6) == 6
    assert safe_int("not-a-number", 6) == 6
    assert safe_int(True, 6) == 6


def test_safe_int_converts_and_clamps_external_values() -> None:
    assert safe_int("3", 1, minimum=1, maximum=5) == 3
    assert safe_int("99", 1, minimum=1, maximum=5) == 5
    assert safe_int("-10", 1, minimum=1, maximum=5) == 1


def test_safe_int_strict_mode_raises_clear_value_error() -> None:
    with pytest.raises(ValueError, match="demo_budget must be an integer"):
        safe_int(None, 3, field_name="demo_budget", strict=True)
    with pytest.raises(ValueError, match="demo_budget must be an integer"):
        safe_int("bad", 3, field_name="demo_budget", strict=True)
