from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.product_evidence_harness.browser_contracts import (
    AcquisitionMethod,
    BrowserActionRecord,
    BrowserEvidenceBundle,
    BrowserEvidenceRequest,
    BrowserEvidenceStatus,
    VisualAsset,
)


@dataclass(frozen=True, slots=True)
class BrowserRuntimeConfig:
    artifact_root: Path = Path("/data/artifacts")
    headless: bool = True
    navigation_timeout_ms: int = 60_000
    action_timeout_ms: int = 8_000
    max_contexts: int = 3
    viewport_width: int = 1440
    viewport_height: int = 1100
    minimum_image_width: int = 240
    minimum_image_height: int = 240
    maximum_asset_bytes: int = 12 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "BrowserRuntimeConfig":
        return cls(
            artifact_root=Path(os.getenv("ARTIFACT_ROOT", "/data/artifacts")),
            headless=os.getenv("BROWSER_HEADLESS", "true").strip().lower() in {"1", "true", "yes", "on"},
            navigation_timeout_ms=int(os.getenv("BROWSER_NAVIGATION_TIMEOUT_MS", "60000")),
            action_timeout_ms=int(os.getenv("BROWSER_ACTION_TIMEOUT_MS", "8000")),
            max_contexts=max(1, int(os.getenv("BROWSER_MAX_CONTEXTS", "3"))),
            viewport_width=int(os.getenv("BROWSER_VIEWPORT_WIDTH", "1440")),
            viewport_height=int(os.getenv("BROWSER_VIEWPORT_HEIGHT", "1100")),
            minimum_image_width=int(os.getenv("BROWSER_MIN_IMAGE_WIDTH", "240")),
            minimum_image_height=int(os.getenv("BROWSER_MIN_IMAGE_HEIGHT", "240")),
            maximum_asset_bytes=int(os.getenv("BROWSER_MAX_ASSET_BYTES", str(12 * 1024 * 1024))),
        )


