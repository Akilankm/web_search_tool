from __future__ import annotations

import os
from typing import Any

from loguru import logger


_PATCHED = False


def _enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def apply_agentic_browser_fallback_patch() -> None:
    """Fall back to deterministic rendered-page capture when LLM planning fails.

    The fallback does not bypass strict acceptance. It only supplies a browser
    evidence bundle so the existing deterministic identity, feature, URL,
    scrapability, and durability gates can make the final decision.
    """

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from src.product_evidence_harness.llm.agentic_browser import (
        AgenticBrowserInvestigator,
    )

    original_investigate = AgenticBrowserInvestigator.investigate

    def investigate(self, *, request, schema, progress=None):
        bundle, dossier = original_investigate(
            self,
            request=request,
            schema=schema,
            progress=progress,
        )
        if bundle is not None or not _enabled(
            "PRODUCT_HARNESS_ALLOW_DETERMINISTIC_BROWSER_FALLBACK_ON_LLM_ERROR",
            True,
        ):
            return bundle, dossier

        failure = str(getattr(dossier, "error", "") or "")
        if not failure:
            return bundle, dossier

        emit = progress or (lambda *_args: None)
        try:
            fallback_bundle = self.browser.acquire(request)
        except Exception as exc:
            logger.warning(
                "Deterministic browser fallback failed | candidate_id={} | original_error={} | fallback_error={}",
                request.candidate_id,
                failure[:240],
                type(exc).__name__,
            )
            return bundle, dossier

        dossier.status = "COMPLETED"
        dossier.final_url = fallback_bundle.final_url or fallback_bundle.requested_url
        dossier.termination_reason = "DETERMINISTIC_BROWSER_FALLBACK_AFTER_LLM_FAILURE"
        dossier.final_llm_assessment = {
            **dict(getattr(dossier, "final_llm_assessment", {}) or {}),
            "agentic_llm_failed": True,
            "agentic_llm_error": failure[:500],
            "deterministic_browser_fallback": True,
        }
        dossier.error = None
        emit(
            "AGENTIC_BROWSER_INVESTIGATION",
            f"{request.candidate_id} | DETERMINISTIC_BROWSER_FALLBACK | openable={fallback_bundle.browser_openable} | scrapable={fallback_bundle.text_scrapable}",
        )
        logger.warning(
            "Agentic LLM failed; deterministic browser evidence retained | candidate_id={} | error={}",
            request.candidate_id,
            failure[:240],
        )
        return fallback_bundle, dossier

    AgenticBrowserInvestigator.investigate = investigate
