from __future__ import annotations

from types import SimpleNamespace

from product_evidence_harness import (
    FeatureCriticality,
    FeatureDefinition,
    FeatureEvidence,
    FeatureEvidenceStatus,
    FeatureSchema,
    ProductQuery,
    ScrapeResult,
)
from product_evidence_harness.llm.feature_reasoner import LLMFeatureReasoner


class FakeLLMService:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0
        self.prompts: list[str] = []

    def predict(self, prompt, *args, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.content)


class FailingLLMService:
    def __init__(self) -> None:
        self.calls = 0

    def predict(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("provider unavailable")


def _schema() -> FeatureSchema:
    return FeatureSchema(
        schema_id="toy",
        features=(
            FeatureDefinition(
                feature_id="MATERIAL",
                feature_name="Material",
                criticality=FeatureCriticality.REQUIRED,
                allowed_values=("ABS plastic", "Wood"),
            ),
        ),
    )


def _scrape() -> ScrapeResult:
    return ScrapeResult(
        url="https://shop.example/product/1",
        final_url="https://shop.example/product/1",
        scraped=True,
        success=True,
        reachable=True,
        is_scrapable=True,
        status_code=200,
        looks_like_product_page=True,
        title="Acme Rocket",
        description="The product body is made from ABS plastic and includes 18 pieces.",
    )


def _missing() -> tuple[FeatureEvidence, ...]:
    return (
        FeatureEvidence(
            feature_id="MATERIAL",
            feature_name="Material",
            source_url="https://shop.example/product/1",
            status=FeatureEvidenceStatus.NOT_FOUND,
        ),
    )


def test_reasoner_accepts_only_quote_grounded_allowed_value() -> None:
    service = FakeLLMService(
        '{"features":[{"feature_id":"MATERIAL","value":"ABS plastic",'
        '"evidence_quote":"made from ABS plastic","confidence":0.93}]}'
    )
    reasoner = LLMFeatureReasoner(service=service, max_calls=1)

    evidence = reasoner.evaluate(
        product=ProductQuery(main_text="Acme Rocket", country_code="US"),
        schema=_schema(),
        scrape=_scrape(),
        deterministic_evidence=_missing(),
    )

    assert service.calls == 1
    assert "https://shop.example/product/1" in service.prompts[0]
    assert len(evidence) == 1
    assert evidence[0].value == "ABS plastic"
    assert evidence[0].status == FeatureEvidenceStatus.LLM_FOUND
    assert evidence[0].confidence == 0.75


def test_reasoner_rejects_hallucinated_quote() -> None:
    service = FakeLLMService(
        '{"features":[{"feature_id":"MATERIAL","value":"Wood",'
        '"evidence_quote":"constructed from premium wood","confidence":0.99}]}'
    )
    reasoner = LLMFeatureReasoner(service=service, max_calls=1)

    evidence = reasoner.evaluate(
        product=ProductQuery(main_text="Acme Rocket", country_code="US"),
        schema=_schema(),
        scrape=_scrape(),
        deterministic_evidence=_missing(),
    )

    assert service.calls == 1
    assert evidence == ()


def test_reasoner_obeys_call_budget() -> None:
    service = FakeLLMService('{"features":[]}')
    reasoner = LLMFeatureReasoner(service=service, max_calls=1)

    for _ in range(2):
        reasoner.evaluate(
            product=ProductQuery(main_text="Acme Rocket", country_code="US"),
            schema=_schema(),
            scrape=_scrape(),
            deterministic_evidence=_missing(),
        )

    assert service.calls == 1


def test_reasoner_provider_failure_returns_no_evidence() -> None:
    service = FailingLLMService()
    reasoner = LLMFeatureReasoner(service=service, max_calls=1)

    evidence = reasoner.evaluate(
        product=ProductQuery(main_text="Acme Rocket", country_code="US"),
        schema=_schema(),
        scrape=_scrape(),
        deterministic_evidence=_missing(),
    )

    assert service.calls == 1
    assert evidence == ()
