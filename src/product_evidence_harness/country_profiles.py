from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROFILE_PATH_ENV = "PRODUCT_HARNESS_COUNTRY_PROFILES"
DEFAULT_PROFILE_FILE = Path(__file__).resolve().parent / "configs" / "country_profiles.json"


def _norm_country(code: str | None) -> str:
    return (code or "").strip().upper()


def _norm_lang(code: str | None) -> str:
    return (code or "").strip().lower()


def _norm_domain(domain: str | None) -> str:
    value = (domain or "").strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/", 1)[0]
    return value[4:] if value.startswith("www.") else value


@dataclass(frozen=True)
class LanguageProfile:
    """Language-market priority inside a country.

    This does not encode retailers. It only tells the harness which language
    market to search first for a country and which localized commerce/country
    terms to use while discovering retailers dynamically from web search.
    """

    language_code: str
    language_name: str
    priority: int
    distribution_weight: float
    country_terms: tuple[str, ...] = ()
    commerce_terms: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, fallback_priority: int) -> "LanguageProfile":
        code = _norm_lang(data.get("language_code") or data.get("code") or "en") or "en"
        return cls(
            language_code=code,
            language_name=str(data.get("language_name") or data.get("name") or code).strip() or code,
            priority=int(data.get("priority") or fallback_priority),
            distribution_weight=float(data.get("distribution_weight") or data.get("weight") or 0.0),
            country_terms=tuple(str(x).strip() for x in data.get("country_terms", []) if str(x).strip()),
            commerce_terms=tuple(str(x).strip() for x in data.get("commerce_terms", []) if str(x).strip()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "language_code": self.language_code,
            "language_name": self.language_name,
            "priority": self.priority,
            "distribution_weight": self.distribution_weight,
            "country_terms": list(self.country_terms),
            "commerce_terms": list(self.commerce_terms),
        }


@dataclass(frozen=True)
class CountryProfile:
    """Country-level search profile controlled only by country code.

    The profile contains geography hints and language-market priorities. It
    deliberately does not contain retailer allow-lists/deny-lists because
    retailer availability is dynamic and should be discovered from search.
    """

    country_code: str
    country_name: str = ""
    default_language: str = "en"
    language_profiles: tuple[LanguageProfile, ...] = field(default_factory=lambda: (
        LanguageProfile("en", "English", 1, 1.0, (), ("buy", "shop", "price", "product", "toy")),
    ))
    tlds: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, country_code: str, data: dict[str, Any]) -> "CountryProfile":
        # v3 preferred shape: languages is a list of objects.
        raw_languages = data.get("languages") or []
        language_profiles: list[LanguageProfile] = []
        if raw_languages and all(isinstance(x, dict) for x in raw_languages):
            for idx, item in enumerate(raw_languages, start=1):
                language_profiles.append(LanguageProfile.from_dict(item, fallback_priority=idx))
        else:
            # Backward compatibility with v2 shape: languages + buy_terms + country_names.
            buy_terms = data.get("buy_terms") or {}
            country_names = tuple(str(x).strip() for x in data.get("country_names", []) if str(x).strip())
            for idx, lang in enumerate(raw_languages or [data.get("default_language") or "en"], start=1):
                code = _norm_lang(lang) or "en"
                language_profiles.append(LanguageProfile(
                    language_code=code,
                    language_name=code,
                    priority=idx,
                    distribution_weight=1.0 / max(1, len(raw_languages or [code])),
                    country_terms=country_names,
                    commerce_terms=tuple(str(x).strip() for x in buy_terms.get(code, []) if str(x).strip()),
                ))
        if not language_profiles:
            language_profiles = [LanguageProfile("en", "English", 1, 1.0, (), ("buy", "shop", "price", "product", "toy"))]
        language_profiles = sorted(language_profiles, key=lambda lp: (lp.priority, -lp.distribution_weight, lp.language_code))
        default_language = _norm_lang(data.get("default_language") or language_profiles[0].language_code) or language_profiles[0].language_code
        return cls(
            country_code=_norm_country(country_code),
            country_name=str(data.get("country_name") or data.get("name") or country_code).strip(),
            default_language=default_language,
            language_profiles=tuple(language_profiles),
            tlds=tuple(str(x).strip().lower() for x in data.get("tlds", []) if str(x).strip()),
        )

    @cached_property
    def languages(self) -> tuple[str, ...]:
        return tuple(lp.language_code for lp in self.language_profiles)

    @cached_property
    def country_names(self) -> tuple[str, ...]:
        terms: list[str] = []
        if self.country_name:
            terms.append(self.country_name)
        for lp in self.language_profiles:
            terms.extend(lp.country_terms)
        return tuple(dict.fromkeys(t for t in terms if t))

    @cached_property
    def retailer_domains(self) -> tuple[str, ...]:
        """Compatibility property.

        Retailer domains are deliberately not maintained in country profiles.
        The harness discovers retailer candidates dynamically from SerpAPI.
        """
        return ()

    def language_profile(self, language_code: str | None) -> LanguageProfile:
        code = _norm_lang(language_code)
        for lp in self.language_profiles:
            if lp.language_code == code:
                return lp
        for lp in self.language_profiles:
            if lp.language_code == self.default_language:
                return lp
        return self.language_profiles[0]

    def language_profiles_for(self, requested_language: str | None = None) -> tuple[LanguageProfile, ...]:
        ordered: list[LanguageProfile] = []
        requested = _norm_lang(requested_language)
        if requested:
            match = next((lp for lp in self.language_profiles if lp.language_code == requested), None)
            if match:
                ordered.append(match)
        default = next((lp for lp in self.language_profiles if lp.language_code == self.default_language), None)
        if default and default not in ordered:
            ordered.append(default)
        for lp in self.language_profiles:
            if lp not in ordered:
                ordered.append(lp)
        if not any(lp.language_code == "en" for lp in ordered):
            ordered.append(LanguageProfile("en", "English", len(ordered) + 1, 0.0, (), ("buy", "shop", "price", "product", "toy")))
        return tuple(ordered)

    def languages_for(self, requested_language: str | None = None) -> tuple[str, ...]:
        return tuple(lp.language_code for lp in self.language_profiles_for(requested_language))

    def buy_terms_for(self, language_code: str | None = None, *, max_terms: int = 6) -> tuple[str, ...]:
        terms: list[str] = []
        primary = self.language_profile(language_code)
        terms.extend(primary.commerce_terms)
        for lp in self.language_profiles_for(language_code):
            terms.extend(lp.commerce_terms)
        out: list[str] = []
        seen: set[str] = set()
        for term in terms:
            clean = str(term).strip()
            key = clean.lower()
            if clean and key not in seen:
                seen.add(key)
                out.append(clean)
            if len(out) >= max_terms:
                break
        return tuple(out)

    def to_language_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "country_code": self.country_code,
                "country_name": self.country_name,
                "tlds": "|".join(self.tlds),
                **lp.to_dict(),
                "country_terms": "|".join(lp.country_terms),
                "commerce_terms": "|".join(lp.commerce_terms),
            }
            for lp in self.language_profiles
        ]


