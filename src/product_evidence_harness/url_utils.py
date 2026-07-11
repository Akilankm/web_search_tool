from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from src.product_evidence_harness.constants import (
    BLOCKED_DOMAINS,
    BLOCKED_EXTENSIONS,
    URL_REGEX,
    VALID_URL_SCHEMES,
)

_URL_PATTERN = re.compile(URL_REGEX, re.IGNORECASE)
_TRACKING_QUERY_KEYS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "dclid",
    "fbclid",
    "msclkid",
    "yclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
    "campaign",
    "affiliate",
    "aff_id",
    "tracking",
})


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def normalize_url(url: str | None) -> str | None:
    """Return a stable comparison URL while preserving product identity parameters.

    Known analytics/affiliate parameters are removed. Other parameters are retained
    and sorted because keys such as ``sku``, ``pid``, ``variant`` or ``product_id``
    may be required to identify the exact product page.
    """
    if not url:
        return None
    url = str(url).strip().strip(".,);]'\"")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in VALID_URL_SCHEMES or not parsed.netloc:
        return None
    path = parsed.path.rstrip("/") or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_pairs), doseq=True)
    normalized = urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))
    if is_blocked_url(normalized):
        return None
    return normalized


def is_blocked_url(url: str) -> bool:
    lowered = url.lower()
    if any(domain in lowered for domain in BLOCKED_DOMAINS):
        return True
    return any(lowered.split("?", 1)[0].endswith(ext) for ext in BLOCKED_EXTENSIONS)


def urls_from_text(text: str) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for match in _URL_PATTERN.finditer(text or ""):
        url = normalize_url(match.group(0))
        if url and url not in seen:
            seen.add(url)
            results.append(url)
    return results
