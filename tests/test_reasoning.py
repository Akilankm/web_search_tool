from types import SimpleNamespace

from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import ProductInput
from product_url_v2.reasoning import ReasoningSettings, StructuredIdentityReasoner


class FakeCompletions:
    def create(self, **kwargs):
        content = '{"facts":[{"field":"brand","value":"Pokemon","confidence":0.8,"evidence":"PKM"},{"field":"ean","value":"9999999999999","confidence":0.9,"evidence":"invented"}],"unknowns":["pack_configuration"],"negative_constraints":["do not assume display"],"hypotheses":[{"name":"ME04 single booster pack","attributes":{"model":"ME04","pack_configuration":"SINGLE_PACK"},"negative_constraints":["display"],"probability":0.7,"rationale":"generic booster wording"}]}'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


def test_reasoner_refines_hypotheses_but_rejects_invented_identifiers() -> None:
    product = ProductInput("P1", "PKM ME04 WACHSENDES CHAOS BOOSTER", "CH")
    deterministic = DeterministicProductInterpreter().interpret(product)
    result = StructuredIdentityReasoner(
        ReasoningSettings(enabled=True, required=True, model="fixture", api_key="fixture"),
        client=FakeClient(),
    ).refine(product, deterministic)
    assert result.strongest("model").value == "ME04"
    assert "9999999999999" not in result.values("ean")
    assert any(item.attributes.get("pack_configuration") == "SINGLE_PACK" for item in result.hypotheses)
