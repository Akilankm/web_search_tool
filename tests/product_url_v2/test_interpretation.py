from __future__ import annotations

from product_url_v2 import (
    DeterministicProductInterpreter,
    IdentityReasoningContract,
    ProductForm,
    ProductInput,
    SignalField,
    build_search_context,
    normalize_product_text,
)


def _values(result, field: SignalField) -> set[str]:
    return {item.normalized_value for item in result.signals_for(field)}


def test_leitz_document_sleeve_extracts_brand_form_and_quantity() -> None:
    result = DeterministicProductInterpreter().interpret(
        ProductInput(
            row_id="LEITZ-1",
            main_text="LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK",
            country_code="DE",
            language_code="de",
        )
    )

    brand = result.strongest_signal(SignalField.BRAND)
    assert brand is not None
    assert brand.normalized_value == "LEITZ"
    assert brand.confidence >= 0.70
    assert _values(result, SignalField.PRODUCT_FORM) == {
        ProductForm.DOCUMENT_SLEEVE.value
    }
    assert _values(result, SignalField.QUANTITY) == {"100"}
    assert len(result.hypotheses) == 1
    assert dict(result.hypotheses[0].attributes)["PRODUCT_FORM"] == (
        ProductForm.DOCUMENT_SLEEVE.value
    )
    assert not any(
        item.key == "booster_pack_configuration" for item in result.uncertainties
    )


def test_generic_pokemon_booster_preserves_pack_configuration_hypotheses() -> None:
    result = DeterministicProductInterpreter().interpret(
        ProductInput(
            row_id="PKM-1",
            main_text="PKM ME04 WACHSENDES CHAOS BOOSTER",
            country_code="CH",
            language_code="de",
        )
    )

    assert "ME04" in _values(result, SignalField.MODEL)
    assert _values(result, SignalField.PRODUCT_FORM) == {ProductForm.BOOSTER.value}
    prefix = result.strongest_signal(SignalField.BRAND)
    assert prefix is not None
    assert prefix.normalized_value == "PKM"
    assert prefix.confidence < 0.60
    assert any(item.key == "brand_or_prefix" for item in result.uncertainties)

    hypotheses = {item.hypothesis_id: item for item in result.hypotheses}
    assert set(hypotheses) == {"H1", "H2", "H3"}
    assert dict(hypotheses["H1"].attributes)["PACK_CONFIGURATION"] == (
        ProductForm.BOOSTER_PACK.value
    )
    assert dict(hypotheses["H2"].attributes)["PACK_CONFIGURATION"] == (
        ProductForm.BOOSTER_BUNDLE.value
    )
    assert dict(hypotheses["H3"].attributes)["PACK_CONFIGURATION"] == (
        ProductForm.BOOSTER_DISPLAY.value
    )
    assert "not booster bundle" in hypotheses["H1"].negative_constraints
    assert "not booster display" in hypotheses["H1"].negative_constraints
    assert "ME04" in result.exact_anchors

    context = build_search_context(result)
    assert context.unresolved_discriminators
    assert "single booster pack" in context.unresolved_discriminators[0].lower()
    assert "ME04" in context.exact_anchors
    assert not any(field == "BRAND" for field, _ in context.known_facts)


def test_provided_gtin_is_a_full_confidence_exact_anchor() -> None:
    result = DeterministicProductInterpreter().interpret(
        ProductInput(
            row_id="PKM-EAN",
            main_text="PKM ME04 WACHSENDES CHAOS BOOSTER",
            country_code="CH",
            ean="196214141070",
            language_code="de",
        )
    )

    gtin = result.strongest_signal(SignalField.EAN)
    assert gtin is not None
    assert gtin.normalized_value == "196214141070"
    assert gtin.confidence == 1.0
    assert result.exact_anchors[:2] == ("196214141070", "ME04")


def test_explicit_booster_bundle_does_not_create_single_pack_alternatives() -> None:
    result = DeterministicProductInterpreter().interpret(
        ProductInput(
            row_id="PKM-BUNDLE",
            main_text="POKEMON ME04 WACHSENDES CHAOS BOOSTER BUNDLE DE",
            country_code="CH",
            language_code="de",
        )
    )

    assert result.strongest_signal(SignalField.PRODUCT_FORM).normalized_value == (
        ProductForm.BOOSTER_BUNDLE.value
    )
    assert len(result.hypotheses) == 1
    assert not any(
        item.key == "booster_pack_configuration" for item in result.uncertainties
    )


def test_reasoning_contract_contains_only_grounded_input_and_explicit_unknowns() -> None:
    result = DeterministicProductInterpreter().interpret(
        ProductInput(
            row_id="PKM-REASONING",
            main_text="PKM ME04 WACHSENDES CHAOS BOOSTER",
            country_code="CH",
            language_code="de",
        )
    )

    payload = IdentityReasoningContract.request_payload(result)

    assert payload["product_input"]["main_text"] == result.product.main_text
    assert payload["product_input"]["ean"] is None
    assert payload["deterministic_signals"]
    assert len(payload["current_hypotheses"]) == 3
    assert payload["current_uncertainties"]
    assert any("Do not invent EAN" in rule for rule in payload["rules"])
    assert set(payload["output_schema"]) == {
        "signals",
        "hypotheses",
        "unresolved_discriminators",
        "recommended_search_anchors",
        "negative_search_terms",
    }


def test_normalization_preserves_unicode_semantics_and_removes_spacing_noise() -> None:
    assert normalize_product_text(
        "  LEITZ\u00a0RECYCLE   PROSPEKTHÜLLE  100   STÜCK "
    ) == "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK"
