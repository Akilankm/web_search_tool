from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from src.product_evidence_harness.numeric_safety import safe_float, safe_int


_PATCHED = False


class _PlannerCounterProxy:
    """Expose null-safe counters while delegating planner behavior unchanged."""

    def __init__(self, planner: Any) -> None:
        object.__setattr__(self, "_planner", planner)

    @property
    def calls(self) -> int:
        return safe_int(
            getattr(self._planner, "calls", 0),
            0,
            minimum=0,
            field_name="adaptive_search_planner.calls",
        )

    @calls.setter
    def calls(self, value: Any) -> None:
        setattr(self._planner, "calls", safe_int(value, 0, minimum=0))

    @property
    def fallbacks(self) -> int:
        return safe_int(
            getattr(self._planner, "fallbacks", 0),
            0,
            minimum=0,
            field_name="adaptive_search_planner.fallbacks",
        )

    @fallbacks.setter
    def fallbacks(self, value: Any) -> None:
        setattr(self._planner, "fallbacks", safe_int(value, 0, minimum=0))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._planner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_planner":
            object.__setattr__(self, name, value)
        elif name in {"calls", "fallbacks"}:
            setattr(type(self), name).fset(self, value)
        else:
            setattr(self._planner, name, value)


def _patch_adaptive_search() -> None:
    from src.product_evidence_harness import adaptive_search_runtime
    from src.product_evidence_harness.three_stage_pipeline import (
        ThreeStageProductEvidenceHarness,
    )

    def bounded_int(name: str, default: int, low: int, high: int) -> int:
        return safe_int(
            adaptive_search_runtime.os.getenv(name),
            default,
            minimum=low,
            maximum=high,
            field_name=name,
        )

    adaptive_search_runtime._bounded_int = bounded_int

    current_run = ThreeStageProductEvidenceHarness.run
    if getattr(current_run, "_null_numeric_boundary_wrapper", False):
        return

    def run(self, *args, **kwargs):
        original_planner = getattr(self, "adaptive_search_planner", None)
        if original_planner is None:
            return current_run(self, *args, **kwargs)

        # The adaptive runtime reads planner counters after search. Some injected
        # planners expose those optional counters as null, which previously caused
        # int(None) after the expensive search had already completed.
        setattr(
            original_planner,
            "calls",
            safe_int(getattr(original_planner, "calls", 0), 0, minimum=0),
        )
        setattr(
            original_planner,
            "fallbacks",
            safe_int(getattr(original_planner, "fallbacks", 0), 0, minimum=0),
        )
        self.adaptive_search_planner = _PlannerCounterProxy(original_planner)
        try:
            return current_run(self, *args, **kwargs)
        finally:
            self.adaptive_search_planner = original_planner

    run._null_numeric_boundary_wrapper = True
    ThreeStageProductEvidenceHarness.run = run


def _patch_browser_contracts() -> None:
    from src.product_evidence_harness import browser_contracts

    def evidence_intent_post_init(self) -> None:
        object.__setattr__(
            self,
            "maximum_images",
            safe_int(
                self.maximum_images,
                10,
                minimum=0,
                maximum=30,
                field_name="intent.maximum_images",
            ),
        )
        object.__setattr__(
            self,
            "maximum_screenshots",
            safe_int(
                self.maximum_screenshots,
                8,
                minimum=0,
                maximum=20,
                field_name="intent.maximum_screenshots",
            ),
        )
        object.__setattr__(
            self,
            "maximum_actions",
            safe_int(
                self.maximum_actions,
                30,
                minimum=1,
                maximum=100,
                field_name="intent.maximum_actions",
            ),
        )
        object.__setattr__(
            self,
            "requested_evidence_categories",
            tuple(
                dict.fromkeys(
                    str(item).strip()
                    for item in (self.requested_evidence_categories or ())
                    if str(item).strip()
                )
            ),
        )

    browser_contracts.EvidenceIntent.__post_init__ = evidence_intent_post_init

    current_visual_from_mapping = browser_contracts.VisualAsset.from_mapping.__func__

    @classmethod
    def visual_from_mapping(cls, value: Mapping[str, Any]):
        payload = dict(value or {})
        payload["width"] = safe_int(payload.get("width"), 0, minimum=0)
        payload["height"] = safe_int(payload.get("height"), 0, minimum=0)
        payload["size_bytes"] = safe_int(payload.get("size_bytes"), 0, minimum=0)
        return current_visual_from_mapping(cls, payload)

    browser_contracts.VisualAsset.from_mapping = visual_from_mapping


