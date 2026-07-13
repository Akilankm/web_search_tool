from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

from src.product_evidence_harness.environment import (
    EnvironmentValidationError,
    validate_runtime_environment as _validate_legacy_environment,
)


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off"}


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
    serpapi_request_limit: int
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
    """Validate the strict three-stage production contract.

    The legacy validator is reused for secret, endpoint, permission, and
    operational checks. Its obsolete one-credit value is overridden only in the
    validation copy; the real runtime value must be exactly three.
    """

    values = _effective_values(env_file, environ)
    if enforce_three_stage:
        _enforce_three_stage_settings(values)

    compatibility_values = dict(values)
    compatibility_values["PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES"] = "1"
    compatibility_values["PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES"] = "0"

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
    ) + ("three_stage_cost_and_acceptance_controls_validated",)

    return ThreeStageEnvironmentValidationReport(
        env_file=base.env_file,
        env_file_loaded=base.env_file_loaded,
        env_file_permissions_checked=base.env_file_permissions_checked,
        serpapi_configured=base.serpapi_configured,
        llm_feature_reasoning_enabled=base.llm_feature_reasoning_enabled,
        llm_configured=base.llm_configured,
        one_credit_contract_enforced=False,
        three_stage_contract_enforced=enforce_three_stage,
        serpapi_request_limit=3,
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


def _enforce_three_stage_settings(values: Mapping[str, str]) -> None:
    workflow = str(
        values.get("PRODUCT_HARNESS_WORKFLOW", "three_stage_feature_aware")
    ).strip()
    if workflow not in {
        "three_stage_feature_aware",
        "one_credit_feature_aware",
    }:
        raise EnvironmentValidationError(
            "PRODUCT_HARNESS_WORKFLOW must be three_stage_feature_aware"
        )

    organic = _strict_int(
        values,
        "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES",
        3,
        minimum=3,
        maximum=3,
    )
    ai_mode = _strict_int(
        values,
        "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES",
        0,
        minimum=0,
        maximum=0,
    )
    if organic != 3 or ai_mode != 0:
        raise EnvironmentValidationError(
            "Three-stage workflow requires organic=3 and AI Mode=0"
        )

    for name in (
        "PRODUCT_HARNESS_COUNTRY_FIRST",
        "PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK",
        "PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY",
        "PRODUCT_HARNESS_REJECT_EXPIRING_URLS",
        "PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE",
    ):
        if not _strict_bool(values, name, True):
            raise EnvironmentValidationError(
                f"{name} must be true for the production runner"
            )

    _strict_int(
        values,
        "PRODUCT_HARNESS_SCRAPE_TOP_K_PER_STAGE",
        6,
        minimum=1,
        maximum=10,
    )
    _strict_int(
        values,
        "PRODUCT_HARNESS_BROWSER_CANDIDATE_LIMIT",
        9,
        minimum=3,
        maximum=30,
    )


def _strict_bool(
    values: Mapping[str, str],
    name: str,
    default: bool,
) -> bool:
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
        value = (
            default
            if raw is None or str(raw).strip() == ""
            else int(str(raw).strip())
        )
    except ValueError as exc:
        raise EnvironmentValidationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise EnvironmentValidationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value
