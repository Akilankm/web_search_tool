from __future__ import annotations

from product_url_v2 import (
    BenchmarkCase,
    BenchmarkMetrics,
    ReleaseThresholds,
    canonical_url,
    evaluate_release,
)


def test_canonical_url_removes_tracking_without_erasing_product_identity() -> None:
    assert canonical_url(
        "https://www.shop.example/product/123/?variant=blue&utm_source=google#details"
    ) == "https://shop.example/product/123?variant=blue"


def test_release_gate_rejects_good_delivery_with_wrong_product_escapes() -> None:
    cases = (
        BenchmarkCase(
            case_id="A",
            expected_url="https://shop.example/product/a",
            selected_url="https://shop.example/product/a",
            candidate_urls=("https://shop.example/product/a",),
            strict_verified=True,
            review_required=False,
            identity_correct=True,
            variant_pack_correct=True,
            direct_product_page=True,
            human_accepted=True,
        ),
        BenchmarkCase(
            case_id="B",
            expected_url="https://shop.example/product/b",
            selected_url="https://shop.example/product/b-bundle",
            candidate_urls=(
                "https://shop.example/product/b",
                "https://shop.example/product/b-bundle",
            ),
            strict_verified=False,
            review_required=True,
            identity_correct=True,
            variant_pack_correct=False,
            direct_product_page=True,
            human_accepted=False,
        ),
    )

    metrics = BenchmarkMetrics.from_cases(cases)
    decision = evaluate_release(
        metrics,
        ReleaseThresholds(
            minimum_url_delivery_rate=1.0,
            minimum_correct_product_delivery_rate=0.9,
            minimum_candidate_recall_at_k=1.0,
            maximum_wrong_product_escape_rate=0.01,
            minimum_direct_product_page_rate=1.0,
        ),
    )

    assert metrics.url_delivery_rate == 1.0
    assert metrics.candidate_recall_at_k == 1.0
    assert metrics.wrong_product_escape_rate == 0.5
    assert decision.approved is False
    assert any("Wrong-product escape rate" in item for item in decision.failures)


def test_release_gate_approves_clean_benchmark() -> None:
    cases = tuple(
        BenchmarkCase(
            case_id=str(index),
            expected_url=f"https://shop.example/product/{index}",
            selected_url=f"https://shop.example/product/{index}",
            candidate_urls=(f"https://shop.example/product/{index}",),
            strict_verified=True,
            review_required=False,
            identity_correct=True,
            variant_pack_correct=True,
            direct_product_page=True,
            human_accepted=True,
        )
        for index in range(20)
    )

    decision = evaluate_release(BenchmarkMetrics.from_cases(cases))

    assert decision.approved is True
    assert decision.failures == ()
