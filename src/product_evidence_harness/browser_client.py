from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from src.product_evidence_harness.browser_contracts import BrowserEvidenceBundle, BrowserEvidenceRequest


@dataclass(frozen=True, slots=True)
class BrowserServiceConfig:
    base_url: str = "http://browser:9000"
    api_token: str = ""
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 180.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "BrowserServiceConfig":
        token = os.getenv("BROWSER_API_TOKEN", "").strip()
        token_file = os.getenv("BROWSER_API_TOKEN_FILE", "").strip()
        if not token and token_file:
            path = Path(token_file)
            if path.is_file():
                token = path.read_text(encoding="utf-8").strip()
        return cls(
            base_url=os.getenv("BROWSER_BASE_URL", "http://browser:9000").rstrip("/"),
            api_token=token,
            connect_timeout_seconds=float(os.getenv("BROWSER_CONNECT_TIMEOUT_SECONDS", "5")),
            read_timeout_seconds=float(os.getenv("BROWSER_READ_TIMEOUT_SECONDS", "180")),
            max_retries=max(0, int(os.getenv("BROWSER_CLIENT_MAX_RETRIES", "2"))),
        )


class BrowserServiceError(RuntimeError):
    pass


class BrowserEvidenceClient:
    def __init__(self, config: BrowserServiceConfig | None = None) -> None:
        self.config = config or BrowserServiceConfig.from_env()
        headers = {"User-Agent": "product-evidence-agent/0.5"}
        if self.config.api_token:
            headers["Authorization"] = f"Bearer {self.config.api_token}"
        self._client = httpx.Client(
            base_url=self.config.base_url,
            headers=headers,
            timeout=httpx.Timeout(
                connect=self.config.connect_timeout_seconds,
                read=self.config.read_timeout_seconds,
                write=30.0,
                pool=30.0,
            ),
        )

    def close(self) -> None:
        self._client.close()

    def health(self) -> dict[str, Any]:
        response = self._client.get("/health")
        response.raise_for_status()
        return dict(response.json())

    def acquire(self, request: BrowserEvidenceRequest) -> BrowserEvidenceBundle:
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._client.post("/v1/evidence/acquire", json=request.to_dict())
                response.raise_for_status()
                return BrowserEvidenceBundle.from_mapping(response.json())
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
        raise BrowserServiceError(f"Browser evidence request failed: {type(last_error).__name__}: {last_error}") from last_error

    def __enter__(self) -> "BrowserEvidenceClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
