from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from src.product_evidence_harness.agentic_browser_contracts import AgenticBrowserAction
from src.product_evidence_harness.browser_contracts import BrowserEvidenceRequest
from src.product_evidence_harness.browser_service.agentic_controller import AgenticBrowserController
from src.product_evidence_harness.browser_service.controller import BrowserEvidenceController


_controller = BrowserEvidenceController()
_agentic = AgenticBrowserController(_controller)


def _expected_token() -> str:
    token = os.getenv("BROWSER_API_TOKEN", "").strip()
    token_file = os.getenv("BROWSER_API_TOKEN_FILE", "").strip()
    if not token and token_file:
        try:
            token = open(token_file, encoding="utf-8").read().strip()
        except OSError:
            token = ""
    return token


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = _expected_token()
    if not expected:
        raise HTTPException(status_code=503, detail="Browser service token is not configured")
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid browser service token")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _controller.start()
    yield
    await _controller.close()


app = FastAPI(title="Product Browser Evidence Service", version="0.8.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    if not _expected_token():
        raise HTTPException(status_code=503, detail="Browser service token is not configured")
    return await _agentic.health()


@app.post("/v1/evidence/acquire", dependencies=[Depends(require_token)])
async def acquire(payload: dict) -> dict:
    request = BrowserEvidenceRequest.from_mapping(payload)
    result = await _controller.acquire(request)
    return result.to_dict()


@app.post("/v1/agentic/sessions/start", dependencies=[Depends(require_token)])
async def start_agentic_session(payload: dict) -> dict:
    request = BrowserEvidenceRequest.from_mapping(payload)
    observation = await _agentic.start(request)
    return observation.to_dict()


@app.get("/v1/agentic/sessions/{session_id}/observe", dependencies=[Depends(require_token)])
async def observe_agentic_session(session_id: str) -> dict:
    try:
        observation = await _agentic.observe(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agentic browser session not found") from exc
    return observation.to_dict()


@app.post("/v1/agentic/sessions/{session_id}/act", dependencies=[Depends(require_token)])
async def act_agentic_session(session_id: str, payload: dict) -> dict:
    try:
        action = AgenticBrowserAction.from_mapping({**payload, "session_id": session_id})
        observation = await _agentic.act(action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agentic browser session not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return observation.to_dict()


@app.post("/v1/agentic/sessions/{session_id}/finish", dependencies=[Depends(require_token)])
async def finish_agentic_session(session_id: str) -> dict:
    try:
        bundle = await _agentic.finish(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agentic browser session not found") from exc
    return bundle.to_dict()


@app.delete("/v1/agentic/sessions/{session_id}", dependencies=[Depends(require_token)])
async def abort_agentic_session(session_id: str) -> dict:
    await _agentic.abort(session_id)
    return {"status": "closed", "session_id": session_id}
