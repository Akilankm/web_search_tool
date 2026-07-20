from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATHS = tuple(sorted((ROOT / "notebooks").glob("*.ipynb")))


def test_every_supported_notebook_code_cell_compiles() -> None:
    assert [path.name for path in NOTEBOOK_PATHS] == [
        "01_single_product.ipynb",
        "02_batch_products.ipynb",
        "03_artifact_diagnostics.ipynb",
    ]

    for notebook_path in NOTEBOOK_PATHS:
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        code_cells = [
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell.get("cell_type") == "code"
        ]
        assert code_cells
        for index, source in enumerate(code_cells, start=1):
            compile(source, f"{notebook_path.name}:cell-{index}", "exec")
