from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.product_evidence_harness.contracts import ProductQuery
from src.product_evidence_harness.offline_capture import OfflineCaptureConfig, LivePageOfflineArtifactBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze a live product page into an offline product evidence artifact.")
    parser.add_argument("--url", required=True, help="Confirmed champion URL to capture.")
    parser.add_argument("--output-dir", default="outputs/offline_artifacts", help="Base output directory or explicit artifact directory when --artifact-dir is used.")
    parser.add_argument("--artifact-dir", default=None, help="Explicit artifact folder to write.")
    parser.add_argument("--row-id", default="demo", help="Input/product row id used in the artifact path.")
    parser.add_argument("--main-text", default="Offline capture product", help="Input product main text for structured evidence overlap.")
    parser.add_argument("--country-code", default="ZZ", help="Input country code for ProductQuery metadata.")
    parser.add_argument("--retailer-name", default=None)
    parser.add_argument("--ean", default=None)
    args = parser.parse_args()

    product = ProductQuery(
        row_id=args.row_id,
        main_text=args.main_text,
        country_code=args.country_code,
        retailer_name=args.retailer_name,
        ean=args.ean,
    )
    builder = LivePageOfflineArtifactBuilder(
        OfflineCaptureConfig(output_dir=Path(args.output_dir))
    )
    artifact = builder.capture_url(args.url, artifact_dir=args.artifact_dir, product=product)
    print(json.dumps(artifact.to_dict(), indent=2, ensure_ascii=False))
    print(f"\nOpen offline HTML: {artifact.offline_html_path}")


if __name__ == "__main__":
    main()
