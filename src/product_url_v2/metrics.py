from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from product_url_v2.contracts import DeliveryStatus, GateStatus, ProductRun


_TRACKING_NAMES = {
    "fbclid",
    "gclid",
    "msclkid",
    "ref",
    "ref_",
    "source",
    "campaign",
    "session",
    "sessionid",
}
_TRACKING_PREFIXES = ("utm_", "pk_", "ga_", "trk_")


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def canonical_url(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower().removeprefix("www.")
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        folded = key.lower()
        if folded in _TRACKING_NAMES or folded.startswith(_TRACKING_PREFIXES):
            continue
        query.append((folded, value.strip()))
    return urlunparse(
        (parsed.scheme.lower(), netloc, path, "", urlencode(sorted(query)), "")
    )


@dataclass(frozen=True, slots=True)
class RunMetrics:
    url_delivered: bool
    strictly_verified: bool
    review_required: bool
    candidate_count: int
    browser_assessed_count: int
    browser_assessment_coverage: float
    text_extractable_count: int
    direct_product_page_count: int
    coding_ready: bool
    search_actions_used: int
    full_scrapes_used: int
    browser_investigations_used: int

    @classmethod
    def from_run(cls, run: ProductRun) -> "RunMetrics":
        decision = run.decision
        candidates = run.candidates
        browser_assessed = sum(1 for item in candidates if item.browser_assessed)
        return cls(
            url_delivered=bool(decision and decision.selected_url),
            strictly_verified=bool(decision and decision.strictly_verified),
            review_required=bool(
                decision and decision.status is DeliveryStatus.REVIEW_REQUIRED
            ),
            candidate_count=len(candidates),
            browser_assessed_count=browser_assessed,
            browser_assessment_coverage=_ratio(browser_assessed, len(candidates)),
            text_extractable_count=sum(
                1 for item in candidates if item.text_extractable is GateStatus.PASS
            ),
            direct_product_page_count=sum(
                1 for item in candidates if item.direct_product_page is GateStatus.PASS
            ),
            coding_ready=bool(decision and decision.coding_ready),
            search_actions_used=run.budget_usage.search_actions,
            full_scrapes_used=run.budget_usage.full_scrapes,
            browser_investigations_used=run.budget_usage.browser_investigations,
        )


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    expected_url: str
    selected_url: str | None
    candidate_urls: tuple[str, ...]
    strict_verified: bool
    review_required: bool
    identity_correct: bool
    variant_pack_correct: bool
    direct_product_page: bool
    human_accepted: bool | None = None
    latency_seconds: float | None = None
    total_cost: float | None = None

    @property
    def delivered(self) -> bool:
        return canonical_url(self.selected_url) is not None

    @property
    def exact_url_correct(self) -> bool:
        return bool(
            canonical_url(self.selected_url)
            and canonical_url(self.selected_url) == canonical_url(self.expected_url)
        )

    @property
    def correct_product_delivery(self) -> bool:
        return bool(
            self.delivered
            and self.identity_correct
            and self.variant_pack_correct
            and self.direct_product_page
        )

    @property
    def candidate_recalled(self) -> bool:
        expected = canonical_url(self.expected_url)
        return bool(
            expected
            and expected
            in {item for item in map(canonical_url, self.candidate_urls) if item}
        )

    @property
    def wrong_product_escaped(self) -> bool:
        return bool(self.delivered and (not self.identity_correct or not self.variant_pack_correct))


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    total_cases: int
    url_delivery_rate: float
    exact_url_top1_accuracy: float
    correct_product_delivery_rate: float
    candidate_recall_at_k: float
    wrong_product_escape_rate: float
    strict_verified_rate: float
    review_required_rate: float
    review_acceptance_rate: float
    direct_product_page_rate: float
    mean_latency_seconds: float | None
    mean_cost_per_case: float | None
    mean_cost_per_correct_delivery: float | None

    @classmethod
    def from_cases(cls, cases: Iterable[BenchmarkCase]) -> "BenchmarkMetrics":
        values = tuple(cases)
        total = len(values)
        delivered = [item for item in values if item.delivered]
        reviews = [item for item in values if item.review_required]
        reviewed = [item for item in reviews if item.human_accepted is not None]
        latencies = [
            float(item.latency_seconds)
            for item in values
            if item.latency_seconds is not None
        ]
        costs = [float(item.total_cost) for item in values if item.total_cost is not None]
        correct_with_cost = [
            float(item.total_cost)
            for item in values
            if item.total_cost is not None and item.correct_product_delivery
        ]
        return cls(
            total_cases=total,
            url_delivery_rate=_ratio(len(delivered), total),
            exact_url_top1_accuracy=_ratio(
                sum(1 for item in values if item.exact_url_correct), total
            ),
            correct_product_delivery_rate=_ratio(
                sum(1 for item in values if item.correct_product_delivery), total
            ),
            candidate_recall_at_k=_ratio(
                sum(1 for item in values if item.candidate_recalled), total
            ),
            wrong_product_escape_rate=_ratio(
                sum(1 for item in values if item.wrong_product_escaped), total
            ),
            strict_verified_rate=_ratio(
                sum(1 for item in values if item.strict_verified), total
            ),
            review_required_rate=_ratio(len(reviews), total),
            review_acceptance_rate=_ratio(
                sum(1 for item in reviewed if item.human_accepted), len(reviewed)
            ),
            direct_product_page_rate=_ratio(
                sum(1 for item in delivered if item.direct_product_page), len(delivered)
            ),
            mean_latency_seconds=mean(latencies) if latencies else None,
            mean_cost_per_case=mean(costs) if costs else None,
            mean_cost_per_correct_delivery=(
                mean(correct_with_cost) if correct_with_cost else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ReleaseThresholds:
    minimum_url_delivery_rate: float = 0.98
    minimum_correct_product_delivery_rate: float = 0.95
    minimum_candidate_recall_at_k: float = 0.98
    maximum_wrong_product_escape_rate: float = 0.01
    minimum_direct_product_page_rate: float = 0.98


@dataclass(frozen=True, slots=True)
class ReleaseDecision:
    approved: bool
    failures: tuple[str, ...]


def evaluate_release(
    metrics: BenchmarkMetrics,
    thresholds: ReleaseThresholds | None = None,
) -> ReleaseDecision:
    limits = thresholds or ReleaseThresholds()
    failures: list[str] = []
    if metrics.url_delivery_rate < limits.minimum_url_delivery_rate:
        failures.append(
            f"URL delivery rate {metrics.url_delivery_rate:.2%} is below {limits.minimum_url_delivery_rate:.2%}."
        )
    if (
        metrics.correct_product_delivery_rate
        < limits.minimum_correct_product_delivery_rate
    ):
        failures.append(
            "Correct-product delivery rate "
            f"{metrics.correct_product_delivery_rate:.2%} is below "
            f"{limits.minimum_correct_product_delivery_rate:.2%}."
        )
    if metrics.candidate_recall_at_k < limits.minimum_candidate_recall_at_k:
        failures.append(
            f"Candidate recall@K {metrics.candidate_recall_at_k:.2%} is below {limits.minimum_candidate_recall_at_k:.2%}."
        )
    if metrics.wrong_product_escape_rate > limits.maximum_wrong_product_escape_rate:
        failures.append(
            "Wrong-product escape rate "
            f"{metrics.wrong_product_escape_rate:.2%} exceeds "
            f"{limits.maximum_wrong_product_escape_rate:.2%}."
        )
    if metrics.direct_product_page_rate < limits.minimum_direct_product_page_rate:
        failures.append(
            "Direct product-page rate "
            f"{metrics.direct_product_page_rate:.2%} is below "
            f"{limits.minimum_direct_product_page_rate:.2%}."
        )
    return ReleaseDecision(approved=not failures, failures=tuple(failures))
