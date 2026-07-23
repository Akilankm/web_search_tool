from __future__ import annotations

import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.parse import urlparse

from playwright.async_api import Page, async_playwright

from product_url_v2.config import BrowserConfig
from product_url_v2.models import BrowserEvidence, CandidateAssessment, GateStatus
from product_url_v2.policy import browser_precheck, browser_rank


@dataclass(slots=True)
class BrowserClient:
    """Open candidate URLs directly with local Playwright.

    The notebook runtime does not call a browser microservice and does not alter
    the Jupyter event loop. When a notebook event loop is already active, the
    asynchronous Playwright work runs in one isolated worker thread.
    """

    config: BrowserConfig
    artifact_root: Path

    @classmethod
    def from_env(cls, config: BrowserConfig) -> "BrowserClient":
        root = Path(os.getenv("PRODUCT_URL_ARTIFACT_ROOT") or "data/artifacts")
        return cls(config=config, artifact_root=root)

    def investigate(self, url: str, row_id: str, candidate_id: str) -> BrowserEvidence:
        if not self.config.enabled:
            return BrowserEvidence(url=url, access=GateStatus.NOT_ASSESSED, error="browser disabled")

        coroutine = self._investigate(url, row_id, candidate_id)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        # Jupyter owns the main-thread event loop. The worker thread runs
        # Playwright with an independent event loop and leaves Jupyter untouched.
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="product-browser") as executor:
            return executor.submit(asyncio.run, coroutine).result()

    async def _investigate(self, url: str, row_id: str, candidate_id: str) -> BrowserEvidence:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return BrowserEvidence(url=url, access=GateStatus.FAIL, error="absolute HTTP(S) URL required")

        screenshot_dir = self.artifact_root / row_id / "browser"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{candidate_id}.png"

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                try:
                    context = await browser.new_context(
                        viewport={"width": 1440, "height": 1100},
                        locale="en-US",
                    )
                    page = await context.new_page()
                    page.set_default_timeout(min(self.config.timeout_seconds * 1000, 30_000))
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.config.timeout_seconds * 1000,
                    )
                    try:
                        await page.wait_for_load_state("networkidle", timeout=8_000)
                    except Exception:
                        pass

                    final_url = page.url
                    title = " ".join((await page.title()).split())
                    visible_text = " ".join((await page.locator("body").inner_text()).split())[:200_000]
                    controls = await _product_controls(page)
                    status_code = response.status if response is not None else None
                    error = _render_error(status_code, title, visible_text)

                    rendered_screenshot = ""
                    try:
                        await page.screenshot(path=str(screenshot_path), full_page=True)
                        rendered_screenshot = str(screenshot_path)
                    except Exception:
                        rendered_screenshot = ""

                    return BrowserEvidence(
                        url=url,
                        access=GateStatus.FAIL if error else GateStatus.PASS,
                        final_url=final_url,
                        title=title,
                        visible_text=visible_text,
                        screenshot_path=rendered_screenshot,
                        product_controls=tuple(controls),
                        error=error,
                    )
                finally:
                    await browser.close()
        except Exception as exc:
            return BrowserEvidence(
                url=url,
                access=GateStatus.FAIL,
                error=f"{type(exc).__name__}: {exc}",
            )


def select_browser_candidates(
    candidates: Sequence[CandidateAssessment],
    limit: int,
) -> tuple[CandidateAssessment, ...]:
    if limit <= 0:
        return ()
    eligible = [candidate for candidate in candidates if browser_precheck(candidate)]
    return tuple(sorted(eligible, key=browser_rank, reverse=True)[:limit])


async def _product_controls(page: Page) -> list[str]:
    selectors = (
        "button",
        "[role=button]",
        "input[type=submit]",
        "select",
        "[itemprop=price]",
        "[itemprop=isbn]",
        "[itemprop=gtin13]",
        "[data-testid*=cart]",
        "[class*=price]",
        "[class*=stock]",
        "[class*=product]",
    )
    values: list[str] = []
    for selector in selectors:
        try:
            nodes = page.locator(selector)
            count = min(await nodes.count(), 40)
            for index in range(count):
                text = " ".join((await nodes.nth(index).inner_text()).split())
                if text and re.search(
                    r"cart|basket|buy|price|stock|variant|format|isbn|ean|gtin|product|size|color|quantity|"
                    r"warenkorb|kaufen|produkt|prix|acheter",
                    text,
                    flags=re.I,
                ):
                    values.append(text[:300])
        except Exception:
            continue
    return list(dict.fromkeys(values))[:30]


def _render_error(http_status: int | None, title: str, text: str) -> str:
    if http_status is not None and http_status >= 400:
        return f"Rendered navigation returned HTTP {http_status}."
    if len(text) < 80:
        return "Rendered page did not expose enough visible product text."
    surface = f"{title} {text[:1000]}"
    if re.search(
        r"\b404\b|page not found|seite nicht gefunden|access denied|forbidden|service unavailable",
        surface,
        flags=re.I,
    ):
        return "Rendered page appears to be an error or access-denied surface."
    return ""
