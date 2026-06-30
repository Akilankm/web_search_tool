# Champion

The tournament champion is the main selected URL only when it passes all production gates.

A champion must be browser-openable, highly scrapable, exact-product matched, and rich enough for downstream product coding.

The engine should work through the ranked candidate pool from the 4-credit search set and continue batch scraping until it finds a production-ready champion or exhausts the candidate/scrape budget.

Runner-up URLs are used for comparison only.

If no URL passes the production gate, there is no champion. In that case `product_url` stays empty and the best weak URL is kept only as a review candidate.

Invalid GTIN values are not used to build search queries.

Coding readiness cannot be ready unless a production-ready exact champion exists.
