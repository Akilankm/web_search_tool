"""Country-to-language, currency, and market profile mapping.

This module provides intelligent language/currency/market lookups by country code.
Supports regional variants (e.g., Switzerland has German, French, Italian).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).parent / "data"
_MAPPING_FILE = _DATA_DIR / "country_language_mapping.json"


@dataclass(frozen=True)
class CountryLanguageProfile:
    """Language and market profile for a country."""

    country_code: str
    country_name: str
    primary_language: str
    alternative_languages: tuple[str, ...] = ()
    market_profile_id: str = ""
    currency: str = ""
    region_language_mapping: dict[str, str] = None

    def get_language_for_region(self, region: Optional[str]) -> str:
        """Get language code, considering regional override.
        
        Args:
            region: Optional region name (e.g., "Romandy" for Switzerland).
                    If None or not found, returns primary_language.
        
        Returns:
            Language code (e.g., "de", "fr").
        """
        if not region or not self.region_language_mapping:
            return self.primary_language
        
        region_lower = region.lower()
        for region_key, lang_code in self.region_language_mapping.items():
            if region_key.lower() == region_lower:
                return lang_code
        
        return self.primary_language


class CountryLanguageRegistry:
    """Lazy-loaded registry for country-language mappings."""

    def __init__(self):
        self._cache: dict[str, CountryLanguageProfile] = {}
        self._mapping_data: Optional[dict] = None

    def _load_mapping(self) -> dict:
        """Load the country-language mapping JSON lazily."""
        if self._mapping_data is None:
            if not _MAPPING_FILE.exists():
                raise FileNotFoundError(
                    f"Country-language mapping file not found: {_MAPPING_FILE}"
                )
            with open(_MAPPING_FILE, "r", encoding="utf-8") as f:
                self._mapping_data = json.load(f)
        return self._mapping_data

    def get_profile(self, country_code: str) -> CountryLanguageProfile:
        """Get language profile for a country code.
        
        Args:
            country_code: ISO 3166-1 alpha-2 code (e.g., "CH", "US").
        
        Returns:
            CountryLanguageProfile with language, currency, market info.
        
        Raises:
            KeyError if country code not found in mapping.
        """
        country_code = country_code.upper()
        
        if country_code in self._cache:
            return self._cache[country_code]
        
        mapping = self._load_mapping()
        if country_code not in mapping:
            raise KeyError(
                f"Country code '{country_code}' not found in mapping. "
                f"Add it to {_MAPPING_FILE}"
            )
        
        data = mapping[country_code]
        profile = CountryLanguageProfile(
            country_code=country_code,
            country_name=data.get("country_name", ""),
            primary_language=data["primary_language"],
            alternative_languages=tuple(data.get("alternative_languages", [])),
            market_profile_id=data.get("market_profile_id", ""),
            currency=data.get("currency", ""),
            region_language_mapping=data.get("region_language_mapping", {}),
        )
        
        self._cache[country_code] = profile
        return profile

    def get_language(
        self,
        country_code: str,
        region: Optional[str] = None,
    ) -> str:
        """Get language code for a country (with optional regional override).
        
        Args:
            country_code: ISO 3166-1 alpha-2 code (e.g., "CH").
            region: Optional region name for multi-language countries
                    (e.g., "Romandy" for French-speaking Switzerland).
        
        Returns:
            Language code (e.g., "de", "fr", "en").
        
        Raises:
            KeyError if country code not found.
        """
        profile = self.get_profile(country_code)
        return profile.get_language_for_region(region)

    def get_currency(self, country_code: str) -> str:
        """Get currency code for a country.
        
        Args:
            country_code: ISO 3166-1 alpha-2 code.
        
        Returns:
            Currency code (e.g., "CHF", "EUR", "USD").
        
        Raises:
            KeyError if country code not found.
        """
        profile = self.get_profile(country_code)
        return profile.currency

    def get_market_profile_id(self, country_code: str) -> str:
        """Get market profile ID for a country.
        
        Args:
            country_code: ISO 3166-1 alpha-2 code.
        
        Returns:
            Market profile ID (e.g., "ch", "co", "us").
        
        Raises:
            KeyError if country code not found.
        """
        profile = self.get_profile(country_code)
        return profile.market_profile_id


# Global registry instance
_REGISTRY: Optional[CountryLanguageRegistry] = None


def get_registry() -> CountryLanguageRegistry:
    """Get the global country-language registry (lazy-initialized)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CountryLanguageRegistry()
    return _REGISTRY


def resolve_language(
    country_code: str,
    region: Optional[str] = None,
) -> str:
    """Resolve language code from country code (and optional region).
    
    Convenience function that uses the global registry.
    
    Args:
        country_code: ISO 3166-1 alpha-2 code (e.g., "CH").
        region: Optional region name for multi-language countries.
    
    Returns:
        Language code (e.g., "de", "en").
    
    Raises:
        KeyError if country code not found.
    """
    return get_registry().get_language(country_code, region)


def resolve_currency(country_code: str) -> str:
    """Resolve currency code from country code.
    
    Convenience function that uses the global registry.
    
    Args:
        country_code: ISO 3166-1 alpha-2 code.
    
    Returns:
        Currency code (e.g., "CHF", "EUR").
    
    Raises:
        KeyError if country code not found.
    """
    return get_registry().get_currency(country_code)


def resolve_market_profile_id(country_code: str) -> str:
    """Resolve market profile ID from country code.
    
    Convenience function that uses the global registry.
    
    Args:
        country_code: ISO 3166-1 alpha-2 code.
    
    Returns:
        Market profile ID (e.g., "ch", "co").
    
    Raises:
        KeyError if country code not found.
    """
    return get_registry().get_market_profile_id(country_code)
