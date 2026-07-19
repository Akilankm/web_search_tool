from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from src.product_evidence_harness.adaptive_search import (
    BudgetAwareSearchPlanner,
    SearchAction,
    SearchEngine,
)
from src.product_evidence_harness.contracts import ProductQuery


_PATCHED = False


def _identity(product: ProductQuery) -> str:
    parts: list[str] = []
    if product.ean:
        parts.append(f'"{product.ean}"')
    if product.main_text:
        parts.append(f'"{" ".join(product.main_text.split())}"')
    return " ".join(parts)


def _native_retailer_engine(
    product: ProductQuery,
    available_engines: Sequence[str],
) -> str | None:
    requested = (product.retailer_name or "").lower().replace(" ", "").replace("_", "")
    for engine in (
        SearchEngine.AMAZON.value,
        SearchEngine.EBAY.value,
        SearchEngine.WALMART.value,
        SearchEngine.HOME_DEPOT.value,
    ):
        if engine.replace("_", "") in requested and engine in available_engines:
            return engine
    return None


def _first_available(
    available_engines: Sequence[str],
    preferred: Sequence[str],
    fallback: str,
) -> str:
    return next((engine for engine in preferred if engine in available_engines), fallback)


def _credit_action(
    *,
    product: ProductQuery,
    credit_number: int,
    available_engines: Sequence[str],
    original: SearchAction,
) -> SearchAction:
    identity = _identity(product)
    available = tuple(available_engines)
    fallback_engine = original.engine or (available[0] if available else SearchEngine.GOOGLE.value)

    if credit_number <= 1:
        engine = _first_available(
            available,
            (SearchEngine.GOOGLE.value, SearchEngine.GOOGLE_AI_MODE.value),
            fallback_engine,
        )
        return replace(
            original,
            engine=engine,
            purpose="official_manufacturer_product_truth",
            query=(
                f"{identity} official manufacturer brand product page "
                f"{product.country_code} -search -category -collection"
            ).strip(),
            scope="country",
            country_code=product.country_code,
            language_code=product.language_code or original.language_code or "en",
            page_token="",
            image_url="",
            expected_signals=(
                "SOURCE_TIER:LOCAL_MANUFACTURER",
                "OFFICIAL_MANUFACTURER_PRODUCT_PAGE",
                "DIRECT_EXACT_PRODUCT_URL",
            ),
            reason=(
                "Credit 1 is reserved for the official manufacturer/brand product page. "
                "Manufacturer product truth is evaluated before retailer preference."
            ),
            planner_source=f"manufacturer_primary:{original.planner_source}",
        )

    if credit_number == 2:
        native = _native_retailer_engine(product, available)
        if product.retailer_name:
            engine = native or _first_available(
                available,
                (
                    SearchEngine.GOOGLE.value,
                    SearchEngine.GOOGLE_SHOPPING.value,
                    SearchEngine.GOOGLE_AI_MODE.value,
                ),
                fallback_engine,
            )
            query = (
                f'{identity} "{product.retailer_name}" direct product page '
                f"{product.country_code} -search -category -collection"
            ).strip()
            tier = "REQUESTED_RETAILER_LOCAL"
            purpose = "requested_retailer_after_manufacturer"
        else:
            engine = _first_available(
                available,
                (
                    SearchEngine.GOOGLE_SHOPPING.value,
                    SearchEngine.GOOGLE.value,
                    SearchEngine.GOOGLE_AI_MODE.value,
                ),
                fallback_engine,
            )
            query = (
                f"{identity} retailer direct product page {product.country_code} "
                "-search -category -collection"
            ).strip()
            tier = "MAJOR_COUNTRY_RETAILER"
            purpose = "country_retailer_after_manufacturer"
        return replace(
            original,
            engine=engine,
            purpose=purpose,
            query=query,
            scope="country",
            country_code=product.country_code,
            language_code=product.language_code or original.language_code or "en",
            page_token="",
            image_url="",
            expected_signals=(
                f"SOURCE_TIER:{tier}",
                "DIRECT_EXACT_PRODUCT_URL",
                "RETAILER_REFERENCE_URL",
            ),
            reason=(
                "Credit 2 preserves the requested-country retailer route after the "
                "manufacturer product-truth opportunity has been evaluated."
            ),
            planner_source=f"manufacturer_primary:{original.planner_source}",
        )

    engine = _first_available(
        available,
        (
            SearchEngine.GOOGLE_AI_MODE.value,
            SearchEngine.GOOGLE.value,
            SearchEngine.GOOGLE_SHOPPING.value,
        ),
        fallback_engine,
    )
    return replace(
        original,
        engine=engine,
        purpose="global_manufacturer_or_retailer_fallback",
        query=(
            f"{identity} official manufacturer or retailer exact product page "
            "-search -category -collection"
        ).strip(),
        scope="global",
        country_code=product.country_code,
        language_code=product.language_code or original.language_code or "en",
        page_token="",
        image_url="",
        expected_signals=(
            "SOURCE_TIER:GLOBAL_MANUFACTURER",
            "DIRECT_EXACT_PRODUCT_URL",
            "GLOBAL_PRODUCT_FALLBACK",
        ),
        reason=(
            "Credit 3 is the global exact-product fallback after manufacturer and "
            "requested-country retailer routes."
        ),
        planner_source=f"manufacturer_primary:{original.planner_source}",
    )


def apply_manufacturer_search_planner_hardening() -> None:
    """Install the final credit-to-query contract after belief routing patches."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    current_choose = BudgetAwareSearchPlanner.choose_action
    current_fallback = BudgetAwareSearchPlanner.deterministic_fallback

    def choose(self, *args, **kwargs):
        product = kwargs["product"]
        credit = int(kwargs.get("credit_number") or 1)
        handles = kwargs.get("handles") or ()
        original = current_choose(self, *args, **kwargs)
        available = self._available_engines(product, handles)
        return _credit_action(
            product=product,
            credit_number=credit,
            available_engines=available,
            original=original,
        )

    def fallback(self, *args, **kwargs):
        product = kwargs["product"]
        credit = int(kwargs.get("credit_number") or 1)
        available = tuple(kwargs.get("available_engines") or ())
        original = current_fallback(self, *args, **kwargs)
        return _credit_action(
            product=product,
            credit_number=credit,
            available_engines=available,
            original=original,
        )

    BudgetAwareSearchPlanner.choose_action = choose
    BudgetAwareSearchPlanner.deterministic_fallback = fallback
