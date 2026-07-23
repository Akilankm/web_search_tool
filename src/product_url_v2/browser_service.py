from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright

VERSION = "1.3.0"
app = FastAPI(title="Exact Product Mapping Browser", version=VERSION)
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
    return {
        "status": "healthy",
        "runtime_contract": "product-url-browser-v1",
        "version": VERSION,
        "validation": ["HTTP success", "rendered body", "final URL", "product controls"],
    }


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
            response = await page.goto(
                payload.url,
                wait_until="domcontentloaded",
                timeout=int(os.getenv("BROWSER_NAVIGATION_TIMEOUT_MS") or 60000),
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            final_url = page.url
            title = " ".join((await page.title()).split())
            text = " ".join((await page.locator("body").inner_text()).split())[:200000]
            controls = await _product_controls(page)
            http_status = response.status if response is not None else None
            await page.screenshot(path=str(screenshot_path), full_page=True)
            await context.close()
            await browser.close()

            error = _render_error(http_status, title, text)
            return {
                "access": "FAIL" if error else "PASS",
                "final_url": final_url,
                "title": title,
                "visible_text": text,
                "product_controls": controls,
                "screenshot_path": str(screenshot_path),
                "http_status": http_status,
                "error": error,
            }
    except Exception as exc:
        return {
            "access": "FAIL",
            "final_url": "",
            "title": "",
            "visible_text": "",
            "product_controls": [],
            "screenshot_path": "",
            "http_status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _product_controls(page) -> list[str]:
    selectors = [
        "button", "[role=button]", "input[type=submit]", "select", "[itemprop=price]",
        "[itemprop=isbn]", "[itemprop=gtin13]", "[data-testid*=cart]", "[class*=price]",
        "[class*=stock]", "[class*=product]",
    ]
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
    error_surface = f"{title} {text[:1000]}"
    if re.search(r"\b404\b|page not found|seite nicht gefunden|access denied|forbidden|service unavailable", error_surface, flags=re.I):
        return "Rendered page appears to be an error or access-denied surface."
    return ""


def _authorize(value: str | None) -> None:
    if not API_TOKEN:
        return
    if value != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="invalid browser token")
