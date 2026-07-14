from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_PATH = ROOT / "notebooks" / "01_run_product_evidence.ipynb"


def test_every_notebook_code_cell_compiles() -> None:
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    code_cells = [
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell.get("cell_type") == "code"
    ]

    assert code_cells
    for index, source in enumerate(code_cells, start=1):
        compile(source, f"{NOTEBOOK_PATH.name}:cell-{index}", "exec")
