from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.product_evidence_harness.offline_capture import OfflineCaptureConfig, LivePageOfflineArtifactBuilder


class ProductPageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            "/product": ("text/html", b"""
                <html><head>
                  <title>Demo Toy Product</title>
                  <link rel=\"stylesheet\" href=\"/style.css\">
                  <script src=\"/live.js\"></script>
                </head><body>
                  <h1>Demo Toy Product</h1>
                  <img src=\"/hero.jpg\" srcset=\"/hero-small.jpg 1x, /hero-large.jpg 2x\">
                  <form action=\"https://retailer.example/checkout\"><button>Add</button></form>
                  <a href=\"https://retailer.example/live\">Live link</a>
                </body></html>
            """),
            "/style.css": ("text/css", b"body{background:url('/bg.png');}"),
            "/hero.jpg": ("image/jpeg", b"hero"),
            "/hero-small.jpg": ("image/jpeg", b"small"),
            "/hero-large.jpg": ("image/jpeg", b"large"),
            "/bg.png": ("image/png", b"bg"),
            "/live.js": ("application/javascript", b"fetch('/api')"),
        }
        content_type, payload = routes.get(self.path, ("text/plain", b"missing"))
        self.send_response(200 if self.path in routes else 404)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return


def test_capture_rewrites_assets_and_disables_live_network(tmp_path: Path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProductPageHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/product"
        builder = LivePageOfflineArtifactBuilder(OfflineCaptureConfig(output_dir=tmp_path))
        artifact = builder.capture_url(url, row_id="demo")
    finally:
        server.shutdown()

    assert artifact.offline_artifact_ready
    offline_html = Path(artifact.offline_html_path).read_text(encoding="utf-8")
    assert "Content-Security-Policy" in offline_html
    assert "script-src &#x27;none&#x27;" in offline_html
    assert "src=\"http://" not in offline_html
    assert "href=\"http://" not in offline_html
    assert "action=\"http" not in offline_html
    assert "data-offline-href" in offline_html
    assert "data-offline-disabled=\"external-script\"" in offline_html
    assert "assets/images/" in offline_html
    assert "assets/css/" in offline_html

    validation = json.loads(Path(artifact.validation_path).read_text(encoding="utf-8"))
    assert validation["status"] == "PRODUCTION_READY_OFFLINE_ARTIFACT"
    assert validation["network_bound_reference_count"] == 0
    assert validation["downloaded_asset_count"] >= 4