class CountryProfileRegistry:
    def __init__(self, profiles: dict[str, CountryProfile], default: CountryProfile) -> None:
        self._profiles = {_norm_country(k): v for k, v in profiles.items()}
        self._default = default

    @classmethod
    def load(cls, path: str | Path | None = None) -> "CountryProfileRegistry":
        resolved = Path(path or os.getenv(PROFILE_PATH_ENV) or DEFAULT_PROFILE_FILE)
        with resolved.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        countries = payload.get("countries", payload)
        default_data = countries.get("DEFAULT", {})
        default = CountryProfile.from_dict("DEFAULT", default_data)
        profiles = {
            _norm_country(code): CountryProfile.from_dict(code, data)
            for code, data in countries.items()
            if _norm_country(code) != "DEFAULT" and isinstance(data, dict)
        }
        return cls(profiles=profiles, default=default)

    def get(self, country_code: str | None) -> CountryProfile:
        code = _norm_country(country_code)
        profile = self._profiles.get(code)
        if profile:
            return profile
        tlds = (f".{code.lower()}",) if len(code) == 2 else self._default.tlds
        return CountryProfile(
            country_code=code or "DEFAULT",
            country_name=code or self._default.country_name,
            default_language=self._default.default_language,
            language_profiles=self._default.language_profiles,
            tlds=tlds,
        )

    def domain_matches_country(self, url_or_domain: str, country_code: str | None) -> bool:
        profile = self.get(country_code)
        parsed = urlparse(url_or_domain)
        domain = _norm_domain(parsed.netloc or url_or_domain)
        if not domain:
            return False
        if profile.tlds and any(domain.endswith(tld) for tld in profile.tlds):
            return True
        url_lower = (url_or_domain or "").lower()
        code = _norm_country(country_code).lower()
        return bool(code and (f"/{code}/" in url_lower or f"-{code}/" in url_lower or f"_{code}/" in url_lower))

    def country_hints(self, country_code: str | None, *, max_domain_hints: int = 4) -> tuple[str, ...]:
        profile = self.get(country_code)
        hints = [f"site:{tld}" for tld in profile.tlds]
        return tuple(dict.fromkeys(hints[:max_domain_hints]))

    def country_context_terms(self, country_code: str | None, language_code: str | None = None) -> tuple[str, ...]:
        profile = self.get(country_code)
        lp = profile.language_profile(language_code)
        terms: list[str] = []
        terms.extend(lp.country_terms)
        terms.extend(profile.country_names[:4])
        terms.extend(lp.commerce_terms[:5])
        return tuple(dict.fromkeys(t for t in terms if t))

    def language_profiles_for(self, country_code: str | None, requested_language: str | None = None) -> tuple[LanguageProfile, ...]:
        return self.get(country_code).language_profiles_for(requested_language)
