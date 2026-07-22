from __future__ import annotations

from product_url_v2 import (
    DeterministicProductInterpreter,
    InformationGainSearchPlanner,
    ProductInput,
    SearchAction,
    SearchEngine,
    SearchPurpose,
    SearchScope,
)


def _product() -> ProductInput:
    return ProductInput(
        row_id="REQUEST-SEMANTICS",
        main_text="PKM ME04 WACHSENDES CHAOS BOOSTER",
        country_code="CH",
        language_code="de",
    )


def test_immersive_signature_is_defined_by_billable_page_token() -> None:
    country = SearchAction(
        credit_number=2,
        engine=SearchEngine.GOOGLE_IMMERSIVE_PRODUCT,
        purpose=SearchPurpose.RESOLVE_UNCERTAINTY,
        scope=SearchScope.COUNTRY,
        page_token="TOKEN-1",
        country_code="CH",
    )
    global_recovery = SearchAction(
        credit_number=3,
        engine=SearchEngine.GOOGLE_IMMERSIVE_PRODUCT,
        purpose=SearchPurpose.MANDATORY_URL_RECOVERY,
        scope=SearchScope.GLOBAL,
        page_token="TOKEN-1",
    )

    assert country.signature == global_recovery.signature


def test_negative_constraints_exclude_actual_sibling_product_forms() -> None:
    product = _product()
    interpretation = DeterministicProductInterpreter().interpret(product)
    action = InformationGainSearchPlanner().choose(
        product=product,
        interpretation=interpretation,
        credit_number=2,
        observations=(),
        handles=(),
        used_signatures=set(),
    )

    assert '-"booster bundle"' in action.query
    assert '-"booster display"' in action.query
    assert '-"not booster bundle"' not in action.query
    assert '-"not booster display"' not in action.query
