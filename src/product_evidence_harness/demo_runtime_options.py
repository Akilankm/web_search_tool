from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Mapping


@dataclass(frozen=True, slots=True)
class DemoOptionSpec:
    key: str
    label: str
    env_names: tuple[str, ...]
    default: int
    minimum: int
    maximum: int
    help_text: str


DEMO_OPTION_SPECS: tuple[DemoOptionSpec, ...] = (
    DemoOptionSpec(
        key="serpapi_credits",
        label="SerpAPI search credits",
        env_names=("PRODUCT_HARNESS_MAX_SERPAPI_CREDITS",),
        default=3,
        minimum=1,
        maximum=3,
        help_text="Maximum paid search actions for this product. The production route is capped at three.",
    ),
    DemoOptionSpec(
        key="full_scrapes",
        label="Full page scrapes",
        env_names=("PRODUCT_HARNESS_MAX_FULL_SCRAPES", "PRODUCT_HARNESS_MAX_SCRAPES"),
        default=6,
        minimum=1,
        maximum=12,
        help_text="Maximum candidate pages admitted for full text extraction and verification.",
    ),
    DemoOptionSpec(
        key="scrapes_per_domain",
        label="Scrapes per domain",
        env_names=("PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN",),
        default=2,
        minimum=1,
        maximum=4,
        help_text="Prevents one website from consuming the evidence budget.",
    ),
    DemoOptionSpec(
        key="planner_candidates",
        label="Planner candidate context",
        env_names=("PRODUCT_HARNESS_SEARCH_PLANNER_MAX_CANDIDATES",),
        default=8,
        minimum=3,
        maximum=20,
        help_text="Maximum ranked candidates exposed to the adaptive search planner.",
    ),
    DemoOptionSpec(
        key="agentic_candidates",
        label="Browser-investigated candidates",
        env_names=("PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES",),
        default=3,
        minimum=1,
        maximum=8,
        help_text="Maximum candidate pages opened through the controlled browser workflow.",
    ),
    DemoOptionSpec(
        key="browser_turns_per_candidate",
        label="Browser turns per candidate",
        env_names=("PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE",),
        default=4,
        minimum=1,
        maximum=12,
        help_text="Maximum observe-plan-act turns for each browser candidate.",
    ),
    DemoOptionSpec(
        key="browser_actions_per_candidate",
        label="Browser actions per candidate",
        env_names=("PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE",),
        default=6,
        minimum=1,
        maximum=24,
        help_text="Maximum clicks, expansions, image inspections and evidence actions per candidate.",
    ),
    DemoOptionSpec(
        key="images_in_reasoning",
        label="Images in visual reasoning",
        env_names=("PRODUCT_HARNESS_AGENTIC_MAX_IMAGES",),
        default=8,
        minimum=4,
        maximum=20,
        help_text="Maximum rendered or product images made available to one browser reasoning turn.",
    ),
)

_SPEC_BY_KEY = {spec.key: spec for spec in DEMO_OPTION_SPECS}
_SPEC_BY_ENV = {
    env_name: spec
    for spec in DEMO_OPTION_SPECS
    for env_name in spec.env_names
}
_CURRENT_OPTIONS: ContextVar[dict[str, int]] = ContextVar(
    "product_evidence_demo_runtime_options",
    default={},
)


def normalize_demo_runtime_options(raw: Mapping[str, Any] | None) -> dict[str, int]:
    """Validate the narrow per-job budget surface used by the leadership demo."""

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
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer") from exc
        if integer < spec.minimum or integer > spec.maximum:
            raise ValueError(
                f"{key} must be between {spec.minimum} and {spec.maximum}; received {integer}"
            )
        normalized[key] = integer
    return normalized


def default_demo_runtime_options() -> dict[str, int]:
    return {spec.key: spec.default for spec in DEMO_OPTION_SPECS}


def current_demo_runtime_options() -> dict[str, int]:
    return dict(_CURRENT_OPTIONS.get())


def effective_demo_runtime_options() -> dict[str, int]:
    requested = current_demo_runtime_options()
    return {
        spec.key: requested.get(spec.key, _environment_default(spec))
        for spec in DEMO_OPTION_SPECS
    }


def _environment_default(spec: DemoOptionSpec) -> int:
    for env_name in spec.env_names:
        raw = os.getenv(env_name)
        if raw is None:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        return max(spec.minimum, min(spec.maximum, value))
    return spec.default


@contextmanager
def demo_runtime_option_scope(raw: Mapping[str, Any] | None) -> Iterator[dict[str, int]]:
    normalized = normalize_demo_runtime_options(raw)
    token = _CURRENT_OPTIONS.set(normalized)
    try:
        yield effective_demo_runtime_options()
    finally:
        _CURRENT_OPTIONS.reset(token)


class ContextAwareEnvironment:
    """Module-local ``os`` proxy that resolves approved job overrides first."""

    def __init__(self, base_os: Any) -> None:
        self._base_os = base_os

    def getenv(self, name: str, default: Any = None) -> Any:
        spec = _SPEC_BY_ENV.get(name)
        if spec is not None:
            requested = current_demo_runtime_options()
            if spec.key in requested:
                return str(requested[spec.key])
        return self._base_os.getenv(name, default)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base_os, name)


def runtime_option_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "default": spec.default,
            "minimum": spec.minimum,
            "maximum": spec.maximum,
            "help_text": spec.help_text,
        }
        for spec in DEMO_OPTION_SPECS
    ]
