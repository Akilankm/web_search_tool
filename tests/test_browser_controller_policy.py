from pathlib import Path

from src.product_evidence_harness.browser_service.controller import BrowserEvidenceController, BrowserRuntimeConfig


def test_asset_policy_rejects_non_http_and_tracking_assets(tmp_path: Path) -> None:
    controller = BrowserEvidenceController(BrowserRuntimeConfig(artifact_root=tmp_path))
    assert not controller._allowed_asset_url("https://shop.example/p/1", "data:image/png;base64,abc")
    assert not controller._allowed_asset_url("https://shop.example/p/1", "https://cdn.example/tracking-pixel.gif")
    assert controller._allowed_asset_url("https://shop.example/p/1", "https://cdn.example/product-1.jpg")
