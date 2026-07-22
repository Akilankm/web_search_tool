from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright

app = FastAPI(title="Product URL Browser", version="1.0.2")
ARTIFACT_ROOT = Path(os.getenv("PRODUCT_URL_ARTIFACT_ROOT") or "/data/artifacts")
API_TOKEN = str(os.getenv("BROWSER_API_TOKEN") or "").strip()
if not API_TOKEN:
    token_file = str(os.getenv("BROWSER_API_TOKEN_FILE") or "").strip()
    if token_file and Path(token_file).is_file():
        API_TOKEN = Path(token_file).read_text(encoding="utf-8").strip()


class InvestigationRequest(BaseModel):
    url: str
    row_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    candidate_id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "healthy", "runtime_contract": "product-url-browser-v1", "version": "1.0.2"}


@app.post("/investigate")
async def investigate(payload: InvestigationRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _authorize(authorization)
    parsed = urlparse(payload.url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="absolute HTTP(S) URL required")
    screenshot_dir = ARTIFACT_ROOT / payload.row_id / "browser"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshot_dir / f"{payload.candidate_id}.png"
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(viewport={"width": 1440, "height": 1100}, locale="en-US")
            page = await context.new_page()
            page.set_default_timeout(int(os.getenv("BROWSER_ACTION_TIMEOUT_MS") or 10000))
            await page.goto(payload.url, wait_until="domcontentloaded", timeout=int(os.getenv("BROWSER_NAVIGATION_TIMEOUT_MS") or 60000))
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            final_url = page.url
            title = await page.title()
            text = " ".join((await page.locator("body").inner_text()).split())[:200000]
            controls = await _product_controls(page)
            await page.screenshot(path=str(screenshot_path), full_page=True)
            await context.close()
            await browser.close()
            return {
                "access": "PASS",
                "final_url": final_url,
                "title": title,
                "visible_text": text,
                "product_controls": controls,
                "screenshot_path": str(screenshot_path),
                "error": "",
            }
    except Exception as exc:
        return {
            "access": "FAIL",
            "final_url": "",
            "title": "",
            "visible_text": "",
            "product_controls": [],
            "screenshot_path": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _product_controls(page) -> list[str]:
    selectors = [
        "button", "[role=button]", "input[type=submit]", "select", "[itemprop=price]",
        "[data-testid*=cart]", "[class*=price]", "[class*=stock]",
    ]
    values: list[str] = []
    for selector in selectors:
        try:
            nodes = page.locator(selector)
            count = min(await nodes.count(), 40)
            for index in range(count):
                text = " ".join((await nodes.nth(index).inner_text()).split())
                if text and re.search(r"cart|basket|buy|price|stock|variant|size|color|quantity|warenkorb|kaufen|prix|acheter", text, flags=re.I):
                    values.append(text[:200])
        except Exception:
            continue
    return list(dict.fromkeys(values))[:30]


def _authorize(value: str | None) -> None:
    if not API_TOKEN:
        return
    if value != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="invalid browser token")
