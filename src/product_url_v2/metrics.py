from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from product_url_v2.config import ReleaseGates
from product_url_v2.models import DeliveryStatus
from product_url_v2.search import canonical_url


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    row_id: str
    expected_url: str
    expected_product_id: str = ""


@dataclass(frozen=True, slots=True)
class BenchmarkOutcome:
    row_id: str
    delivered_url: str | None
    status: DeliveryStatus
    correct_product: bool
    direct_product_page: bool
    expected_in_candidates: bool
    latency_ms: int
    cost_units: float = 0.0


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    total: int
    url_delivery_rate: float
    exact_url_top1_accuracy: float
    correct_product_delivery_rate: float
    candidate_recall_at_k: float
    wrong_product_escape_rate: float
    direct_product_page_rate: float
    average_latency_ms: float
    cost_per_correct_url: float


def calculate_metrics(cases: Sequence[BenchmarkCase], outcomes: Sequence[BenchmarkOutcome]) -> BenchmarkMetrics:
    by_row = {item.row_id: item for item in outcomes}
    total = len(cases)
    if total == 0:
        raise ValueError("benchmark requires at least one case")
    delivered = exact = correct = recalled = wrong = direct = 0
    latency = cost = 0.0
    for case in cases:
        outcome = by_row.get(case.row_id)
        if outcome is None:
            continue
        latency += outcome.latency_ms
        cost += outcome.cost_units
        if outcome.delivered_url:
            delivered += 1
            exact += int(canonical_url(outcome.delivered_url) == canonical_url(case.expected_url))
            correct += int(outcome.correct_product)
            wrong += int(not outcome.correct_product)
            direct += int(outcome.direct_product_page)
        recalled += int(outcome.expected_in_candidates)
    return BenchmarkMetrics(
        total=total,
        url_delivery_rate=delivered / total,
        exact_url_top1_accuracy=exact / total,
        correct_product_delivery_rate=correct / total,
        candidate_recall_at_k=recalled / total,
        wrong_product_escape_rate=wrong / total,
        direct_product_page_rate=direct / delivered if delivered else 0.0,
        average_latency_ms=latency / total,
        cost_per_correct_url=cost / correct if correct else float("inf"),
    )


def release_failures(metrics: BenchmarkMetrics, gates: ReleaseGates) -> tuple[str, ...]:
    checks = {
        "url_delivery_rate": metrics.url_delivery_rate >= gates.url_delivery_rate,
        "correct_product_delivery_rate": metrics.correct_product_delivery_rate >= gates.correct_product_delivery_rate,
        "candidate_recall_at_k": metrics.candidate_recall_at_k >= gates.candidate_recall_at_k,
        "wrong_product_escape_rate": metrics.wrong_product_escape_rate <= gates.wrong_product_escape_rate,
        "direct_product_page_rate": metrics.direct_product_page_rate >= gates.direct_product_page_rate,
    }
    return tuple(name for name, passed in checks.items() if not passed)
