from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True, slots=True)
class URLDurabilityAssessment:
    original_url: str
    canonical_url: str | None
    durable: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ProductURLDurabilityGate:
    """Reject temporary, signed, session-bound, or otherwise expiring product URLs."""

    transient_query_parameters = frozenset(
        {
            "access_token",
            "auth",
            "authorization",
            "credential",
            "e",
            "exp",
            "expires",
            "expiry",
            "hmac",
            "jwt",
            "key-pair-id",
            "policy",
            "session",
            "session_id",
            "sessionid",
            "sid",
            "sig",
            "signature",
            "token",
            "x-amz-algorithm",
            "x-amz-credential",
            "x-amz-date",
            "x-amz-expires",
            "x-amz-security-token",
            "x-amz-signature",
            "x-goog-algorithm",
            "x-goog-credential",
            "x-goog-date",
            "x-goog-expires",
            "x-goog-signature",
        }
    )
    removable_tracking_parameters = frozenset(
        {
            "fbclid",
            "gclid",
            "gbraid",
            "mc_cid",
            "mc_eid",
            "ref",
            "referrer",
            "source",
            "utm_campaign",
            "utm_content",
            "utm_medium",
            "utm_source",
            "utm_term",
            "wbraid",
        }
    )

    def assess(self, url: str | None) -> URLDurabilityAssessment:
        raw = str(url or "").strip()
        reasons: list[str] = []
        if not raw:
            return URLDurabilityAssessment(raw, None, False, ("URL_MISSING",))

        try:
            parsed = urlsplit(raw)
        except ValueError:
            return URLDurabilityAssessment(raw, None, False, ("URL_MALFORMED",))

        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            reasons.append("URL_NOT_ABSOLUTE_HTTP")
        if parsed.username or parsed.password:
            reasons.append("URL_CONTAINS_CREDENTIALS")

        retained: list[tuple[str, str]] = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            normalized = key.strip().lower()
            if normalized in self.transient_query_parameters:
                reasons.append(f"URL_TRANSIENT_PARAMETER:{normalized}")
                continue
            if normalized in self.removable_tracking_parameters or normalized.startswith("utm_"):
                continue
            retained.append((key, value))

        canonical = urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path or "/",
                urlencode(retained, doseq=True),
                "",
            )
        )
        return URLDurabilityAssessment(
            original_url=raw,
            canonical_url=canonical,
            durable=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
        )
