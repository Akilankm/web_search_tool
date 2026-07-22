from product_url_v2.interpretation import DeterministicProductInterpreter, build_search_context
from product_url_v2.models import ProductInput


def test_leitz_interpretation() -> None:
    result = DeterministicProductInterpreter().interpret(
        ProductInput("LEITZ-1", "LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK", "DE", language_code="de")
    )
    assert result.strongest("brand").value == "LEITZ"
    assert result.strongest("quantity").value == "100"
    assert result.strongest("product_form").value == "DOCUMENT_SLEEVE"
    assert len(result.hypotheses) == 1


def test_generic_booster_preserves_competing_commercial_forms() -> None:
    result = DeterministicProductInterpreter().interpret(
        ProductInput("PKM-1", "PKM ME04 WACHSENDES CHAOS BOOSTER", "CH", language_code="de")
    )
    assert result.strongest("model").value == "ME04"
    assert result.strongest("brand").confidence < 0.60
    assert result.unresolved_discriminators[0] == "brand" or "pack_configuration" in result.unresolved_discriminators
    assert {item.attributes["pack_configuration"] for item in result.hypotheses} == {"SINGLE_PACK", "BUNDLE", "DISPLAY"}
    context = build_search_context(ProductInput("PKM-1", "PKM ME04 WACHSENDES CHAOS BOOSTER", "CH"), result)
    assert "ME04" in context["exact_anchors"]
    assert "pack_configuration" in context["unresolved_discriminators"]
