import ast
from pathlib import Path

import nbformat
import pytest

from product_url.resolver import Budgets, ProductInput, build_queries, canonical_url, evaluate

ROOT = Path(__file__).resolve().parents[1]


def test_input_contract() -> None:
    item = ProductInput("  LEGO 75379 R2-D2  ", "gb", ean="1234 5678 9012 3")
    assert item.main_text == "LEGO 75379 R2-D2"
    assert item.country_code == "GB"
    assert item.ean == "1234567890123"
    with pytest.raises(ValueError):
        ProductInput("", "GB")


def test_query_budget_and_identifier_lock() -> None:
    item = ProductInput("PKM ME04 BOOSTER", "CH", ean="196214141070", retailer_name="Toy Shop")
    queries = build_queries(item, {"brand": "Pokemon", "model": "ME04", "search_queries": []}, 3)
    assert len(queries) == 3
    assert all(item.ean in query for query in queries[:2])


def test_canonical_url_removes_tracking() -> None:
    assert canonical_url("https://shop.example/product/1?utm_source=x&keep=yes#frag") == "https://shop.example/product/1?keep=yes"


def test_exact_candidate_fixture() -> None:
    item = ProductInput("LEGO R2-D2 75379", "GB", ean="1234567890123")
    candidate = {
        "url": "https://shop.example/products/lego-r2d2-75379",
        "final_url": "https://shop.example/products/lego-r2d2-75379",
        "title": "LEGO R2-D2 75379",
        "page_title": "LEGO R2-D2 75379",
        "markdown": "LEGO R2-D2 75379 EAN 1234567890123 price add to cart",
        "html": '<script type="application/ld+json">{"@type":"Product"}</script>',
        "crawl_success": True,
    }
    evaluate(item, {"key_terms": ["lego", "r2", "d2", "75379"]}, candidate)
    assert candidate["identifier_match"] is True
    assert candidate["product_page"] is True
    assert not candidate["blockers"]


def test_pca_environment_contract_is_consistent() -> None:
    paths = [ROOT / ".env.example", ROOT / "README.md", ROOT / "src/product_url/resolver.py"]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "PCA_LMM" not in text
    for name in (
        "PCA_LLM_API_KEY",
        "PCA_LLM_API_VERSION",
        "PCA_LLM_ENDPOINT",
        "PCA_LLM_DEPLOYMENT",
        "PCA_LLM_CONSUMER_ID",
        "PCA_LLM_MAX_RETRIES",
    ):
        assert name in text


def test_notebooks_are_plain_and_compilable() -> None:
    forbidden = ("streamlit", "fastapi", "docker", "nest_asyncio", "monkeypatch", "asyncio.run")
    notebooks = sorted((ROOT / "notebooks").glob("*.ipynb"))
    assert [path.name for path in notebooks] == [
        "01_resolve_one_product.ipynb",
        "02_resolve_csv_batch.ipynb",
    ]
    for path in notebooks:
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)
        code = "\n".join(str(cell.source) for cell in notebook.cells if cell.cell_type == "code")
        assert not any(token in code.casefold() for token in forbidden)
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type == "code":
                ast.parse(str(cell.source), filename=f"{path.name}:cell-{index}")
