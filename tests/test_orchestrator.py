from pathlib import Path

from product_url_v2.config import BrowserConfig, RuntimeConfig
from product_url_v2.models import BrowserEvidence, GateStatus, PageEvidence, ProductInput, SearchObservation, SearchResult
from product_url_v2.orchestrator import ProductURLOrchestrator


class FakeSearch:
    def execute(self, action, product):
        url = "https://lego.example/products/r2-d2-75379"
        return SearchObservation(action, "SUCCESS", (SearchResult(url, "LEGO R2-D2 75379", "LEGO model 75379", "fixture", action.engine, action.query, 1, True),))


class FakeAcquirer:
    def acquire_many(self, candidates, progress=None):
        url = candidates[0].url
        evidence = PageEvidence(
            url, url, 200, "text/html", "LEGO R2-D2 75379", "LEGO building set",
            "LEGO R2-D2 75379 price add to cart in stock",
            ({"@type": "Product", "name": "LEGO R2-D2 75379", "brand": {"name": "LEGO"}, "model": "75379", "offers": {"price": "99.99"}},),
            {"og:type": "product"}, (), (), GateStatus.PASS,
        )
        if progress:
            progress("ACQUISITION_PLAN", {
                "submitted_candidate_count": len(candidates),
                "selected_candidate_count": 1,
                "max_candidates": 1,
                "max_per_domain": 1,
                "max_workers": 1,
                "selected_urls": [url],
            })
            progress("PAGE_FETCHED", {
                "requested_url": url,
                "final_url": url,
                "fetch_status": "PASS",
                "status_code": 200,
                "content_type": "text/html",
                "title": "LEGO R2-D2 75379",
                "jsonld_product_count": 1,
                "visible_text_length": 48,
                "link_count": 0,
                "image_count": 0,
                "elapsed_ms": 0,
                "fetch_error": "",
            })
        return {url: evidence}


class FakeBrowser:
    def investigate(self, url, row_id, candidate_id):
        return BrowserEvidence(url, GateStatus.PASS, url, "LEGO R2-D2 75379", "LEGO R2-D2 75379 add to cart", product_controls=("Add to cart",))


def test_end_to_end_artifacts_delivery_and_trace(tmp_path: Path) -> None:
    feature_root = tmp_path / "features"
    feature_root.mkdir()
    (feature_root / "toy.json").write_text('{"required_fields":["brand","product_name"]}')
    config = RuntimeConfig(artifact_root=tmp_path / "artifacts", feature_set_root=feature_root, browser=BrowserConfig(enabled=True, required=True, max_candidates=1, base_url="http://unused"))
    events = []
    result = ProductURLOrchestrator(config, FakeSearch(), FakeAcquirer(), FakeBrowser()).resolve(
        ProductInput("RUN-1", "LEGO R2-D2 75379", "GB", feature_set="toy"),
        progress=events.append,
    )
    assert result.decision.selected_url == "https://lego.example/products/r2-d2-75379"
    assert result.decision.status.value in {"VERIFIED", "REVIEW_REQUIRED"}
    assert events
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert any(event.event_type == "CANDIDATE_ASSESSED" for event in events)
    assert any(event.event_type == "CANDIDATE_RANKING" for event in events)
    assert any(event.event_type == "DECISION_COMPLETE" for event in events)
    artifact_dir = Path(result.artifact_dir)
    for name in ("input.json", "interpretation.json", "search.json", "candidates.json", "candidates.csv", "decision.json", "result.json", "audit.md"):
        assert (artifact_dir / name).is_file()
