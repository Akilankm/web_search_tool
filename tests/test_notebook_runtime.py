from __future__ import annotations

import asyncio
from pathlib import Path

from product_url_v2.browser import BrowserClient
from product_url_v2.config import BrowserConfig
from product_url_v2.models import BrowserEvidence, GateStatus


class ImmediateBrowser(BrowserClient):
    async def _investigate(self, url: str, row_id: str, candidate_id: str) -> BrowserEvidence:
        return BrowserEvidence(
            url=url,
            access=GateStatus.PASS,
            final_url=url,
            title="Exact product",
            visible_text="Exact product details " * 10,
        )


def test_browser_client_runs_inside_existing_notebook_event_loop(tmp_path: Path) -> None:
    client = ImmediateBrowser(BrowserConfig(), tmp_path)

    async def invoke() -> BrowserEvidence:
        # Jupyter owns a running loop when synchronous notebook cells execute.
        return client.investigate("https://shop.example/product/item", "ROW-1", "C-1")

    evidence = asyncio.run(invoke())

    assert evidence.access is GateStatus.PASS
    assert evidence.final_url == "https://shop.example/product/item"


def test_browser_client_uses_local_artifact_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PRODUCT_URL_ARTIFACT_ROOT", str(tmp_path))

    client = BrowserClient.from_env(BrowserConfig())

    assert client.artifact_root == tmp_path
    assert not hasattr(client.config, "base_url")
