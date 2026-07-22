from product_url_v2.acquisition import parse_html_evidence, product_fields
from product_url_v2.models import GateStatus


def test_jsonld_and_visible_page_extraction() -> None:
    html = b'''<html><head><title>LEGO Set 123</title><meta property="og:type" content="product"><script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"LEGO Set 123","brand":{"@type":"Brand","name":"LEGO"},"sku":"123","gtin13":"1234567890123","offers":{"@type":"Offer","price":"19.99","priceCurrency":"EUR"}}</script></head><body><button>Add to cart</button></body></html>'''
    evidence = parse_html_evidence("https://shop.example/products/123", "https://shop.example/products/123", 200, "text/html", html)
    fields = product_fields(evidence)
    assert evidence.fetch_status is GateStatus.PASS
    assert fields["brand"] == "LEGO"
    assert fields["gtin13"] == "1234567890123"
    assert fields["price"] == "19.99"
