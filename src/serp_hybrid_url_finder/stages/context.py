from __future__ import annotations

from dataclasses import dataclass

from serp_hybrid_url_finder.models import CountryContext, ProductQuery


@dataclass(frozen=True)
class CountryContextResolver:
    """Builds country context from the required country_code.

    Uses pycountry when available. If it is not installed, the pipeline still
    runs with the raw country code and SerpAPI ``gl``.
    """

    def resolve(self, product: ProductQuery) -> CountryContext:
        code = product.country_code.strip().upper()
        country_name = None
        try:  # optional dependency; never required for the pipeline to run
            import pycountry  # type: ignore

            country = pycountry.countries.get(alpha_2=code)
            country_name = getattr(country, "name", None) if country else None
        except Exception:
            country_name = None
        market_name = country_name or code
        return CountryContext(
            country_code=code,
            serp_gl=code.lower(),
            country_name=country_name,
            market_constraint=f"Product page must be relevant to the {market_name} market.",
        )