def _patch_browser_runtime_config() -> None:
    from src.product_evidence_harness.browser_service import controller

    @classmethod
    def from_env(cls):
        return cls(
            artifact_root=Path(os.getenv("ARTIFACT_ROOT") or "/data/artifacts"),
            headless=str(os.getenv("BROWSER_HEADLESS") or "true").strip().lower()
            in {"1", "true", "yes", "on"},
            navigation_timeout_ms=safe_int(
                os.getenv("BROWSER_NAVIGATION_TIMEOUT_MS"),
                60_000,
                minimum=1_000,
                maximum=300_000,
                field_name="BROWSER_NAVIGATION_TIMEOUT_MS",
            ),
            action_timeout_ms=safe_int(
                os.getenv("BROWSER_ACTION_TIMEOUT_MS"),
                8_000,
                minimum=500,
                maximum=60_000,
                field_name="BROWSER_ACTION_TIMEOUT_MS",
            ),
            max_contexts=safe_int(
                os.getenv("BROWSER_MAX_CONTEXTS"),
                3,
                minimum=1,
                maximum=32,
                field_name="BROWSER_MAX_CONTEXTS",
            ),
            viewport_width=safe_int(
                os.getenv("BROWSER_VIEWPORT_WIDTH"),
                1440,
                minimum=320,
                maximum=7680,
                field_name="BROWSER_VIEWPORT_WIDTH",
            ),
            viewport_height=safe_int(
                os.getenv("BROWSER_VIEWPORT_HEIGHT"),
                1100,
                minimum=320,
                maximum=4320,
                field_name="BROWSER_VIEWPORT_HEIGHT",
            ),
            minimum_image_width=safe_int(
                os.getenv("BROWSER_MIN_IMAGE_WIDTH"),
                240,
                minimum=0,
                maximum=4096,
                field_name="BROWSER_MIN_IMAGE_WIDTH",
            ),
            minimum_image_height=safe_int(
                os.getenv("BROWSER_MIN_IMAGE_HEIGHT"),
                240,
                minimum=0,
                maximum=4096,
                field_name="BROWSER_MIN_IMAGE_HEIGHT",
            ),
            maximum_asset_bytes=safe_int(
                os.getenv("BROWSER_MAX_ASSET_BYTES"),
                12 * 1024 * 1024,
                minimum=1,
                maximum=100 * 1024 * 1024,
                field_name="BROWSER_MAX_ASSET_BYTES",
            ),
        )

    controller.BrowserRuntimeConfig.from_env = from_env


def _patch_serpapi_config() -> None:
    from src.product_evidence_harness import config

    current_from_env = config.SerpAPIConfig.from_env.__func__

    @classmethod
    def from_env(cls, **kwargs):
        overrides = dict(kwargs)
        if "organic_num_results" in overrides:
            overrides["organic_num_results"] = safe_int(
                overrides.get("organic_num_results"),
                100,
                minimum=1,
                maximum=100,
                field_name="organic_num_results",
            )
        return current_from_env(cls, **overrides)

    config.SerpAPIConfig.from_env = from_env


def _patch_llm_config() -> None:
    from src.product_evidence_harness.llm import service

    def post_init(self) -> None:
        required = {
            "api_key": self.api_key,
            "api_version": self.api_version,
            "endpoint": self.endpoint,
            "deployment": self.deployment,
        }
        missing = [
            name for name, value in required.items() if not str(value or "").strip()
        ]
        if missing:
            raise ValueError("Missing LLM configuration fields: " + ", ".join(missing))

        object.__setattr__(
            self,
            "max_tokens",
            safe_int(
                self.max_tokens,
                1600,
                minimum=1,
                maximum=32768,
                field_name="LLM max_tokens",
            ),
        )
        object.__setattr__(
            self,
            "temperature",
            safe_float(
                self.temperature,
                0.0,
                minimum=0.0,
                maximum=2.0,
                field_name="LLM temperature",
            ),
        )
        object.__setattr__(
            self,
            "connect_timeout",
            safe_float(
                self.connect_timeout,
                15.0,
                minimum=1.0,
                maximum=120.0,
                field_name="LLM connect_timeout",
            ),
        )
        object.__setattr__(
            self,
            "read_timeout",
            safe_float(
                self.read_timeout,
                120.0,
                minimum=5.0,
                maximum=600.0,
                field_name="LLM read_timeout",
            ),
        )
        object.__setattr__(
            self,
            "max_retries",
            safe_int(
                self.max_retries,
                2,
                minimum=0,
                maximum=5,
                field_name="LLM max_retries",
            ),
        )

    service.LLMConfig.__post_init__ = post_init


def apply_null_numeric_runtime_patch() -> None:
    """Remove raw ``int(None)`` failure modes from active runtime boundaries."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    _patch_adaptive_search()
    _patch_browser_contracts()
    _patch_browser_runtime_config()
    _patch_serpapi_config()
    _patch_llm_config()
