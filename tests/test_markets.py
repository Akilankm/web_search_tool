"""Tests for the de-hardcoded market profile registry (markets.py)."""

from __future__ import annotations

import re

import pytest

from serp_hybrid_url_finder.markets import (
    GENERIC_PROFILE,
    MarketProfile,
    MarketProfileRegistry,
    resolve_market_profile,
)


def test_resolve_unknown_country_falls_back_to_generic():
    assert resolve_market_profile(None) is GENERIC_PROFILE
    assert resolve_market_profile("") is GENERIC_PROFILE
    # An unregistered country resolves to the generic multilingual default.
    assert resolve_market_profile("ZZ") is GENERIC_PROFILE


def test_quantity_regex_captures_count_and_unit():
    pattern = re.compile(GENERIC_PROFILE.build_quantity_regex(), re.IGNORECASE)
    match = pattern.search("Balení 18 KS")
    assert match is not None
    # Group order is the contract consumed by the identity verifier:
    # group(1) = count, group(2) = unit.
    assert match.group(1) == "18"
    assert match.group(2).lower() == "ks"


def test_price_regex_detects_prices_in_both_orders():
    pattern = re.compile(GENERIC_PROFILE.build_price_regex(), re.IGNORECASE)
    assert pattern.search("199 Kč")          # number then currency
    assert pattern.search("$5.99")           # currency then number
    assert pattern.search("1 299,00 EUR")    # locale-formatted number then currency
    assert not pattern.search("just some words")


def test_merged_with_extends_without_losing_base_terms():
    override = MarketProfile(
        profile_id="co",
        country_codes=("CO",),
        quantity_units=("botellas",),
        currency_terms=("cop",),
        title_stopwords=frozenset({"extra"}),
    )
    merged = GENERIC_PROFILE.merged_with(override)

    assert merged.profile_id == "co"               # override identity wins
    assert "botellas" in merged.quantity_units     # override term added
    assert "ks" in merged.quantity_units           # base term preserved
    assert "extra" in merged.title_stopwords       # override stopword unioned
    assert "the" in merged.title_stopwords         # base stopword preserved


def test_registry_register_resolves_country_override():
    registry = MarketProfileRegistry()
    override = MarketProfile(
        profile_id="co",
        country_codes=("CO",),
        quantity_units=("botellas",),
        currency_terms=("cop",),
    )
    registry.register(override)

    resolved = registry.resolve("co")              # case-insensitive lookup
    assert resolved.profile_id == "co"
    assert "botellas" in resolved.quantity_units
    assert "ks" in resolved.quantity_units         # inherited from generic default
    # Unregistered country still falls back to the generic default.
    assert registry.resolve("US") is GENERIC_PROFILE
