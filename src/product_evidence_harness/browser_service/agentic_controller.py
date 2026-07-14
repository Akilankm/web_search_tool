from __future__ import annotations

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.product_evidence_harness.agentic_browser_contracts import (
    AgenticBrowserAction,
    AgenticBrowserActionType,
    AgenticBrowserElement,
    AgenticBrowserImage,
    AgenticBrowserObservation,
)
from src.product_evidence_harness.browser_contracts import (
    AcquisitionMethod,
    BrowserActionRecord,
    BrowserEvidenceBundle,
    BrowserEvidenceRequest,
    BrowserEvidenceStatus,
    VisualAsset,
)
from src.product_evidence_harness.browser_service.controller import BrowserEvidenceController


@dataclass
class _AgenticSession:
    session_id: str
    request: BrowserEvidenceRequest
    root: Path
    context: Any
    page: Any
    actions: list[BrowserActionRecord] = field(default_factory=list)
    assets: list[VisualAsset] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    closed: bool = False


class AgenticBrowserController:
    """Stateful, allow-listed browser tools used by the LLM planning loop.

    The LLM never receives Playwright access. It can only act on element IDs that
    were emitted by the latest observation and it cannot type, upload, execute
    JavaScript, supply credentials, purchase, or navigate to an invented URL.
    """

    def __init__(self, base: BrowserEvidenceController) -> None:
        self.base = base
        self._sessions: dict[str, _AgenticSession] = {}
        self._lock = asyncio.Lock()

    async def health(self) -> dict[str, Any]:
        base = await self.base.health()
        return {**base, "agentic_sessions": len(self._sessions), "agentic_tools": True}

    async def start(self, request: BrowserEvidenceRequest) -> AgenticBrowserObservation:
        await self.base.start()
        await self.base._semaphore.acquire()
        session_id = uuid.uuid4().hex
        root = self.base.config.artifact_root / request.job_id / request.candidate_id / "agentic"
        root.mkdir(parents=True, exist_ok=True)
        context = await self.base._browser.new_context(
            viewport={
                "width": self.base.config.viewport_width,
                "height": self.base.config.viewport_height,
            },
            locale=self.base._locale(request),
            accept_downloads=False,
        )
        page = await context.new_page()
        page.set_default_timeout(self.base.config.action_timeout_ms)
        page.set_default_navigation_timeout(self.base.config.navigation_timeout_ms)
        session = _AgenticSession(
            session_id=session_id,
            request=request,
            root=root,
            context=context,
            page=page,
        )
        async with self._lock:
            self._sessions[session_id] = session
        try:
            before = request.url
            response = await page.goto(request.url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)
            session.actions.append(
                self.base._action(session.actions, "OPEN_PAGE", request.url, "SUCCESS", before, page.url)
            )
            status_code = response.status if response is not None else None
            if status_code is not None and status_code >= 400:
                session.warnings.append(f"HTTP_STATUS_{status_code}")
            return await self.observe(session_id)
        except Exception:
            await self.abort(session_id)
            raise

    async def observe(self, session_id: str) -> AgenticBrowserObservation:
        session = self._session(session_id)
        page = session.page
        visible_text = await self.base._safe_body_text(page)
        lowered = visible_text.lower()
        session.blockers.extend(
            term for term in self.base.BLOCKER_TERMS if term in lowered
        )
        session.blockers[:] = list(dict.fromkeys(session.blockers))
        title = await page.title()
        visible_name = await self.base._visible_product_name(page)
        interactive = await self._interactive_elements(page)
        images = await self._images(page)
        observation_index = len(list((session.root / "observations").glob("OBS-*.png")))
        screenshot_path = session.root / "observations" / f"OBS-{observation_index:03d}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await page.screenshot(path=str(screenshot_path), full_page=False)
            screenshot_value: str | None = str(screenshot_path)
        except Exception as exc:
            session.warnings.append(f"OBSERVATION_SCREENSHOT_FAILED:{type(exc).__name__}")
            screenshot_value = None
        terminal = bool(
            session.blockers
            or len(session.actions) >= session.request.intent.maximum_actions
        )
        observation = AgenticBrowserObservation(
            session_id=session.session_id,
            candidate_id=session.request.candidate_id,
            url=page.url,
            title=title,
            visible_product_name=visible_name,
            visible_text=visible_text[:12_000],
            interactive_elements=tuple(interactive),
            images=tuple(images),
            blockers=tuple(session.blockers),
            warnings=tuple(dict.fromkeys(session.warnings)),
            action_count=len(session.actions),
            maximum_actions=session.request.intent.maximum_actions,
            screenshot_path=screenshot_value,
            terminal=terminal,
        )
        self._write_json(session.root / "latest_observation.json", observation.to_dict())
        return observation

    async def act(self, action: AgenticBrowserAction) -> AgenticBrowserObservation:
        session = self._session(action.session_id)
        if len(session.actions) >= session.request.intent.maximum_actions:
            session.warnings.append("MAXIMUM_ACTIONS_REACHED")
            return await self.observe(action.session_id)
        page = session.page
        before = page.url
        result = "SUCCESS"
        detail = action.reason[:500]
        target = action.element_id or action.direction or action.action.value
        try:
            if action.action is AgenticBrowserActionType.CLICK:
                if not action.element_id or not re.fullmatch(r"E\d{3}", action.element_id):
                    raise ValueError("click requires an observed E### element_id")
                locator = page.locator(f'[data-agentic-id="{action.element_id}"]')
                if await locator.count() != 1 or not await locator.first.is_visible():
                    raise ValueError("element is not available in the current observation")
                await locator.first.click(timeout=self.base.config.action_timeout_ms)
                await page.wait_for_timeout(700)
            elif action.action is AgenticBrowserActionType.SCROLL:
                direction = (action.direction or "down").strip().lower()
                if direction not in {"up", "down", "top", "bottom"}:
                    raise ValueError("scroll direction must be up, down, top, or bottom")
                script = {
                    "up": "window.scrollBy(0, -window.innerHeight * 0.8)",
                    "down": "window.scrollBy(0, window.innerHeight * 0.8)",
                    "top": "window.scrollTo(0, 0)",
                    "bottom": "window.scrollTo(0, document.body.scrollHeight)",
                }[direction]
                await page.evaluate(script)
                await page.wait_for_timeout(450)
            elif action.action is AgenticBrowserActionType.INSPECT_IMAGE:
                if not action.element_id or not re.fullmatch(r"I\d{3}", action.element_id):
                    raise ValueError("inspect_image requires an observed I### element_id")
                locator = page.locator(f'[data-agentic-image-id="{action.element_id}"]')
                if await locator.count() != 1 or not await locator.first.is_visible():
                    raise ValueError("image is not available in the current observation")
                image_dir = session.root / "images"
                image_dir.mkdir(parents=True, exist_ok=True)
                path = image_dir / f"{action.element_id}.png"
                await locator.first.screenshot(path=str(path))
                session.assets.append(
                    self.base._asset_from_file(
                        request=session.request,
                        asset_id=action.element_id,
                        path=path,
                        method=AcquisitionMethod.BROWSER_ELEMENT_SCREENSHOT,
                        browser_action="LLM_INSPECT_IMAGE",
                        element_description=detail or "Image selected by the LLM investigator",
                        mime_type="image/png",
                        validated=True,
                    )
                )
            elif action.action is AgenticBrowserActionType.CAPTURE_SCREENSHOT:
                screenshot_dir = session.root / "screenshots"
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                path = screenshot_dir / f"ACTION-{len(session.actions) + 1:03d}.png"
                await page.screenshot(path=str(path), full_page=False)
                session.assets.append(
                    self.base._asset_from_file(
                        request=session.request,
                        asset_id=f"ACTION-{len(session.actions) + 1:03d}",
                        path=path,
                        method=AcquisitionMethod.BROWSER_VIEWPORT_SCREENSHOT,
                        browser_action="LLM_CAPTURE_SCREENSHOT",
                        element_description=detail or "Viewport selected by the LLM investigator",
                        mime_type="image/png",
                        validated=True,
                    )
                )
            elif action.action is AgenticBrowserActionType.FINISH:
                return await self.observe(action.session_id)
            else:
                raise ValueError(f"unsupported action: {action.action.value}")
            if urlparse(page.url).scheme not in {"http", "https"}:
                raise ValueError("browser action left the permitted HTTP(S) context")
        except Exception as exc:
            result = "FAILED"
            detail = f"{type(exc).__name__}: {exc}"
            session.warnings.append(f"ACTION_FAILED:{action.action.value}:{type(exc).__name__}")
        session.actions.append(
            BrowserActionRecord(
                step=len(session.actions) + 1,
                action=f"LLM_{action.action.value.upper()}",
                target=target,
                result=result,
                detail=detail,
                url_before=before,
                url_after=page.url,
            )
        )
        return await self.observe(action.session_id)

    async def finish(self, session_id: str) -> BrowserEvidenceBundle:
        session = self._session(session_id)
        page = session.page
        text = await self.base._safe_body_text(page)
        related = self.base._identity_related(
            session.request,
            " ".join(
                [
                    await page.title(),
                    await self.base._visible_product_name(page),
                    text[:6000],
                ]
            ),
        )
        product_like = await self.base._looks_product_like(page, text)
        rendered_product_verified = bool(related and product_like and not session.blockers)
        status = (
            BrowserEvidenceStatus.ACCESS_BLOCKED
            if session.blockers
            else BrowserEvidenceStatus.COMPLETED
            if rendered_product_verified
            else BrowserEvidenceStatus.PARTIAL
        )
        try:
            bundle = await self.base._finalize(
                request=session.request,
                root=session.root,
                page=page,
                actions=session.actions,
                assets=self.base._dedupe_assets(session.assets),
                blockers=session.blockers,
                warnings=session.warnings,
                status=status,
                rendered_product_verified=rendered_product_verified,
                error=("Rendered page contains an access blocker." if session.blockers else None),
                gallery_discovered=bool(session.assets),
            )
            return bundle
        finally:
            await self._close(session)

    async def abort(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            await self._close(session)

    def _session(self, session_id: str) -> _AgenticSession:
        session = self._sessions.get(session_id)
        if session is None or session.closed:
            raise KeyError(session_id)
        return session

    async def _close(self, session: _AgenticSession) -> None:
        if session.closed:
            return
        session.closed = True
        try:
            await session.context.close()
        finally:
            async with self._lock:
                self._sessions.pop(session.session_id, None)
            self.base._semaphore.release()

    async def _interactive_elements(self, page: Any) -> list[AgenticBrowserElement]:
        payload = await page.evaluate(
            """
            () => {
              const nodes = [...document.querySelectorAll(
                'button,a,[role="button"],[role="tab"],summary,input[type="button"],input[type="submit"]'
              )];
              const visible = nodes.filter(node => {
                const r = node.getBoundingClientRect();
                const s = getComputedStyle(node);
                return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none';
              }).slice(0, 80);
              return visible.map((node, index) => {
                const id = `E${String(index + 1).padStart(3, '0')}`;
                node.setAttribute('data-agentic-id', id);
                return {
                  element_id: id,
                  role: node.getAttribute('role') || node.tagName.toLowerCase(),
                  text: (node.innerText || node.getAttribute('aria-label') || node.value || '').trim().slice(0, 180),
                  tag: node.tagName.toLowerCase(),
                  href: node.href || null,
                };
              });
            }
            """
        )
        return [AgenticBrowserElement.from_mapping(item) for item in payload]

    async def _images(self, page: Any) -> list[AgenticBrowserImage]:
        payload = await page.evaluate(
            """
            () => {
              const nodes = [...document.querySelectorAll('img')].filter(node => {
                const r = node.getBoundingClientRect();
                return r.width >= 120 && r.height >= 120;
              }).slice(0, 40);
              return nodes.map((node, index) => {
                const id = `I${String(index + 1).padStart(3, '0')}`;
                node.setAttribute('data-agentic-image-id', id);
                return {
                  asset_id: id,
                  element_id: id,
                  alt: (node.alt || '').trim().slice(0, 180),
                  src: node.currentSrc || node.src || '',
                  width: Math.round(node.getBoundingClientRect().width),
                  height: Math.round(node.getBoundingClientRect().height),
                };
              });
            }
            """
        )
        return [AgenticBrowserImage.from_mapping(item) for item in payload]

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
