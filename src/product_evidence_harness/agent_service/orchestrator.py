from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable

from src.product_evidence_harness.browser_client import BrowserEvidenceClient, BrowserServiceError
from src.product_evidence_harness.browser_contracts import BrowserEvidenceRequest, EvidenceIntent, ProductIdentityPayload
from src.product_evidence_harness.config import HarnessConfig, SerpAPIConfig
from src.product_evidence_harness.contracts import ProductQuery, ScrapeResult
from src.product_evidence_harness.feature_evidence import EvidenceSetSelector, FeatureAwareEvidenceExtractor
from src.product_evidence_harness.feature_schema import FeatureEvidence, FeatureSchema, URLFeatureAssessment
from src.product_evidence_harness.identity_verifier import ProductIdentityVerifier
from src.product_evidence_harness.llm.feature_reasoner import LLMFeatureReasoner
from src.product_evidence_harness.llm.vision_reasoner import MultimodalFeatureReasoner
from src.product_evidence_harness.one_credit_pipeline import FeatureAwareHarnessResult, OneCreditProductEvidenceHarness
from src.product_evidence_harness.schema_io import load_feature_schema


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    private_feature_root: Path = Path("/data/private")
    artifact_root: Path = Path("/data/artifacts")
    browser_enabled: bool = True
    browser_candidate_limit: int = 3
    require_multimodal_for_ready: bool = False
    enable_vision_reasoning: bool = True

    @classmethod
    def from_env(cls) -> "AgentRuntimeConfig":
        enabled = {"1", "true", "yes", "on"}
        return cls(
            private_feature_root=Path(os.getenv("PRIVATE_FEATURE_ROOT", "/data/private")),
            artifact_root=Path(os.getenv("ARTIFACT_ROOT", "/data/artifacts")),
            browser_enabled=os.getenv("PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE", "true").lower() in enabled,
            browser_candidate_limit=max(1, int(os.getenv("PRODUCT_HARNESS_BROWSER_CANDIDATE_LIMIT", "3"))),
            require_multimodal_for_ready=os.getenv("PRODUCT_HARNESS_REQUIRE_MULTIMODAL_FOR_READY", "false").lower() in enabled,
            enable_vision_reasoning=os.getenv("PRODUCT_HARNESS_ENABLE_VISION_REASONING", "true").lower() in enabled,
        )


class FeatureSetRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, feature_set: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", feature_set.strip())
        if not safe or safe in {".", ".."}:
            raise ValueError("feature_set is invalid")
        for candidate in (self.root / safe, self.root / f"{safe}.json"):
            resolved = candidate.resolve()
            if self.root in resolved.parents and resolved.is_file():
                return resolved
        raise FileNotFoundError(f"Private feature set not found: {feature_set}")


