from __future__ import annotations

from product_url_v2.config import RuntimeConfig
from product_url_v2.evaluation import apply_browser_evidence, assess_candidate, choose_delivery
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import (
    BrowserEvidence,
    CandidateAssessment,
    DeliveryStatus,
    GateStatus,
    IdentityMatch,
    PageEvidence,
    ProductInput,
    SearchResult,
    SourceRole,
)
from product_url_v2.search import canonical_url

EAN = "9783311706717"
TITLE = "MENSCH TÖTE DICH NICHT!"


def _page(url: str, text: str, products=(), status: GateStatus = GateStatus.PASS, error: str = "") -> PageEvidence:
    return PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=200 if status is GateStatus.PASS else 503,
        content_type="text/html",
        title=TITLE if text else "",
        description=text,
        visible_text=text,
        jsonld_products=tuple(products),
        metadata={"og:type": "product"} if status is GateStatus.PASS else {},
        links=(),
        images=(),
        fetch_status=status,
        fetch_error=error,
    )


def _fully_mapped_candidate(role: SourceRole, url: str, candidate_id: str) -> CandidateAssessment:
    return CandidateAssessment(
        candidate_id=candidate_id,
        url=url,
        domain=url.split("//", 1)[1].split("/", 1)[0],
        search_rank=1,
        search_support=1.0,
        source_role=role,
        identity_match=IdentityMatch.EXACT,
        identity_confidence=0.99,
        direct_product_page=GateStatus.PASS,
        direct_page_score=0.95,
        durable_url=GateStatus.PASS,
        country_match=GateStatus.PASS,
        retailer_match=GateStatus.NOT_ASSESSED,
        browser_access=GateStatus.PASS,
        text_extractable=GateStatus.PASS,
        coding_evidence_complete=GateStatus.PASS,
        source_authority=100 if "MANUFACTURER" in role.value else 75,
        evidence={
            "required_identifier": EAN,
            "exact_identifier_verified": True,
            "hard_url_blockers": [],
            "delivery_basis": "rendered_exact_product_page",
        },
    )


