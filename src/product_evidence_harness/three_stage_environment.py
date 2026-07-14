from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

from src.product_evidence_harness.adaptive_search import DEFAULT_ALLOWED_ENGINES
from src.product_evidence_harness.environment import (
    EnvironmentValidationError,
    validate_runtime_environment as _validate_legacy_environment,
)


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off"}
_REQUIRED_ADAPTIVE_ENGINES = {
    "google",
    "google_shopping",
    "google_ai_mode",
    "google_immersive_product",
}


@dataclass(frozen=True, slots=True)
class ThreeStageEnvironmentValidationReport:
    env_file: str | None
    env_file_loaded: bool
    env_file_permissions_checked: bool
    serpapi_configured: bool
    llm_feature_reasoning_enabled: bool
    llm_configured: bool
    one_credit_contract_enforced: bool
    three_stage_contract_enforced: bool
    adaptive_search_contract_enforced: bool
    serpapi_request_limit: int
    allowed_search_engines: tuple[str, ...]
    llm_search_planning_enabled: bool
    llm_search_feedback_enabled: bool
    agentic_browser_enabled: bool
    agentic_browser_required: bool
    agentic_browser_contract_enforced: bool
    max_agentic_candidates: int
    max_agentic_turns_per_candidate: int
    max_agentic_actions_per_candidate: int
    checks_passed: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


EnvironmentValidationReport = ThreeStageEnvironmentValidationReport


def validate_runtime_environment(
    env_file: str | Path | None = ".env",
    *,
    require_serpapi: bool = True,
    enforce_three_stage: bool = True,
    strict_file_permissions: bool = True,
    environ: Mapping[str, str] | None = None,
) -> ThreeStageEnvironmentValidationReport:
    """Validate the adaptive three-credit search and compact browser contract."""

    values = _effective_values(env_file, environ)
    adaptive = _enforce_adaptive_settings(values) if enforce_three_stage else {
        "credits": 3,
        "engines": DEFAULT_ALLOWED_ENGINES,
        "planning": True,
        "feedback": True,
    }

    agentic_enabled = _strict_bool(
        values, "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER", True
    )
    agentic_required = _strict_bool(
        values, "PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER", True
    )
    feature_reasoning_enabled = _strict_bool(
        values,
        "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING",
        False,
    )

    # The legacy validator still owns credential, permission and security checks.
    # Present it with a one-credit compatibility view so it does not reject the
    # new adaptive planning flags as obsolete expansive-search controls.
    compatibility_values = dict(values)
    compatibility_values["PRODUCT_HARNESS_WORKFLOW"] = "one_credit_feature_aware"
    compatibility_values["PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES"] = "1"
    compatibility_values["PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES"] = "0"
    compatibility_values["PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING"] = "false"
    compatibility_values["PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK"] = "false"
    if agentic_enabled:
        compatibility_values["PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING"] = "true"

    base = _validate_legacy_environment(
        env_file,
        require_serpapi=require_serpapi,
        enforce_one_credit=True,
        strict_file_permissions=strict_file_permissions,
        environ=compatibility_values,
    )
    checks = tuple(
        check
        for check in base.checks_passed
        if check != "one_credit_cost_controls_validated"
    ) + (
        "adaptive_three_credit_multi_engine_search_validated",
        "llm_search_planner_and_feedback_validated",
        "precision_and_acceptance_controls_validated",
        "llm_agentic_browser_context_budget_validated",
    )

    configured_candidates = _strict_int(
        values,
        "PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES",
        3,
        minimum=1,
        maximum=90,
    )
    configured_turns = _strict_int(
        values,
        "PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE",
        4,
        minimum=1,
        maximum=30,
    )
    configured_actions = _strict_int(
        values,
        "PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE",
        6,
        minimum=1,
        maximum=60,
    )

    return ThreeStageEnvironmentValidationReport(
        env_file=base.env_file,
        env_file_loaded=base.env_file_loaded,
        env_file_permissions_checked=base.env_file_permissions_checked,
        serpapi_configured=base.serpapi_configured,
        llm_feature_reasoning_enabled=feature_reasoning_enabled,
        llm_configured=base.llm_configured,
        one_credit_contract_enforced=False,
        three_stage_contract_enforced=enforce_three_stage,
        adaptive_search_contract_enforced=enforce_three_stage,
        serpapi_request_limit=int(adaptive["credits"]),
        allowed_search_engines=tuple(adaptive["engines"]),
        llm_search_planning_enabled=bool(adaptive["planning"]),
        llm_search_feedback_enabled=bool(adaptive["feedback"]),
        agentic_browser_enabled=agentic_enabled,
        agentic_browser_required=agentic_required,
        agentic_browser_contract_enforced=bool(
            agentic_enabled and agentic_required
        ),
        max_agentic_candidates=min(3, configured_candidates),
        max_agentic_turns_per_candidate=min(4, configured_turns),
        max_agentic_actions_per_candidate=min(6, configured_actions),
        checks_passed=checks,
    )