class BrowserEvidenceController:
    """Render and interact with one candidate URL inside an isolated browser context."""

    SAFE_SECTION_TERMS = (
        "product details", "details", "specifications", "technical details", "more information",
        "description", "materials", "dimensions", "package contents", "manufacturer",
        "safety", "warnings", "downloads", "instructions", "show more", "read more",
        "produktdetails", "technische daten", "mehr anzeigen", "beschreibung", "warnhinweise",
        "caractéristiques", "détails", "plus d'informations", "sécurité",
    )
    SAFE_OVERLAY_TERMS = (
        "accept all", "accept", "allow all", "continue", "agree", "close", "no thanks",
        "alle akzeptieren", "akzeptieren", "weiter", "schließen", "tout accepter", "continuer",
    )
    BLOCKER_TERMS = (
        "verify you are human", "captcha", "access denied", "bot detection", "unusual traffic",
        "sign in to continue", "login required", "forbidden",
    )

    def __init__(self, config: BrowserRuntimeConfig | None = None) -> None:
        self.config = config or BrowserRuntimeConfig.from_env()
        self.config.artifact_root.mkdir(parents=True, exist_ok=True)
        self._playwright: Any = None
        self._browser: Any = None
        self._semaphore = asyncio.Semaphore(self.config.max_contexts)

    async def start(self) -> None:
        if self._browser is not None:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            args=["--disable-dev-shm-usage", "--no-first-run", "--disable-background-networking"],
        )

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def health(self) -> dict[str, Any]:
        await self.start()
        return {"status": "healthy", "browser": "chromium", "max_contexts": self.config.max_contexts}

    async def acquire(self, request: BrowserEvidenceRequest) -> BrowserEvidenceBundle:
        async with self._semaphore:
            await self.start()
            return await self._acquire_locked(request)

    async def _acquire_locked(self, request: BrowserEvidenceRequest) -> BrowserEvidenceBundle:
        root = self.config.artifact_root / request.job_id / request.candidate_id / "browser"
        image_dir = root / "images"
        screenshot_dir = root / "screenshots"
        image_dir.mkdir(parents=True, exist_ok=True)
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        actions: list[BrowserActionRecord] = []
        assets: list[VisualAsset] = []
        blockers: list[str] = []
        warnings: list[str] = []
        context = await self._browser.new_context(
            viewport={"width": self.config.viewport_width, "height": self.config.viewport_height},
            locale=self._locale(request),
            accept_downloads=False,
        )
        page = await context.new_page()
        page.set_default_timeout(self.config.action_timeout_ms)
        page.set_default_navigation_timeout(self.config.navigation_timeout_ms)

        try:
            before = request.url
            response = await page.goto(request.url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1200)
            actions.append(self._action(actions, "OPEN_PAGE", request.url, "SUCCESS", before, page.url))
            status_code = response.status if response is not None else None
            if status_code is not None and status_code >= 400:
                warnings.append(f"HTTP_STATUS_{status_code}")

            body_text = await self._safe_body_text(page)
            blockers.extend(term for term in self.BLOCKER_TERMS if term in body_text.lower())
            if blockers:
                return await self._finalize(
                    request=request, root=root, page=page, actions=actions, assets=assets,
                    blockers=blockers, warnings=warnings, status=BrowserEvidenceStatus.ACCESS_BLOCKED,
                    rendered_product_verified=False, error="Rendered page contains an access blocker.",
                )

            await self._dismiss_overlays(page, actions, request.intent.maximum_actions)
            await self._expand_sections(page, actions, request.intent.maximum_actions)
            await self._scroll_for_lazy_content(page, actions, request.intent.maximum_actions)

            title = await page.title()
            visible_name = await self._visible_product_name(page)
            rendered_text = await self._safe_body_text(page)
            related = self._identity_related(request, " ".join([title, visible_name, rendered_text[:6000]]))
            product_like = await self._looks_product_like(page, rendered_text)
            rendered_product_verified = bool(related and product_like)

            image_urls = await self._discover_image_urls(page)
            gallery_discovered = bool(image_urls)
            if request.intent.download_images:
                for index, image_url in enumerate(image_urls[: request.intent.maximum_images], start=1):
                    asset = await self._download_image(context, request, image_url, image_dir, index)
                    if asset is not None:
                        assets.append(asset)

            if request.intent.collect_gallery and len(assets) < request.intent.maximum_images:
                clicked = await self._capture_gallery_states(
                    page, request, screenshot_dir, assets, actions,
                    max_assets=request.intent.maximum_images,
                    max_screenshots=request.intent.maximum_screenshots,
                )
                gallery_discovered = gallery_discovered or clicked

            if request.intent.capture_screenshot_fallbacks and not any(asset.vision_ready for asset in assets):
                fallback = await self._capture_primary_visual(page, request, screenshot_dir, len(assets) + 1)
                if fallback is not None:
                    assets.append(fallback)

            if request.intent.capture_full_page_audit and len([a for a in assets if "SCREENSHOT" in a.acquisition_method.value]) < request.intent.maximum_screenshots:
                path = screenshot_dir / "full-page-audit.png"
                await page.screenshot(path=str(path), full_page=True)
                assets.append(self._asset_from_file(
                    request=request,
                    asset_id="AUDIT-FULL-PAGE",
                    path=path,
                    method=AcquisitionMethod.BROWSER_FULL_PAGE_SCREENSHOT,
                    element_description="Full rendered page for audit",
                    validated=True,
                ))

            return await self._finalize(
                request=request,
                root=root,
                page=page,
                actions=actions,
                assets=self._dedupe_assets(assets),
                blockers=blockers,
                warnings=warnings,
                status=BrowserEvidenceStatus.COMPLETED if rendered_product_verified else BrowserEvidenceStatus.PARTIAL,
                rendered_product_verified=rendered_product_verified,
                error=None,
                gallery_discovered=gallery_discovered,
            )
        except Exception as exc:
            return await self._finalize(
                request=request, root=root, page=page, actions=actions, assets=assets,
                blockers=blockers, warnings=warnings, status=BrowserEvidenceStatus.FAILED,
                rendered_product_verified=False, error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            await context.close()

    async def _dismiss_overlays(self, page: Any, actions: list[BrowserActionRecord], maximum_actions: int) -> None:
        for term in self.SAFE_OVERLAY_TERMS:
            if len(actions) >= maximum_actions:
                return
            locator = page.get_by_role("button", name=re.compile(re.escape(term), re.I))
            try:
                if await locator.count() and await locator.first.is_visible():
                    before = page.url
                    await locator.first.click(timeout=1500)
                    await page.wait_for_timeout(250)
                    actions.append(self._action(actions, "DISMISS_OVERLAY", term, "SUCCESS", before, page.url))
            except Exception:
                continue

    async def _expand_sections(self, page: Any, actions: list[BrowserActionRecord], maximum_actions: int) -> None:
        for term in self.SAFE_SECTION_TERMS:
            if len(actions) >= maximum_actions:
                return
            for role in ("button", "tab", "link"):
                locator = page.get_by_role(role, name=re.compile(re.escape(term), re.I))
                try:
                    count = min(await locator.count(), 2)
                    for index in range(count):
                        target = locator.nth(index)
                        if await target.is_visible():
                            before = page.url
                            await target.click(timeout=1800)
                            await page.wait_for_timeout(220)
                            actions.append(self._action(actions, "EXPAND_SECTION", term, "SUCCESS", before, page.url))
                            if len(actions) >= maximum_actions:
                                return
                except Exception:
                    continue

    async def _scroll_for_lazy_content(self, page: Any, actions: list[BrowserActionRecord], maximum_actions: int) -> None:
        if len(actions) >= maximum_actions:
            return
        for ratio in (0.35, 0.7, 1.0):
            await page.evaluate("ratio => window.scrollTo(0, document.body.scrollHeight * ratio)", ratio)
            await page.wait_for_timeout(250)
        await page.evaluate("window.scrollTo(0, 0)")
        actions.append(self._action(actions, "SCROLL_LAZY_CONTENT", "document", "SUCCESS", page.url, page.url))

    async def _discover_image_urls(self, page: Any) -> list[str]:
        urls = await page.evaluate(
            """
            () => {
              const out = [];
              const add = (value) => {
                if (!value || typeof value !== 'string') return;
                value.split(',').forEach(part => {
                  const candidate = part.trim().split(' ')[0];
                  if (candidate && !candidate.startsWith('data:')) out.push(candidate);
                });
              };
              document.querySelectorAll('img').forEach(img => {
                ['src','data-src','data-lazy-src','data-zoom-image'].forEach(k => add(img.getAttribute(k)));
                add(img.getAttribute('srcset'));
                add(img.currentSrc);
              });
              document.querySelectorAll('source').forEach(source => add(source.getAttribute('srcset')));
              const og = document.querySelector('meta[property="og:image"]');
              if (og) add(og.content);
              return [...new Set(out.map(u => { try { return new URL(u, location.href).href; } catch { return null; } }).filter(Boolean))];
            }
            """
        )
        return [url for url in urls if self._allowed_asset_url(page.url, url)]

    async def _download_image(self, context: Any, request: BrowserEvidenceRequest, image_url: str, image_dir: Path, index: int) -> VisualAsset | None:
        try:
            response = await context.request.get(image_url, headers={"Referer": request.url}, timeout=20_000)
            if not response.ok:
                return None
            body = await response.body()
            if not body or len(body) > self.config.maximum_asset_bytes:
                return None
            content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            if not content_type.startswith("image/"):
                return None
            extension = mimetypes.guess_extension(content_type) or ".img"
            path = image_dir / f"IMG-{index:03d}{extension}"
            path.write_bytes(body)
            width, height = self._image_dimensions(path)
            if width and height and (width < self.config.minimum_image_width or height < self.config.minimum_image_height):
                path.unlink(missing_ok=True)
                return None
            return self._asset_from_file(
                request=request,
                asset_id=f"IMG-{index:03d}",
                path=path,
                method=AcquisitionMethod.BROWSER_CONTEXT_DOWNLOAD,
                source_image_url=image_url,
                mime_type=content_type,
                validated=True,
            )
        except Exception:
            return None

    async def _capture_gallery_states(
        self,
        page: Any,
        request: BrowserEvidenceRequest,
        screenshot_dir: Path,
        assets: list[VisualAsset],
        actions: list[BrowserActionRecord],
        *,
        max_assets: int,
        max_screenshots: int,
    ) -> bool:
        selectors = [
            '[role="button"] img',
            'button img',
            '[class*="thumbnail" i] img',
            '[class*="gallery" i] img',
            '[class*="carousel" i] img',
        ]
        seen = 0
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = min(await locator.count(), max_screenshots)
            except Exception:
                continue
            for index in range(count):
                if len(assets) >= max_assets or seen >= max_screenshots:
                    return seen > 0
                item = locator.nth(index)
                try:
                    if not await item.is_visible():
                        continue
                    before = page.url
                    await item.click(timeout=1500)
                    await page.wait_for_timeout(300)
                    path = screenshot_dir / f"SHOT-GALLERY-{seen + 1:03d}.png"
                    primary = await self._primary_image_locator(page)
                    if primary is not None:
                        await primary.screenshot(path=str(path))
                        method = AcquisitionMethod.BROWSER_ELEMENT_SCREENSHOT
                        description = "Rendered product gallery image"
                    else:
                        await page.screenshot(path=str(path), full_page=False)
                        method = AcquisitionMethod.BROWSER_VIEWPORT_SCREENSHOT
                        description = "Rendered viewport after gallery interaction"
                    asset = self._asset_from_file(
                        request=request,
                        asset_id=f"SHOT-{seen + 1:03d}",
                        path=path,
                        method=method,
                        browser_action=f"clicked gallery element {index + 1}",
                        element_description=description,
                        validated=True,
                    )
                    assets.append(asset)
                    actions.append(self._action(actions, "CLICK_GALLERY", f"{selector}[{index}]", "SUCCESS", before, page.url, (asset.asset_id,)))
                    seen += 1
                except Exception:
                    continue
        return seen > 0

    async def _capture_primary_visual(self, page: Any, request: BrowserEvidenceRequest, screenshot_dir: Path, index: int) -> VisualAsset | None:
        try:
            locator = await self._primary_image_locator(page)
            path = screenshot_dir / f"SHOT-FALLBACK-{index:03d}.png"
            if locator is not None:
                await locator.screenshot(path=str(path))
                method = AcquisitionMethod.BROWSER_ELEMENT_SCREENSHOT
                description = "Primary visible product image"
            else:
                await page.screenshot(path=str(path), full_page=False)
                method = AcquisitionMethod.BROWSER_VIEWPORT_SCREENSHOT
                description = "Visible rendered product page"
            return self._asset_from_file(
                request=request,
                asset_id=f"SHOT-{index:03d}",
                path=path,
                method=method,
                element_description=description,
                validated=True,
            )
        except Exception:
            return None

    async def _primary_image_locator(self, page: Any) -> Any | None:
        candidates = page.locator('main img, [class*="product" i] img, [class*="gallery" i] img, img')
        try:
            count = min(await candidates.count(), 50)
        except Exception:
            return None
        best = None
        best_area = 0
        for index in range(count):
            item = candidates.nth(index)
            try:
                box = await item.bounding_box()
                if not box or not await item.is_visible():
                    continue
                area = int(box["width"] * box["height"])
                if area > best_area and box["width"] >= self.config.minimum_image_width and box["height"] >= self.config.minimum_image_height:
                    best = item
                    best_area = area
            except Exception:
                continue
        return best

    async def _visible_product_name(self, page: Any) -> str:
        for selector in ('h1', '[itemprop="name"]', '[class*="product-title" i]', '[class*="product-name" i]'):
            locator = page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible():
                    text = (await locator.inner_text()).strip()
                    if text:
                        return text[:500]
            except Exception:
                continue
        return ""

    async def _safe_body_text(self, page: Any) -> str:
        try:
            return (await page.locator("body").inner_text(timeout=5000))[:80_000]
        except Exception:
            return ""

    async def _looks_product_like(self, page: Any, text: str) -> bool:
        signals = 0
        signals += 1 if await page.locator('h1').count() else 0
        signals += 1 if await page.locator('img').count() else 0
        signals += 1 if re.search(r'\b(price|add to cart|availability|in stock|specifications|details|preis|warenkorb)\b', text, re.I) else 0
        signals += 1 if await page.locator('script[type="application/ld+json"]').count() else 0
        return signals >= 2

    def _identity_related(self, request: BrowserEvidenceRequest, text: str) -> bool:
        folded = re.sub(r"\s+", " ", text.lower())
        tokens = [token for token in re.findall(r"[a-z0-9]+", request.product_identity.main_text.lower()) if len(token) > 2]
        overlap = sum(1 for token in dict.fromkeys(tokens) if token in folded) / max(1, len(set(tokens)))
        ean_match = bool(request.product_identity.ean and request.product_identity.ean in re.sub(r"\D", "", text))
        return bool(ean_match or overlap >= 0.45)

    def _locale(self, request: BrowserEvidenceRequest) -> str:
        language = (request.product_identity.language_code or "en").lower()
        country = request.product_identity.country_code.upper()
        return f"{language}-{country}" if len(country) == 2 else language

    def _allowed_asset_url(self, page_url: str, asset_url: str) -> bool:
        parsed = urlparse(asset_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        lowered = asset_url.lower()
        if any(token in lowered for token in ("logo", "icon", "sprite", "avatar", "tracking", "pixel")):
            return False
        return True

    def _asset_from_file(
        self,
        *,
        request: BrowserEvidenceRequest,
        asset_id: str,
        path: Path,
        method: AcquisitionMethod,
        source_image_url: str | None = None,
        browser_action: str = "",
        element_description: str = "",
        mime_type: str = "",
        validated: bool,
    ) -> VisualAsset:
        data = path.read_bytes()
        width, height = self._image_dimensions(path)
        return VisualAsset(
            asset_id=asset_id,
            source_page_url=request.url,
            source_image_url=source_image_url,
            local_path=str(path),
            acquisition_method=method,
            browser_action=browser_action,
            element_description=element_description,
            mime_type=mime_type,
            width=width,
            height=height,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            validated=validated,
            vision_ready=bool(validated and len(data) > 0),
        )

    def _image_dimensions(self, path: Path) -> tuple[int, int]:
        try:
            from PIL import Image

            with Image.open(path) as image:
                return int(image.width), int(image.height)
        except Exception:
            return 0, 0

    def _dedupe_assets(self, assets: list[VisualAsset]) -> list[VisualAsset]:
        seen: set[str] = set()
        result: list[VisualAsset] = []
        for asset in assets:
            key = asset.sha256 or asset.local_path
            if key in seen:
                continue
            seen.add(key)
            result.append(asset)
        return result

    async def _finalize(
        self,
        *,
        request: BrowserEvidenceRequest,
        root: Path,
        page: Any,
        actions: list[BrowserActionRecord],
        assets: list[VisualAsset],
        blockers: list[str],
        warnings: list[str],
        status: BrowserEvidenceStatus,
        rendered_product_verified: bool,
        error: str | None,
        gallery_discovered: bool = False,
    ) -> BrowserEvidenceBundle:
        try:
            rendered_text = await self._safe_body_text(page)
            title = await page.title()
            visible_name = await self._visible_product_name(page)
            final_url = page.url
            html = await page.content()
        except Exception:
            rendered_text, title, visible_name, html = "", "", "", ""
            final_url = request.url

        rendered_text_path = root / "rendered_text.md"
        final_html_path = root / "final_page.html"
        action_trace_path = root / "browser_actions.json"
        visual_manifest_path = root / "visual_manifest.json"
        self._atomic_write_text(rendered_text_path, rendered_text)
        self._atomic_write_text(final_html_path, html)
        self._atomic_write_json(action_trace_path, [action.to_dict() for action in actions])
        self._atomic_write_json(visual_manifest_path, [asset.to_dict() for asset in assets])

        direct_count = sum(1 for asset in assets if asset.acquisition_method in {
            AcquisitionMethod.DIRECT_HTTP_DOWNLOAD,
            AcquisitionMethod.BROWSER_CONTEXT_DOWNLOAD,
            AcquisitionMethod.NETWORK_RESPONSE_CAPTURE,
        })
        screenshot_count = sum(1 for asset in assets if "SCREENSHOT" in asset.acquisition_method.value)
        browser_openable = status not in {BrowserEvidenceStatus.FAILED, BrowserEvidenceStatus.ACCESS_BLOCKED} and bool(rendered_text or html)
        text_scrapable = browser_openable and len(rendered_text.split()) >= 20
        multimodal_scrapable = text_scrapable and any(asset.vision_ready for asset in assets)
        bundle = BrowserEvidenceBundle(
            status=status,
            job_id=request.job_id,
            candidate_id=request.candidate_id,
            requested_url=request.url,
            final_url=final_url,
            browser_openable=browser_openable,
            rendered_product_verified=rendered_product_verified,
            text_scrapable=text_scrapable,
            gallery_discovered=gallery_discovered,
            direct_images_downloaded=direct_count,
            screenshots_captured=screenshot_count,
            multimodal_scrapable=multimodal_scrapable,
            page_title=title,
            visible_product_name=visible_name,
            rendered_text=rendered_text[:30_000],
            rendered_text_path=str(rendered_text_path),
            final_html_path=str(final_html_path),
            action_trace_path=str(action_trace_path),
            visual_manifest_path=str(visual_manifest_path),
            visual_assets=tuple(assets),
            actions=tuple(actions),
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            error=error,
        )
        self._atomic_write_json(root / "browser_result.json", bundle.to_dict())
        return bundle

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _atomic_write_json(path: Path, content: Any) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _action(
        actions: list[BrowserActionRecord],
        action: str,
        target: str,
        result: str,
        url_before: str,
        url_after: str,
        evidence_created: tuple[str, ...] = (),
    ) -> BrowserActionRecord:
        return BrowserActionRecord(
            step=len(actions) + 1,
            action=action,
            target=target,
            result=result,
            url_before=url_before,
            url_after=url_after,
            evidence_created=evidence_created,
        )
