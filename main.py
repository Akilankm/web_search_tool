from src.serp_hybrid_url_finder import (
    CSVProductIO,
    HybridProductURLFinderPipeline,
    PipelineConfig,
    ProductQuery,
    RichPrinter,
    SerpAPIConfig,
    configure_logging,
)
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm.auto import tqdm
from datetime import datetime
from rich import print

configure_logging('INFO')
printer = RichPrinter()

serp_config = SerpAPIConfig.from_env(
    country_code='CO',  # SerpAPI gl fallback; per-product country_code overrides this
    language_code='en',
    no_cache=False,
)

pipeline_config = PipelineConfig(
    max_organic_calls=2,
    max_ai_mode_calls=2,
    max_candidates_for_ai=18,
    run_ai_repair=True,
    repair_confidence_threshold=0.80,
    # crawl4ai scrape verification
    scrape_enabled=True,
    require_scrapable_final=True,
    max_urls_to_scrape=10,
    crawl_headless=True,
)

pipeline = HybridProductURLFinderPipeline(
    serp_config=serp_config,
    pipeline_config=pipeline_config,
)

product = ProductQuery(
    row_id='demo-001',
    main_text='MATCHBOX LESNEY MADE IN ENGLAND #7  - NARANJA',
    country_code='CO',        # required
    retailer_name='meli',       # optional
    ean='8018190039368',      # optional
)

trace = pipeline.run(product, return_trace=True)

printer.print_dict(trace.best_match.to_dict())

print('Scrape + identity verification per candidate:')
for url, scrape in trace.scrapes.items():
    v = trace.verifications.get(url)
    identity = v.identity_status if v else 'NONE'
    ean = v.ean_check if v else '-'
    qty = v.quantity_check if v else '-'
    print(
        f"- identity={identity:10} ean={ean:9} qty={qty:9} "
        f"scrapable={scrape.is_scrapable} soft404={scrape.is_soft_404} url={url}"
    )

print('\nFinal submission status:', trace.best_match.validation_status)
print('Identity status        :', trace.best_match.identity_status)
print('Retailer match         :', trace.best_match.retailer_check,
      '(requested:', trace.best_match.retailer_name, ')')
print('Confidence             :', trace.best_match.confidence)
print('Product URL            :', trace.best_match.product_url)
print('Justification          :', trace.best_match.justification)

# Full identity + confidence breakdown for the top-ranked candidate (auditable).
if trace.scored_candidates:
    printer.print_verification(trace.scored_candidates[0])