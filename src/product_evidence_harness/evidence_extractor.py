from __future__ import annotations

from dataclasses import dataclass

from src.product_evidence_harness.contracts import ProductEvidence, ScrapeResult


@dataclass(frozen=True)
class EvidenceExtractor:
    def from_scrape(self, scrape: ScrapeResult) -> ProductEvidence:
        return ProductEvidence(
            source_url=scrape.final_url or scrape.url,
            source_type="scraped_page",
            product_title=scrape.page_product_name or scrape.title or scrape.h1 or None,
            brand=scrape.brand or None,
            manufacturer=scrape.manufacturer or None,
            ean=scrape.structured_eans[0] if scrape.structured_eans else None,
            price=scrape.price,
            currency=scrape.currency,
            availability=scrape.availability,
            description=scrape.description,
            specs=dict(scrape.specs),
            confidence=scrape.richness_score,
            notes=(f"word_count={scrape.word_count}", f"richness={scrape.richness_score}"),
        )
