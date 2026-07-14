from pathlib import Path

from src.product_evidence_harness.browser_service.agentic_controller import AgenticBrowserController
from src.product_evidence_harness.browser_service.controller import BrowserEvidenceController, BrowserRuntimeConfig


def test_asset_policy_rejects_non_http_and_tracking_assets(tmp_path: Path) -> None:
    controller = BrowserEvidenceController(BrowserRuntimeConfig(artifact_root=tmp_path))
    assert not controller._allowed_asset_url("https://shop.example/p/1", "data:image/png;base64,abc")
    assert not controller._allowed_asset_url("https://shop.example/p/1", "https://cdn.example/tracking-pixel.gif")
    assert controller._allowed_asset_url("https://shop.example/p/1", "https://cdn.example/product-1.jpg")


def test_agentic_browser_navigation_is_restricted_to_same_site() -> None:
    assert AgenticBrowserController._same_site(
        "https://www.shop.example/product/1",
        "https://shop.example/specifications/1",
    )
    assert AgenticBrowserController._same_site(
        "https://shop.example/product/1",
        "https://details.shop.example/product/1",
    )
    assert not AgenticBrowserController._same_site(
        "https://shop.example/product/1",
        "https://accounts.example.net/login",
    )


def test_agentic_browser_blocks_transactional_and_authentication_click_terms() -> None:
    terms = AgenticBrowserController.PROHIBITED_CLICK_TERMS
    assert "add to cart" in terms
    assert "checkout" in terms
    assert "sign in" in terms
    assert "pay now" in terms