def _effective_values(
    env_file: str | Path | None,
    environ: Mapping[str, str] | None,
) -> dict[str, str]:
    values: dict[str, str] = {}
    if env_file:
        path = Path(env_file).expanduser()
        if path.is_file():
            values.update(
                {
                    key: str(value)
                    for key, value in dotenv_values(path).items()
                    if value is not None
                }
            )
    values.update(
        {
            key: str(value)
            for key, value in (
                os.environ.items() if environ is None else environ.items()
            )
        }
    )
    return values


def _enforce_adaptive_settings(values: Mapping[str, str]) -> dict[str, object]:
    workflow = str(
        values.get("PRODUCT_HARNESS_WORKFLOW", "three_stage_feature_aware")
    ).strip()
    if workflow != "three_stage_feature_aware":
        raise EnvironmentValidationError(
            "PRODUCT_HARNESS_WORKFLOW must be three_stage_feature_aware"
        )

    credits = _strict_int(
        values,
        "PRODUCT_HARNESS_MAX_SERPAPI_CREDITS",
        3,
        minimum=3,
        maximum=3,
    )
    planning = _strict_bool(
        values,
        "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING",
        True,
    )
    feedback = _strict_bool(
        values,
        "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK",
        True,
    )
    require_planning = _strict_bool(
        values,
        "PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING",
        True,
    )
    if not planning or not feedback or not require_planning:
        raise EnvironmentValidationError(
            "Adaptive production search requires LLM search planning, feedback, "
            "and the required-planner contract to be enabled"
        )

    raw_engines = str(
        values.get(
            "PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES",
            ",".join(DEFAULT_ALLOWED_ENGINES),
        )
    )
    engines = tuple(
        dict.fromkeys(
            item.strip().lower()
            for item in raw_engines.split(",")
            if item.strip()
        )
    )
    unknown = sorted(set(engines) - set(DEFAULT_ALLOWED_ENGINES))
    if unknown:
        raise EnvironmentValidationError(
            "Unsupported PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES: "
            + ", ".join(unknown)
        )
    missing = sorted(_REQUIRED_ADAPTIVE_ENGINES - set(engines))
    if missing:
        raise EnvironmentValidationError(
            "Adaptive search requires these engines: " + ", ".join(missing)
        )

    for name in (
        "PRODUCT_HARNESS_COUNTRY_FIRST",
        "PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK",
        "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY",
        "PRODUCT_HARNESS_REJECT_EXPIRING_URLS",
        "PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE",
        "PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER",
        "PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER",
        "PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL",
    ):
        if not _strict_bool(values, name, True):
            raise EnvironmentValidationError(
                f"{name} must be true for the production runner"
            )

    _strict_int(values, "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES", 3, minimum=0, maximum=3)
    _strict_int(values, "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES", 0, minimum=0, maximum=3)
    _strict_int(values, "PRODUCT_HARNESS_SEARCH_PLANNER_MAX_CANDIDATES", 8, minimum=3, maximum=20)
    _strict_int(values, "PRODUCT_HARNESS_SCRAPE_TOP_K_PER_STAGE", 2, minimum=1, maximum=10)
    _strict_int(values, "PRODUCT_HARNESS_BROWSER_CANDIDATE_LIMIT", 3, minimum=1, maximum=90)
    _strict_int(values, "PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES", 3, minimum=1, maximum=90)
    _strict_int(values, "PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE", 4, minimum=1, maximum=30)
    _strict_int(values, "PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE", 6, minimum=1, maximum=60)
    _strict_int(values, "PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS", 4000, minimum=1200, maximum=30000)
    _strict_int(values, "PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS", 15, minimum=5, maximum=100)
    _strict_int(values, "PRODUCT_HARNESS_AGENTIC_MAX_IMAGES", 8, minimum=2, maximum=50)
    _strict_int(values, "PRODUCT_HARNESS_MAX_FULL_SCRAPES", 6, minimum=1, maximum=12)
    _strict_int(values, "PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN", 2, minimum=1, maximum=4)
    _strict_float(values, "PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE", 0.28, minimum=0.05, maximum=0.95)
    return {
        "credits": credits,
        "engines": engines,
        "planning": planning,
        "feedback": feedback,
    }


def _strict_bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    normalized = str(raw).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise EnvironmentValidationError(
        f"{name} must be an explicit boolean (true/false)"
    )


def _strict_int(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = values.get(name)
    try:
        value = default if raw is None or str(raw).strip() == "" else int(str(raw).strip())
    except ValueError as exc:
        raise EnvironmentValidationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise EnvironmentValidationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _strict_float(
    values: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw = values.get(name)
    try:
        value = default if raw is None or str(raw).strip() == "" else float(str(raw).strip())
    except ValueError as exc:
        raise EnvironmentValidationError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise EnvironmentValidationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value
