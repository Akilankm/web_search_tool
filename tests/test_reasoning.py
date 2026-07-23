import os
import sys
from types import ModuleType, SimpleNamespace

import pytest

from product_url_v2.config import ReasoningConfig
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import ProductInput
from product_url_v2.reasoning import ReasoningSettings, StructuredIdentityReasoner


_RESPONSE_CONTENT = (
    '{"facts":[{"field":"brand","value":"Pokemon","confidence":0.8,"evidence":"PKM"},'
    '{"field":"ean","value":"9999999999999","confidence":0.9,"evidence":"invented"}],'
    '"unknowns":["pack_configuration"],'
    '"negative_constraints":["do not assume display"],'
    '"hypotheses":[{"name":"ME04 single booster pack",'
    '"attributes":{"model":"ME04","pack_configuration":"SINGLE_PACK"},'
    '"negative_constraints":["display"],"probability":0.7,'
    '"rationale":"generic booster wording"}]}'
)


class FakeCompletions:
    def __init__(self) -> None:
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=_RESPONSE_CONTENT))]
        )


class FakeClient:
    def __init__(self) -> None:
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


def _settings(**overrides) -> ReasoningSettings:
    values = {
        "enabled": True,
        "required": True,
        "deployment": "fixture-deployment",
        "endpoint": "https://fixture.example",
        "api_version": "2024-10-21",
        "api_key": "fixture-key",
        "consumer_id": "fixture-consumer",
    }
    values.update(overrides)
    return ReasoningSettings(**values)


def test_reasoner_refines_hypotheses_but_rejects_invented_identifiers() -> None:
    product = ProductInput("P1", "PKM ME04 WACHSENDES CHAOS BOOSTER", "CH")
    deterministic = DeterministicProductInterpreter().interpret(product)
    client = FakeClient()
    result = StructuredIdentityReasoner(_settings(), client=client).refine(product, deterministic)

    assert result.strongest("model").value == "ME04"
    assert "9999999999999" not in result.values("ean")
    assert any(
        item.attributes.get("pack_configuration") == "SINGLE_PACK"
        for item in result.hypotheses
    )
    assert client.completions.last_kwargs["model"] == "fixture-deployment"


def test_pca_environment_values_take_precedence() -> None:
    values = {
        "PCA_LLM_API_KEY": "pca-key",
        "PCA_LLM_API_VERSION": "2024-10-21",
        "PCA_LLM_ENDPOINT": "https://pca.example",
        "PCA_LLM_DEPLOYMENT": "pca-deployment",
        "PCA_LLM_CONSUMER_ID": "pca-consumer",
        "LLM_API_KEY": "generic-key",
        "LLM_MODEL": "generic-model",
    }
    previous = {name: os.environ.get(name) for name in values}
    try:
        os.environ.update(values)
        settings = ReasoningSettings.from_runtime(
            ReasoningConfig(enabled=True, required=True)
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    assert settings.api_key == "pca-key"
    assert settings.api_version == "2024-10-21"
    assert settings.endpoint == "https://pca.example"
    assert settings.deployment == "pca-deployment"
    assert settings.consumer_id == "pca-consumer"
    assert settings.default_headers == {"X-NIQ-CIS-Consumer": "pca-consumer"}


def test_azure_client_uses_enterprise_contract() -> None:
    captured = {}

    class FakeAzureOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    openai_module = ModuleType("openai")
    openai_module.AzureOpenAI = FakeAzureOpenAI
    httpx_module = ModuleType("httpx")
    httpx_module.Timeout = lambda **kwargs: ("timeout", kwargs)

    previous_openai = sys.modules.get("openai")
    previous_httpx = sys.modules.get("httpx")
    try:
        sys.modules["openai"] = openai_module
        sys.modules["httpx"] = httpx_module
        product = ProductInput("P2", "PKM ME04 WACHSENDES CHAOS BOOSTER", "CH")
        deterministic = DeterministicProductInterpreter().interpret(product)
        StructuredIdentityReasoner(_settings()).refine(product, deterministic)
    finally:
        if previous_openai is None:
            sys.modules.pop("openai", None)
        else:
            sys.modules["openai"] = previous_openai
        if previous_httpx is None:
            sys.modules.pop("httpx", None)
        else:
            sys.modules["httpx"] = previous_httpx

    assert captured["api_key"] == "fixture-key"
    assert captured["api_version"] == "2024-10-21"
    assert captured["azure_endpoint"] == "https://fixture.example"
    assert captured["azure_deployment"] == "fixture-deployment"
    assert captured["default_headers"] == {
        "X-NIQ-CIS-Consumer": "fixture-consumer"
    }


def test_required_reasoning_rejects_incomplete_pca_configuration() -> None:
    settings = ReasoningSettings(enabled=True, required=True)
    with pytest.raises(RuntimeError, match="PCA_LLM_API_KEY"):
        settings.validate()
