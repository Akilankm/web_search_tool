from __future__ import annotations

import httpx
import pytest

from src.product_evidence_harness.progress_context import browser_progress_callback
from src.product_evidence_harness.browser_client import (
    BrowserEvidenceClient,
    BrowserServiceConfig,
    BrowserServiceError,
)
from src.product_evidence_harness.browser_contracts import (
    BrowserEvidenceRequest,
    ProductIdentityPayload,
)


class SequencedHTTPClient:
    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self.responses = list(responses)

    def post(self, _path: str, *, json: dict) -> httpx.Response:
        assert json["candidate_id"] == "CAND-001"
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        return None


def _request() -> BrowserEvidenceRequest:
    return BrowserEvidenceRequest(
        job_id="ROW-1",
        candidate_id="CAND-001",
        url="https://www.shop.example/product/123?token=secret",
        product_identity=ProductIdentityPayload(
            row_id="ROW-1",
            main_text="Example product",
            country_code="IN",
        ),
    )


def _success_response() -> httpx.Response:
    request = httpx.Request("POST", "http://browser:9000/v1/evidence/acquire")
    return httpx.Response(
        200,
        request=request,
        json={
            "status": "COMPLETED",
            "job_id": "ROW-1",
            "candidate_id": "CAND-001",
            "requested_url": "https://www.shop.example/product/123?token=secret",
            "final_url": "https://shop.example/product/123",
            "browser_openable": True,
            "rendered_product_verified": True,
            "text_scrapable": True,
            "gallery_discovered": False,
            "direct_images_downloaded": 0,
            "screenshots_captured": 0,
            "multimodal_scrapable": False,
        },
    )


def test_browser_client_reports_candidate_start_and_outcome() -> None:
    messages: list[tuple[str, str]] = []
    client = BrowserEvidenceClient(
        BrowserServiceConfig(api_token="", max_retries=0)
    )
    client._client = SequencedHTTPClient([_success_response()])  # type: ignore[assignment]

    with browser_progress_callback(lambda stage, message: messages.append((stage, message))):
        bundle = client.acquire(_request())

    assert bundle.browser_openable is True
    assert [stage for stage, _ in messages] == [
        "REQUESTING_BROWSER_EVIDENCE",
        "REQUESTING_BROWSER_EVIDENCE",
    ]
    assert "CAND-001 | attempt 1/1 | STARTED | shop.example" in messages[0][1]
    assert "CAND-001 | COMPLETED" in messages[1][1]
    assert "openable=True" in messages[1][1]
    assert "scrapable=True" in messages[1][1]
    assert "token=secret" not in " ".join(message for _, message in messages)


def test_browser_client_reports_retry_and_terminal_failure() -> None:
    messages: list[str] = []
    request = httpx.Request("POST", "http://browser:9000/v1/evidence/acquire")
    timeout = httpx.ReadTimeout("timed out", request=request)
    client = BrowserEvidenceClient(
        BrowserServiceConfig(api_token="", max_retries=1)
    )
    client._client = SequencedHTTPClient([timeout, timeout])  # type: ignore[assignment]

    with browser_progress_callback(lambda _stage, message: messages.append(message)):
        with pytest.raises(BrowserServiceError):
            client.acquire(_request())

    assert any("RETRYING" in message and "attempt 1/2" in message for message in messages)
    assert any("FAILED" in message and "2/2 attempts" in message for message in messages)
    assert all("token=secret" not in message for message in messages)
