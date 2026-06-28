from __future__ import annotations

from product_evidence_harness.constants import COUNTRY_ALTERNATIVE, COUNTRY_MATCHED, IDENTITY_PROBABLE, IDENTITY_VERIFIED
from product_evidence_harness.contracts import MatchVerification, ScrapeResult, URLCandidate
from product_evidence_harness.ranker import ProductURLRanker


def _make_card(url, *, identity, country_check, richness, confidence, scrapable=True):
    scrape = ScrapeResult(
        url=url, scraped=True, success=True, reachable=True, is_scrapable=scrapable,
        status_code=200, final_url=url, richness_score=richness, looks_like_product_page=True,
    )
    verification = MatchVerification(
        url=url, identity_status=identity, ean_check="MATCHED", title_check="STRONG",
        quantity_check="MATCHED", brand_check="MATCHED", page_type_check="PRODUCT_DETAIL",
        title_match_score=1.0,
    )
    return ProductURLRanker()._score_one(
        product=__import__("product_evidence_harness").ProductQuery(main_text="Acme Widget 18 ks", country_code="CZ"),
        candidate=URLCandidate(url=url, domain=url.split("//", 1)[-1].split("/", 1)[0]),
        scrape=scrape,
        verification=verification,
    )


def _ordered_urls(ranker, items):
    return [c.candidate.url for c in sorted(items, key=ranker._sort_key, reverse=True)]


def test_correct_identity_outranks_richer_but_weaker_identity():
    ranker = ProductURLRanker()
    verified = _make_card("https://a.cz/p", identity=IDENTITY_VERIFIED, country_check=COUNTRY_MATCHED, richness=0.1, confidence=0.5)
    probable = _make_card("https://b.cz/p", identity=IDENTITY_PROBABLE, country_check=COUNTRY_MATCHED, richness=0.9, confidence=0.9)
    assert _ordered_urls(ranker, [probable, verified])[0] == "https://a.cz/p"


def test_richness_breaks_tie_before_confidence():
    ranker = ProductURLRanker()
    richer = _make_card("https://rich.cz/p", identity=IDENTITY_VERIFIED, country_check=COUNTRY_MATCHED, richness=0.9, confidence=0.5)
    confident = _make_card("https://conf.cz/p", identity=IDENTITY_VERIFIED, country_check=COUNTRY_MATCHED, richness=0.3, confidence=0.9)
    assert _ordered_urls(ranker, [confident, richer])[0] == "https://rich.cz/p"
