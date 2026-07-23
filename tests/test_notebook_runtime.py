from __future__ import annotations

import asyncio
from pathlib import Path

from product_url_v2.browser import BrowserClient
from product_url_v2.config import BrowserConfig, ReasoningConfig, RuntimeConfig
from product_url_v2.models import BrowserEvidence, GateStatus


class ImmediateBrowser(BrowserClient):
    async def _investigate(
        self,
        url: str,
        row_id: str,
        candidate_id: str,
    ) -> BrowserEvidence:
        return BrowserEvidence(
            url=url,
            access=GateStatus.PASS,
            final_url=url,
            title="Exact product",
            visible_text="Exact product details " * 10,
        )


def test_browser_client_runs_inside_existing_notebook_event_loop(
    tmp_path: Path,
) -> None:
    client = ImmediateBrowser(BrowserConfig(), tmp_path)

    async def invoke() -> BrowserEvidence:
        return client.investigate(
            "https://shop.example/product/item",
            "ROW-1",
            "C-1",
        )

    evidence = asyncio.run(invoke())

    assert evidence.access is GateStatus.PASS
    assert evidence.final_url == "https://shop.example/product/item"


def test_browser_client_uses_resolved_artifact_root(tmp_path: Path) -> None:
    client = BrowserClient(BrowserConfig(), tmp_path)

    assert client.artifact_root == tmp_path
    assert not hasattr(client.config, "base_url")


def test_notebook_budget_options_do_not_override_runtime_modes() -> None:
    runtime = RuntimeConfig(
        browser=BrowserConfig(enabled=True, required=True),
        reasoning=ReasoningConfig(enabled=True, required=False),
    )

    resolved = runtime.with_runtime_options(
        {
            "search_credits": 2,
            "max_candidates": 8,
            "browser_candidates": 3,
        }
    )

    assert resolved.browser.enabled is True
    assert resolved.browser.required is True
    assert resolved.reasoning.enabled is True
    assert resolved.reasoning.required is False