class ProductEvidenceOrchestrator:
    """Coordinates one-credit discovery, browser evidence, and multimodal reasoning."""

    def __init__(
        self,
        config: AgentRuntimeConfig | None = None,
        browser_client: BrowserEvidenceClient | None = None,
    ) -> None:
        self.config = config or AgentRuntimeConfig.from_env()
        self.config.artifact_root.mkdir(parents=True, exist_ok=True)
        self.feature_registry = FeatureSetRegistry(self.config.private_feature_root)
        self.browser_client = browser_client or (BrowserEvidenceClient() if self.config.browser_enabled else None)

    def health(self) -> dict[str, Any]:
        browser: dict[str, Any] = {"status": "disabled"}
        if self.browser_client is not None:
            try:
                browser = self.browser_client.health()
            except Exception as exc:
                browser = {"status": "unavailable", "error_type": type(exc).__name__}
        return {
            "status": "healthy" if browser.get("status") in {"healthy", "disabled"} else "degraded",
            "browser_service": browser,
            "private_feature_root_exists": self.config.private_feature_root.exists(),
            "artifact_root": str(self.config.artifact_root),
        }

    def run(self, payload: dict[str, Any], *, progress: Callable[[str, str], None] | None = None) -> dict[str, Any]:
        emit = progress or (lambda *_args: None)
        product_payload = dict(payload.get("product") or payload)
        feature_set = str(payload.get("feature_set") or product_payload.pop("feature_set", "")).strip()
        if not feature_set:
            raise ValueError("feature_set is required; the private feature file is resolved inside the agent container")

        emit("VALIDATING_INPUT", "Loading product input and private feature set")
        product = ProductQuery(**product_payload)
        feature_path = self.feature_registry.resolve(feature_set)
        schema = load_feature_schema(feature_path)

        emit("SEARCHING", "Running one-credit identity-only candidate discovery")
        llm_reasoner = None
        if os.getenv("PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING", "false").lower() in {"1", "true", "yes", "on"}:
            llm_reasoner = LLMFeatureReasoner.from_env(
                max_calls=int(os.getenv("PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT", "2"))
            )
        harness = OneCreditProductEvidenceHarness(
            serp_config=SerpAPIConfig.from_env(
                country_code=product.country_code,
                language_code=product.language_code or "en",
            ),
            config=HarnessConfig.from_env(),
            feature_reasoner=llm_reasoner,
        )
        base = harness.run(product, feature_schema=schema, return_trace=True)
        if not isinstance(base, FeatureAwareHarnessResult):
            raise RuntimeError("Expected feature-aware trace result")

        browser_bundles = []
        browser_assessments: list[URLFeatureAssessment] = []
        if self.browser_client is not None and self._browser_needed(base):
            emit("REQUESTING_BROWSER_EVIDENCE", "Acquiring rendered and visual evidence")
            for index, url in enumerate(self._browser_urls(base), start=1):
                request = BrowserEvidenceRequest(
                    job_id=product.row_id,
                    candidate_id=f"CAND-{index:03d}",
                    url=url,
                    product_identity=ProductIdentityPayload(
                        row_id=product.row_id,
                        main_text=product.main_text,
                        country_code=product.country_code,
                        retailer_name=product.retailer_name,
                        ean=product.ean,
                        language_code=product.language_code,
                    ),
                    intent=EvidenceIntent(
                        verify_rendered_product=True,
                        expand_product_sections=True,
                        collect_gallery=True,
                        download_images=True,
                        capture_screenshot_fallbacks=True,
                        maximum_images=10,
                        maximum_screenshots=8,
                        maximum_actions=30,
                        requested_evidence_categories=(
                            "product_gallery", "package_front_back", "specification_sections",
                            "safety_and_warning_sections", "dimension_diagrams",
                        ),
                    ),
                )
                try:
                    bundle = self.browser_client.acquire(request)
                except BrowserServiceError:
                    continue
                browser_bundles.append(bundle)
                assessment = self._assessment_from_browser(product, schema, bundle, llm_reasoner)
                if assessment is not None:
                    browser_assessments.append(assessment)

        emit("RUNNING_MULTIMODAL_REASONING", "Combining text and visual feature evidence")
        assessments = self._merge_assessments(base.feature_assessments, browser_assessments)
        evidence_set = EvidenceSetSelector(max_supplementary_urls=3).select(
            schema=schema,
            assessments=assessments,
            preferred_primary_url=base.product_match.product_url or base.product_match.best_available_url,
        )
        multimodal_ready = any(bundle.multimodal_scrapable for bundle in browser_bundles)
        coding_ready = bool(evidence_set.coding_ready and (multimodal_ready or not self.config.require_multimodal_for_ready))
        status = "COMPLETED" if coding_ready else "REVIEW_REQUIRED"

        emit("WRITING_OUTPUTS", "Writing the final evidence dossier")
        result = {
            "job_status": status,
            "product": product.to_dict(),
            "feature_set": feature_set,
            "feature_schema_path": str(feature_path),
            "search": {
                "query": base.search_query,
                "serpapi_requests_used": 1,
                "feature_schema_used_by_search": False,
            },
            "product_match": base.product_match.to_dict(),
            "primary_url": evidence_set.primary_url,
            "supplementary_urls": list(evidence_set.supplementary_urls),
            "evidence_set": evidence_set.to_dict(),
            "feature_assessments": [assessment.to_dict() for assessment in assessments],
            "browser_evidence": [bundle.to_dict() for bundle in browser_bundles],
            "multimodal_ready": multimodal_ready,
            "coding_ready": coding_ready,
            "artifact_dir": str(self.config.artifact_root / product.row_id),
        }
        output = self.config.artifact_root / product.row_id / "orchestrated_result.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_json(output, result)
        return result

    def _browser_needed(self, base: FeatureAwareHarnessResult) -> bool:
        if not base.product_match.product_url:
            return True
        if base.evidence_set is None or not base.evidence_set.coding_ready:
            return True
        selected = set(base.evidence_set.selected_urls)
        for card in base.state.scorecards:
            if card.candidate.url in selected and card.scrape and not card.scrape.image_urls:
                return True
        return False

    def _browser_urls(self, base: FeatureAwareHarnessResult) -> tuple[str, ...]:
        preferred = [base.product_match.product_url, base.product_match.best_available_url]
        preferred.extend(card.candidate.url for card in base.state.scorecards if not card.hard_failures)
        preferred.extend(card.candidate.url for card in base.state.scorecards)
        return tuple(dict.fromkeys(url for url in preferred if url))[: self.config.browser_candidate_limit]

    def _assessment_from_browser(
        self,
        product: ProductQuery,
        schema: FeatureSchema,
        bundle: Any,
        llm_reasoner: Any,
    ) -> URLFeatureAssessment | None:
        if not bundle.browser_openable or not bundle.text_scrapable:
            return None
        scrape = self._scrape_from_bundle(bundle)
        verifier = ProductIdentityVerifier(policy=HarnessConfig.from_env().with_effective_policy().policy)
        verification = verifier.verify(product, scrape)
        assessment = FeatureAwareEvidenceExtractor().extract(
            product=product,
            schema=schema,
            scrape=scrape,
            verification=verification,
            reasoner=llm_reasoner,
        )
        if not assessment.identity_accepted or not self.config.enable_vision_reasoning:
            return assessment
        if not assessment.missing_features or not bundle.multimodal_scrapable:
            return assessment
        try:
            vision = MultimodalFeatureReasoner().evaluate(
                schema=schema,
                bundle=bundle,
                missing_feature_ids=assessment.missing_features,
            )
        except Exception:
            return assessment
        return self._merge_visual_evidence(schema, assessment, vision)

    @staticmethod
    def _scrape_from_bundle(bundle: Any) -> ScrapeResult:
        text = bundle.rendered_text or ""
        image_urls = tuple(asset.source_image_url or asset.local_path for asset in bundle.visual_assets if asset.vision_ready)
        return ScrapeResult(
            url=bundle.requested_url,
            scraped=True,
            success=bundle.browser_openable,
            reachable=bundle.browser_openable,
            is_scrapable=bundle.text_scrapable,
            status_code=None,
            final_url=bundle.final_url,
            title=bundle.page_title,
            h1=bundle.visible_product_name,
            page_product_name=bundle.visible_product_name,
            image_urls=image_urls,
            richness_score=min(1.0, 0.35 + 0.15 * bool(text) + 0.25 * bool(image_urls) + 0.25 * bundle.rendered_product_verified),
            markdown_excerpt=text[:4000],
            markdown_chars=len(text),
            word_count=len(text.split()),
            image_count=len(image_urls),
            looks_like_product_page=bundle.rendered_product_verified,
            is_soft_404=False,
            verification_text=text[:30_000],
            attributes={"browser_evidence": "true", "visual_asset_count": len(image_urls)},
        )

    @staticmethod
    def _merge_visual_evidence(
        schema: FeatureSchema,
        assessment: URLFeatureAssessment,
        visual: Iterable[FeatureEvidence],
    ) -> URLFeatureAssessment:
        merged = {item.feature_id: item for item in assessment.evidence}
        for item in visual:
            current = merged.get(item.feature_id)
            if current is None or (not current.supported and item.supported) or item.confidence > current.confidence:
                merged[item.feature_id] = item
        ordered = tuple(merged[feature.feature_id] for feature in schema.features)
        supported = {item.feature_id for item in ordered if item.supported}
        conflicts = tuple(item.feature_id for item in ordered if item.status.value == "CONFLICTING_EVIDENCE")
        missing = tuple(feature.feature_id for feature in schema.features if feature.feature_id not in supported)
        coverage = round(len(supported) / max(1, len(schema.features)), 4)
        return replace(
            assessment,
            evidence=ordered,
            coverage=coverage,
            required_coverage=coverage,
            critical_coverage=coverage,
            missing_features=missing,
            conflicting_features=conflicts,
            source_role="PRIMARY_CANDIDATE" if coverage >= schema.required_coverage_threshold else "SUPPLEMENTARY_CANDIDATE",
        )

    @staticmethod
    def _merge_assessments(
        base: Iterable[URLFeatureAssessment],
        browser: Iterable[URLFeatureAssessment],
    ) -> tuple[URLFeatureAssessment, ...]:
        by_url: dict[str, URLFeatureAssessment] = {item.url: item for item in base}
        for item in browser:
            current = by_url.get(item.url)
            if current is None or (item.identity_accepted and item.coverage > current.coverage):
                by_url[item.url] = item
        return tuple(by_url.values())

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
