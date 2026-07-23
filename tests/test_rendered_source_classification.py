from product_url_v2.config import RuntimeConfig
from product_url_v2.evaluation import apply_browser_evidence, assess_candidate
from product_url_v2.interpretation import DeterministicProductInterpreter
from product_url_v2.models import BrowserEvidence, GateStatus, PageEvidence, ProductInput, SearchResult, SourceRole
from product_url_v2.policy import evaluate_acceptance


EAN = "9783311706717"
TITLE = "MENSCH TÖTE DICH NICHT!"


def test_javascript_rendered_manufacturer_is_reclassified_before_ranking() -> None:
    url = "https://kampaverlag.ch/produkt/mensch-toete-dich-nicht/id/9783311706717"
    product = ProductInput("BOOK-MANUFACTURER-JS", TITLE, "CH", ean=EAN, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    search = SearchResult(url, TITLE, EAN, "fixture", "google", EAN, 1, True)
    page = PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=403,
        content_type="text/html",
        title="",
        description="",
        visible_text="",
        jsonld_products=(),
        metadata={},
        links=(),
        images=(),
        fetch_status=GateStatus.FAIL,
        fetch_error="HTTP 403",
    )
    candidate = assess_candidate(product, interpretation, search, page, {}, RuntimeConfig())
    assert candidate.source_role is SourceRole.COUNTRY_RETAILER

    rendered = BrowserEvidence(
        url=url,
        access=GateStatus.PASS,
        final_url=url,
        title=TITLE,
        visible_text=(
            f"{TITLE} Philipp Gurt EAN {EAN} Format E-Book "
            "Hersteller Kampa Verlag Produktdetails In den Warenkorb"
        ),
        product_controls=("In den Warenkorb",),
    )
    candidate = apply_browser_evidence(product, interpretation, candidate, rendered, RuntimeConfig())

    assert candidate.source_role is SourceRole.LOCAL_MANUFACTURER
    assert candidate.evidence["source_role_evidence"]["recomputed_after_browser"] is True
    assert evaluate_acceptance(candidate).eligible is True


def test_rendered_retailer_is_not_promoted_by_publisher_text() -> None:
    url = "https://www.exlibris.ch/de/buecher-buch/e-books/id/9783311706717"
    product = ProductInput("BOOK-RETAILER-JS", TITLE, "CH", ean=EAN, language_code="de")
    interpretation = DeterministicProductInterpreter().interpret(product)
    search = SearchResult(url, TITLE, EAN, "google:organic:EXACT_IDENTIFIER_MANUFACTURER", "google", EAN, 1, True)
    page = PageEvidence(
        requested_url=url,
        final_url=url,
        status_code=403,
        content_type="text/html",
        title="",
        description="",
        visible_text="",
        jsonld_products=(),
        metadata={},
        links=(),
        images=(),
        fetch_status=GateStatus.FAIL,
        fetch_error="HTTP 403",
    )
    candidate = assess_candidate(product, interpretation, search, page, {}, RuntimeConfig())
    rendered = BrowserEvidence(
        url=url,
        access=GateStatus.PASS,
        final_url=url,
        title=TITLE,
        visible_text=f"{TITLE} EAN {EAN} Hersteller Kampa Verlag Produktdetails Preis",
        product_controls=("Preis",),
    )
    candidate = apply_browser_evidence(product, interpretation, candidate, rendered, RuntimeConfig())

    assert candidate.source_role is SourceRole.COUNTRY_RETAILER
