# Champion

The tournament champion is the main selected URL only when it passes all production gates.

A champion must be browser-openable, highly scrapable, exact-product matched, and rich enough for downstream product coding.

Runner-up URLs are used for comparison only.

If no URL passes the production gate, there is no champion. In that case `product_url` stays empty and the best weak URL is kept only as a review candidate.

Invalid GTIN values are not used to build search queries.

Coding readiness cannot be ready unless a production-ready exact champion exists.
