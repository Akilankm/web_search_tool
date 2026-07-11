from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from src.product_evidence_harness.browser_contracts import BrowserEvidenceRequest
from src.product_evidence_harness.browser_service.controller import BrowserEvidenceController


_controller = BrowserEvidenceController()


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
        return
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


app = FastAPI(title="Product Browser Evidence Service", version="0.5.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return await _controller.health()


@app.post("/v1/evidence/acquire", dependencies=[Depends(require_token)])
async def acquire(payload: dict) -> dict:
    request = BrowserEvidenceRequest.from_mapping(payload)
    result = await _controller.acquire(request)
    return result.to_dict()
