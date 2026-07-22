from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SearchConfig:
    credit_limit: int = 3
    results_per_search: int = 20
    max_retries: int = 2
    country_localized: bool = True


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    max_candidates: int = 12
    max_per_domain: int = 2
    max_workers: int = 6
    max_response_bytes: int = 3_000_000
    user_agent: str = "Mozilla/5.0 ProductURLResolver/1.0"


@dataclass(frozen=True, slots=True)
class BrowserConfig:
    enabled: bool = True
    required: bool = False
    max_candidates: int = 3
    base_url: str = "http://browser:9000"
    timeout_seconds: int = 90


@dataclass(frozen=True, slots=True)
class ReasoningConfig:
    enabled: bool = False
    required: bool = False
    deployment: str = ""
    endpoint: str = ""
    api_version: str = ""
    consumer_id: str = ""
    timeout_seconds: int = 60
    max_retries: int = 2
    temperature: float = 0.0
    max_hypotheses: int = 5


@dataclass(frozen=True, slots=True)
class DecisionConfig:
    verified_identity_threshold: float = 0.86
    review_identity_threshold: float = 0.55
    wrong_product_threshold: float = 0.30
    minimum_direct_page_score: float = 0.50


@dataclass(frozen=True, slots=True)
class ReleaseGates:
    url_delivery_rate: float = 0.98
    correct_product_delivery_rate: float = 0.95
    candidate_recall_at_k: float = 0.98
    wrong_product_escape_rate: float = 0.01
    direct_product_page_rate: float = 0.98


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    runtime_contract: str = "product-url-resolver-v1"
    artifact_root: Path = Path("data/artifacts")
    feature_set_root: Path = Path("feature_sets")
    request_timeout_seconds: int = 30
    search: SearchConfig = field(default_factory=SearchConfig)
    acquisition: AcquisitionConfig = field(default_factory=AcquisitionConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
    decision: DecisionConfig = field(default_factory=DecisionConfig)
    release_gates: ReleaseGates = field(default_factory=ReleaseGates)

    def with_runtime_options(self, options: Mapping[str, Any] | None) -> "RuntimeConfig":
        if not options:
            return self
        search = replace(
            self.search,
            credit_limit=_bounded_int(options.get("search_credits"), self.search.credit_limit, 1, 3),
            results_per_search=_bounded_int(options.get("results_per_search"), self.search.results_per_search, 5, 100),
        )
        acquisition = replace(
            self.acquisition,
            max_candidates=_bounded_int(options.get("max_candidates"), self.acquisition.max_candidates, 1, 50),
            max_per_domain=_bounded_int(options.get("max_per_domain"), self.acquisition.max_per_domain, 1, 10),
            max_workers=_bounded_int(options.get("max_workers"), self.acquisition.max_workers, 1, 16),
        )
        browser = replace(
            self.browser,
            enabled=_as_bool(options.get("browser_enabled"), self.browser.enabled),
            required=_as_bool(options.get("browser_required"), self.browser.required),
            max_candidates=_bounded_int(options.get("browser_candidates"), self.browser.max_candidates, 0, 10),
        )
        reasoning = replace(
            self.reasoning,
            enabled=_as_bool(options.get("reasoning_enabled"), self.reasoning.enabled),
            required=_as_bool(options.get("reasoning_required"), self.reasoning.required),
        )
        return replace(self, search=search, acquisition=acquisition, browser=browser, reasoning=reasoning)


def load_config(path: str | Path | None = None) -> RuntimeConfig:
    target = Path(path or os.getenv("PRODUCT_URL_CONFIG") or "config/default.json")
    payload: dict[str, Any] = {}
    if target.is_file():
        loaded = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("runtime configuration must be a JSON object")
        payload = loaded
    runtime = RuntimeConfig(
        runtime_contract=str(payload.get("runtime_contract") or "product-url-resolver-v1"),
        artifact_root=Path(os.getenv("PRODUCT_URL_ARTIFACT_ROOT") or payload.get("artifact_root") or "data/artifacts"),
        feature_set_root=Path(os.getenv("PRODUCT_URL_FEATURE_SET_ROOT") or payload.get("feature_set_root") or "feature_sets"),
        request_timeout_seconds=_bounded_int(payload.get("request_timeout_seconds"), 30, 5, 300),
        search=_from_mapping(SearchConfig, payload.get("search")),
        acquisition=_from_mapping(AcquisitionConfig, payload.get("acquisition")),
        browser=_from_mapping(BrowserConfig, payload.get("browser")),
        reasoning=_from_mapping(ReasoningConfig, payload.get("reasoning")),
        decision=_from_mapping(DecisionConfig, payload.get("decision")),
        release_gates=_from_mapping(ReleaseGates, payload.get("release_gates")),
    )
    browser = replace(
        runtime.browser,
        enabled=_as_bool(os.getenv("PRODUCT_URL_BROWSER_ENABLED"), runtime.browser.enabled),
        required=_as_bool(os.getenv("PRODUCT_URL_BROWSER_REQUIRED"), runtime.browser.required),
        base_url=str(os.getenv("PRODUCT_URL_BROWSER_BASE_URL") or runtime.browser.base_url).rstrip("/"),
    )
    reasoning = replace(
        runtime.reasoning,
        enabled=_as_bool(os.getenv("PRODUCT_URL_REASONING_ENABLED"), runtime.reasoning.enabled),
        required=_as_bool(os.getenv("PRODUCT_URL_REASONING_REQUIRED"), runtime.reasoning.required),
        deployment=_first_env("PCA_LLM_DEPLOYMENT", "LLM_DEPLOYMENT", "LLM_MODEL") or runtime.reasoning.deployment,
        endpoint=_first_env("PCA_LLM_ENDPOINT", "LLM_ENDPOINT", "LLM_BASE_URL") or runtime.reasoning.endpoint,
        api_version=_first_env("PCA_LLM_API_VERSION", "LLM_API_VERSION") or runtime.reasoning.api_version,
        consumer_id=_first_env("PCA_LLM_CONSUMER_ID", "LLM_CONSUMER_ID") or runtime.reasoning.consumer_id,
        max_retries=_bounded_int(
            _first_env("PCA_LLM_MAX_RETRIES", "LLM_MAX_RETRIES"),
            runtime.reasoning.max_retries,
            0,
            5,
        ),
    )
    return replace(runtime, browser=browser, reasoning=reasoning)


def load_feature_set(root: Path, name: str) -> dict[str, Any]:
    candidate = Path(name)
    path = candidate if candidate.suffix == ".json" else root / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"feature set not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("feature set must be a JSON object")
    required = payload.get("required_fields")
    if not isinstance(required, list) or not all(isinstance(item, str) and item for item in required):
        raise ValueError("feature set required_fields must be a non-empty string list")
    return payload


def _from_mapping(cls, value: Any):
    if not isinstance(value, Mapping):
        return cls()
    allowed = cls.__dataclass_fields__.keys()
    return cls(**{key: item for key, item in value.items() if key in allowed})


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, number))


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _first_env(*names: str) -> str:
    for name in names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    return ""
