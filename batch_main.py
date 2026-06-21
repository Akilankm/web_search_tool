"""
Batch processor for product URL finding with parallel workers.

Processes products concurrently using ThreadPoolExecutor for 2-3x speedup.
With paid SerpAPI account, rate-limiting is not a concern.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm.auto import tqdm
from datetime import datetime
from rich import print
import pandas as pd
from rich.traceback import install as install_rich_traceback

from src.serp_hybrid_url_finder import (
    CSVProductIO,
    HybridProductURLFinderPipeline,
    PipelineConfig,
    ProductQuery,
    RichPrinter,
    SerpAPIConfig,
    configure_logging,
)

# Install rich traceback for better error display in concurrent environments
install_rich_traceback()

configure_logging('INFO')
printer = RichPrinter()

serp_config = SerpAPIConfig.from_env(
    country_code='CH',
    no_cache=False,
)

pipeline_config = PipelineConfig(
    max_organic_calls=3,
    max_ai_mode_calls=2,
    max_candidates_for_ai=18,
    run_ai_repair=True,
    repair_confidence_threshold=0.80,
    scrape_enabled=True,
    require_scrapable_final=True,
    max_urls_to_scrape=10,
    crawl_headless=True,
    allow_global_fallback=True
)

pipeline = HybridProductURLFinderPipeline(
    serp_config=serp_config,
    pipeline_config=pipeline_config,
)

# ============================================================================
# Data Loading
# ============================================================================

df = pd.read_excel(
    './data/ORELL_FUESSLI_MONTHLY_O3Q-_Switzerland.xlsx',
    sheet_name='Sheet1',
    engine='openpyxl'
)

print(f"[bold cyan]Loaded {len(df)} products[/bold cyan]")
print(df.head())
print(f"Columns: {list(df.columns)}")

# ============================================================================
# Worker Function
# ============================================================================

def process_product(index: int, row: pd.Series, pipeline: HybridProductURLFinderPipeline) -> dict:
    """
    Process a single product: run pipeline and return results.
    
    Args:
        index: Row index in DataFrame
        row: Pandas Series with product data
        pipeline: HybridProductURLFinderPipeline instance
        
    Returns:
        Dictionary with results, or error info on failure
    """
    try:
        product = ProductQuery(
            row_id=f'data{index+1:03d}',
            main_text=row['MAIN_TEXT'],
            country_code=row['COUNTRY'],
            retailer_name=row.get('RETAILER'),  # Use actual retailer from data, not hardcoded 'None'
            ean=row.get('EAN'),
        )
        
        trace = pipeline.run(product, return_trace=True)
        
        return {
            'index': index,
            'status': 'success',
            'MAIN_TEXT': row['MAIN_TEXT'],
            'COUNTRY': row['COUNTRY'],
            'RETAILER': row.get('RETAILER'),
            'EAN': row.get('EAN'),
            'PRODUCT_URL': trace.best_match.product_url,
            'CONFIDENCE': trace.best_match.confidence,
            'VALIDATION_STATUS': trace.best_match.validation_status,
            'IDENTITY_STATUS': trace.best_match.identity_status,
            'RETAILER_CHECK': trace.best_match.retailer_check,
            'JUSTIFICATION': trace.best_match.justification,
            'error': None,
        }
    
    except Exception as e:
        # Capture error but don't crash the batch
        return {
            'index': index,
            'status': 'error',
            'MAIN_TEXT': row['MAIN_TEXT'],
            'COUNTRY': row['COUNTRY'],
            'RETAILER': row.get('RETAILER'),
            'EAN': row.get('EAN'),
            'PRODUCT_URL': None,
            'CONFIDENCE': 0.0,
            'VALIDATION_STATUS': 'UNKNOWN',
            'IDENTITY_STATUS': 'UNKNOWN',
            'RETAILER_CHECK': 'UNKNOWN',
            'JUSTIFICATION': f'Error: {str(e)}',
            'error': str(e),
        }


# ============================================================================
# Batch Processing with ThreadPoolExecutor
# ============================================================================

def process_batch_parallel(df: pd.DataFrame, pipeline: HybridProductURLFinderPipeline, max_workers: int = 2) -> pd.DataFrame:
    """
    Process all products in parallel using ThreadPoolExecutor.
    
    Args:
        df: DataFrame with product data
        pipeline: HybridProductURLFinderPipeline instance
        max_workers: Number of concurrent worker threads (default 2 for safety)
        
    Returns:
        DataFrame with results
    """
    results = []
    start_time = datetime.now()
    
    print(f"\n[bold cyan]Starting batch processing with {max_workers} workers[/bold cyan]")
    print(f"Total products: {len(df)}")
    print(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(process_product, index, row, pipeline): index
            for index, row in df.iterrows()
        }
        
        # Process results as they complete
        with tqdm(total=len(futures), desc="Processing products") as pbar:
            for future in as_completed(futures):
                index = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update progress bar with status
                    if result['status'] == 'success':
                        pbar.update(1)
                        pbar.set_postfix({
                            'success': sum(1 for r in results if r['status'] == 'success'),
                            'errors': sum(1 for r in results if r['status'] == 'error'),
                        })
                    else:
                        pbar.update(1)
                        pbar.set_postfix({
                            'success': sum(1 for r in results if r['status'] == 'success'),
                            'errors': sum(1 for r in results if r['status'] == 'error'),
                        })
                        print(f"\n⚠️  Product {index+1} ({result['MAIN_TEXT'][:50]}): {result['error']}")
                        
                except Exception as e:
                    pbar.update(1)
                    print(f"\n❌ Worker error on product {index+1}: {str(e)}")
    
    # Sort results by original index
    results.sort(key=lambda x: x['index'])
    output_df = pd.DataFrame(results)
    
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()
    
    print(f"\n[bold green]✓ Batch processing complete[/bold green]")
    print(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f}m)")
    print(f"Avg time/product: {elapsed/len(df):.1f}s")
    print(f"Success: {sum(1 for r in results if r['status'] == 'success')}/{len(results)}")
    
    return output_df


# ============================================================================
# Main Execution
# ============================================================================

if __name__ == '__main__':
    # Process products in parallel with 2 workers
    output_df = process_batch_parallel(df, pipeline, max_workers=2)
    
    # Drop error column from output (keep only the result columns)
    output_df_clean = output_df.drop(columns=['index', 'status', 'error'], errors='ignore')
    
    # Write results to Excel
    output_file = './data/ORELL_FUESSLI_MONTHLY_O3Q-_Switzerland_output.xlsx'
    output_df_clean.to_excel(output_file, index=False, engine='openpyxl')
    print(f"\n[bold cyan]Results written to: {output_file}[/bold cyan]")
    
    # Print summary statistics
    print(f"\n[bold]Summary Statistics:[/bold]")
    print(f"  Total products: {len(output_df)}")
    print(f"  Successful: {sum(output_df['status'] == 'success')}")
    print(f"  Failed: {sum(output_df['status'] == 'error')}")
    if 'CONFIDENCE' in output_df.columns:
        print(f"  Avg confidence: {output_df[output_df['status'] == 'success']['CONFIDENCE'].mean():.3f}")