def test_schreiber_conflicting_identifier_and_inaccessible_page_is_rejected() -> None:
    raw_url = (
        "https://schreibers.ch/detail/ISBN-2244067996519/Gurt-Philipp/"
        "Mensch-t%C3%B6te-Dich-nicht?srsltid=tracking"
    )
    url = canonical_url(raw_url)
    product = ProductInput("BOOK-1", TITLE, "CH", ean=EAN, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    search = SearchResult(url, TITLE, EAN, "google:organic:EXACT_IDENTIFIER_COUNTRY_RETAILER", "google", EAN, 1, True)
    page = _page(url, "", status=GateStatus.FAIL, error="HTTP 503")

    candidate = assess_candidate(product, interpretation, search, page, {}, RuntimeConfig())
    decision = choose_delivery((candidate,))

    assert "srsltid" not in candidate.url
    assert candidate.mapping_eligible is False
    assert candidate.identity_match is IdentityMatch.MISMATCH
    assert any("URL identifier conflict" in conflict for conflict in candidate.conflicts)
    assert decision.status is DeliveryStatus.FAILED
    assert decision.selected_url is None


def test_exact_exlibris_ebook_page_is_selected_after_browser_validation() -> None:
    url = "https://www.exlibris.ch/de/buecher-buch/e-books-deutsch/philipp-gurt/mensch-toete-dich-nicht/id/9783311706717"
    product = ProductInput("BOOK-2", TITLE, "CH", ean=EAN, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    search = SearchResult(url, TITLE, EAN, "google:organic:EXACT_IDENTIFIER_COUNTRY_RETAILER", "google", EAN, 1, True)
    text = (
        "Mensch töte Dich nicht! Philipp Gurt EAN 9783311706717 Format E-Book epub "
        "Hersteller Kampa Verlag Download steht sofort bereit Produktinformationen"
    )
    page = _page(
        url,
        text,
        ({"@type": "Book", "name": TITLE, "isbn": EAN, "publisher": {"name": "Kampa Verlag"}},),
    )
    candidate = assess_candidate(product, interpretation, search, page, {"required_fields": ["product_name"]}, RuntimeConfig())
    browser = BrowserEvidence(
        url=url,
        access=GateStatus.PASS,
        final_url=url,
        title=TITLE,
        visible_text=text + " In den Warenkorb",
        product_controls=("In den Warenkorb",),
    )
    candidate = apply_browser_evidence(product, interpretation, candidate, browser, RuntimeConfig())
    decision = choose_delivery((candidate,))

    assert candidate.exact_identifier_verified is True
    assert candidate.mapping_eligible is True
    assert decision.status in {DeliveryStatus.VERIFIED, DeliveryStatus.REVIEW_REQUIRED}
    assert decision.selected_url == url


def test_print_manufacturer_page_does_not_match_supplied_ebook_ean() -> None:
    url = "https://kampaverlag.ch/produkt/mensch-toete-dich-nicht"
    product = ProductInput("BOOK-3", TITLE, "CH", ean=EAN, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    search = SearchResult(url, TITLE, "Official publisher page", "google:organic:EXACT_IDENTIFIER_MANUFACTURER", "google", EAN, 1, True)
    print_ean = "9783311121381"
    text = f"Mensch töte Dich nicht! Philipp Gurt Kampa Verlag ISBN {print_ean} 400 Seiten Bestellen"
    page = _page(url, text, ({"@type": "Book", "name": TITLE, "isbn": print_ean, "publisher": {"name": "Kampa Verlag"}},))

    candidate = assess_candidate(product, interpretation, search, page, {}, RuntimeConfig())

    assert candidate.identity_match is IdentityMatch.MISMATCH
    assert candidate.mapping_eligible is False
    assert any(print_ean in conflict for conflict in candidate.conflicts)


def test_exact_manufacturer_outranks_exact_retailer() -> None:
    manufacturer = _fully_mapped_candidate(
        SourceRole.LOCAL_MANUFACTURER,
        "https://brand.example/product/exact-9783311706717",
        "M",
    )
    retailer = _fully_mapped_candidate(
        SourceRole.COUNTRY_RETAILER,
        "https://retailer.example/product/exact-9783311706717",
        "R",
    )

    decision = choose_delivery((retailer, manufacturer))

    assert decision.selected_candidate_id == "M"
    assert decision.selected_url == manufacturer.url


def test_browser_failure_blocks_delivery_even_when_http_page_has_exact_ean() -> None:
    url = "https://retailer.example/product/exact-9783311706717"
    product = ProductInput("BOOK-4", TITLE, "CH", ean=EAN, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    search = SearchResult(url, TITLE, EAN, "fixture", "google", EAN, 1, True)
    page = _page(url, f"{TITLE} EAN {EAN} Product details price")
    candidate = assess_candidate(product, interpretation, search, page, {}, RuntimeConfig())
    candidate = apply_browser_evidence(
        product,
        interpretation,
        candidate,
        BrowserEvidence(url=url, access=GateStatus.FAIL, error="navigation timeout"),
        RuntimeConfig(),
    )

    assert candidate.mapping_eligible is False
    assert choose_delivery((candidate,)).selected_url is None


def test_search_snippet_cannot_substitute_for_exact_page_evidence() -> None:
    url = "https://retailer.example/product/mensch-toete-dich-nicht"
    product = ProductInput("BOOK-5", TITLE, "CH", ean=EAN, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    search = SearchResult(url, TITLE, f"EAN {EAN}", "fixture", "google", EAN, 1, True)
    page = _page(url, f"{TITLE} Philipp Gurt product details price")

    candidate = assess_candidate(product, interpretation, search, page, {}, RuntimeConfig())

    assert candidate.exact_identifier_verified is False
    assert candidate.identity_match is not IdentityMatch.EXACT
    assert candidate.mapping_eligible is False


def test_inaccessible_candidates_remain_audit_evidence_not_final_mapping() -> None:
    candidates = tuple(
        CandidateAssessment(
            candidate_id=f"C-{index}",
            url=f"https://shop{index}.example.com/product/item-{index}",
            domain=f"shop{index}.example.com",
            search_rank=index,
            search_support=0.9,
            source_role=SourceRole.COUNTRY_RETAILER,
            identity_match=IdentityMatch.EXACT,
            identity_confidence=0.95,
            direct_product_page=GateStatus.PASS,
            direct_page_score=0.8,
            durable_url=GateStatus.PASS,
            country_match=GateStatus.PASS,
            retailer_match=GateStatus.NOT_ASSESSED,
            browser_access=GateStatus.FAIL,
            text_extractable=GateStatus.FAIL,
            coding_evidence_complete=GateStatus.PASS,
            source_authority=75,
            evidence={
                "required_identifier": EAN,
                "exact_identifier_verified": True,
                "hard_url_blockers": ["Selected URL did not pass rendered-browser accessibility."],
            },
        )
        for index in range(1, 8)
    )

    decision = choose_delivery(candidates)

    assert decision.status is DeliveryStatus.FAILED
    assert decision.selected_url is None
