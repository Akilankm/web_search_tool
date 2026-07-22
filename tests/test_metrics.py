from product_url_v2.config import ReleaseGates
from product_url_v2.metrics import BenchmarkCase, BenchmarkOutcome, calculate_metrics, release_failures
from product_url_v2.models import DeliveryStatus


def test_wrong_product_escape_blocks_release_even_with_full_delivery() -> None:
    cases = [BenchmarkCase("1", "https://shop.example/products/1"), BenchmarkCase("2", "https://shop.example/products/2")]
    outcomes = [
        BenchmarkOutcome("1", cases[0].expected_url, DeliveryStatus.VERIFIED, True, True, True, 100),
        BenchmarkOutcome("2", "https://shop.example/products/wrong", DeliveryStatus.REVIEW_REQUIRED, False, True, True, 100),
    ]
    metrics = calculate_metrics(cases, outcomes)
    assert metrics.url_delivery_rate == 1.0
    assert "wrong_product_escape_rate" in release_failures(metrics, ReleaseGates())
