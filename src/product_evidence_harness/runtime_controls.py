from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Mapping


@dataclass(frozen=True, slots=True)
class RuntimeControlSpec:
    key: str
    label: str
    env_names: tuple[str, ...]
    default: int
    minimum: int
    maximum: int
    help_text: str


RUNTIME_CONTROL_SPECS: tuple[RuntimeControlSpec, ...] = (
    RuntimeControlSpec(
        key="serpapi_credits",
        label="Search credits",
        env_names=("PRODUCT_HARNESS_MAX_SERPAPI_CREDITS",),
        default=3,
        minimum=1,
        maximum=3,
        help_text="Maximum paid search actions available to one product run.",
    ),
    RuntimeControlSpec(
        key="full_scrapes",
        label="Full-page extractions",
        env_names=("PRODUCT_HARNESS_MAX_FULL_SCRAPES", "PRODUCT_HARNESS_MAX_SCRAPES"),
        default=6,
        minimum=1,
        maximum=12,
        help_text="Maximum candidate pages admitted for full extraction and verification.",
    ),
    RuntimeControlSpec(
        key="scrapes_per_domain",
        label="Extractions per domain",
        env_names=("PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN",),
        default=2,
        minimum=1,
        maximum=4,
        help_text="Maximum full-page extractions allowed from a single domain.",
    ),
    RuntimeControlSpec(
        key="planner_candidates",
        label="Planner candidate limit",
        env_names=("PRODUCT_HARNESS_SEARCH_PLANNER_MAX_CANDIDATES",),
        default=8,
        minimum=3,
        maximum=20,
        help_text="Maximum ranked candidates supplied to adaptive search planning.",
    ),
    RuntimeControlSpec(
        key="agentic_candidates",
        label="Browser investigation limit",
        env_names=("PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES",),
        default=3,
        minimum=1,
        maximum=8,
        help_text="Maximum candidate pages investigated through the rendered browser workflow.",
    ),
    RuntimeControlSpec(
        key="browser_turns_per_candidate",
        label="Browser turns per candidate",
        env_names=("PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE",),
        default=4,
        minimum=1,
        maximum=12,
        help_text="Maximum observe-plan-act cycles allowed for each browser candidate.",
    ),
    RuntimeControlSpec(
        key="browser_actions_per_candidate",
        label="Browser actions per candidate",
        env_names=("PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE",),
        default=6,
        minimum=1,
        maximum=24,
        help_text="Maximum controlled clicks, expansions, scrolling and evidence actions per candidate.",
    ),
    RuntimeControlSpec(
        key="images_in_reasoning",
        label="Visual assets per reasoning turn",
        env_names=("PRODUCT_HARNESS_AGENTIC_MAX_IMAGES",),
        default=8,
        minimum=4,
        maximum=20,
        help_text="Maximum screenshots or product images available to one visual reasoning turn.",
    ),
)

_SPEC_BY_KEY = {spec.key: spec for spec in RUNTIME_CONTROL_SPECS}
_SPEC_BY_ENV = {
    env_name: spec
    for spec in RUNTIME_CONTROL_SPECS
    for env_name in spec.env_names
}
_CURRENT_CONTROLS: ContextVar[dict[str, int]] = ContextVar(
    "product_evidence_runtime_controls",
    default={},
)


def normalize_runtime_controls(raw: Mapping[str, Any] | None) -> dict[str, int]:
    """Validate the approved per-job operational control surface."""

    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("runtime_options must be an object")

    unknown = sorted(set(raw) - set(_SPEC_BY_KEY))
    if unknown:
        raise ValueError("Unsupported runtime option(s): " + ", ".join(unknown))

    normalized: dict[str, int] = {}
    for key, value in raw.items():
        spec = _SPEC_BY_KEY[key]
        if isinstance(value, bool):
            raise ValueError(f"{key} must be an integer, not a boolean")
        try:
            integer = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if integer < spec.minimum or integer > spec.maximum:
            raise ValueError(
                f"{key} must be between {spec.minimum} and {spec.maximum}; received {integer}"
            )
        normalized[key] = integer
    return normalized


def default_runtime_controls() -> dict[str, int]:
    return {spec.key: spec.default for spec in RUNTIME_CONTROL_SPECS}


def current_runtime_controls() -> dict[str, int]:
    return dict(_CURRENT_CONTROLS.get())


def _environment_default(spec: RuntimeControlSpec) -> int:
    for env_name in spec.env_names:
        raw = os.getenv(env_name)
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError, OverflowError):
            continue
        return max(spec.minimum, min(spec.maximum, value))
    return spec.default


def effective_runtime_controls() -> dict[str, int]:
    requested = current_runtime_controls()
    return {
        spec.key: requested.get(spec.key, _environment_default(spec))
        for spec in RUNTIME_CONTROL_SPECS
    }


@contextmanager
def runtime_control_scope(raw: Mapping[str, Any] | None) -> Iterator[dict[str, int]]:
    normalized = normalize_runtime_controls(raw)
    token = _CURRENT_CONTROLS.set(normalized)
    try:
        yield effective_runtime_controls()
    finally:
        _CURRENT_CONTROLS.reset(token)


class ContextAwareEnvironment:
    """Resolve approved context-local controls before process environment values."""

    def __init__(self, base_os: Any) -> None:
        self._base_os = base_os

    def getenv(self, name: str, default: Any = None) -> Any:
        spec = _SPEC_BY_ENV.get(name)
        if spec is not None:
            requested = current_runtime_controls()
            if spec.key in requested:
                return str(requested[spec.key])
        return self._base_os.getenv(name, default)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base_os, name)


def runtime_control_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "default": spec.default,
            "minimum": spec.minimum,
            "maximum": spec.maximum,
            "help_text": spec.help_text,
        }
        for spec in RUNTIME_CONTROL_SPECS
    ]
