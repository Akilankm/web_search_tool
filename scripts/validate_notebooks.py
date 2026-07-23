#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

import nbformat


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"
REQUIRED = {
    "01_resolve_one_product.ipynb",
    "02_resolve_csv_batch.ipynb",
}
FORBIDDEN_CODE = {
    "nest" + "_asyncio",
    "streamlit",
    "fastapi",
    "docker compose",
    "product_url_v2." + "api",
    "browser" + "_service",
}
FORBIDDEN_RUNTIME_OPTION_FRAGMENTS = {
    '"browser_enabled":',
    '"browser_required":',
    '"reasoning_enabled":',
    '"reasoning_required":',
}
REQUIRED_OUTPUT_COLUMNS = {
    "MAIN_TEXT",
    "COUNTRY",
    "RETAILER",
    "EAN",
    "PROP_PG_NAME",
    "CANDIDATE_URLS",
    "PRODUCT_URL",
    "CONFIDENCE",
    "VALIDATION_STATUS",
    "IDENTITY_STATUS",
    "RETAILER_CHECK",
    "JUSTIFICATION",
    "ARTIFACT_DIR",
}


def main() -> int:
    actual = {path.name for path in NOTEBOOKS.glob("*.ipynb")}
    missing = REQUIRED - actual
    if missing:
        raise SystemExit(f"Missing supported notebooks: {sorted(missing)}")

    for path in sorted(NOTEBOOKS.glob("*.ipynb")):
        notebook = nbformat.read(path, as_version=4)
        nbformat.validate(notebook)

        combined = "\n".join(str(cell.source) for cell in notebook.cells)
        code_source = "\n".join(
            str(cell.source) for cell in notebook.cells if cell.cell_type == "code"
        )
        lowered_code = code_source.casefold()
        offenders = sorted(term for term in FORBIDDEN_CODE if term in lowered_code)
        if offenders:
            raise SystemExit(f"{path}: forbidden runtime code: {offenders}")

        duplicated_modes = sorted(
            fragment
            for fragment in FORBIDDEN_RUNTIME_OPTION_FRAGMENTS
            if fragment in code_source
        )
        if duplicated_modes:
            raise SystemExit(
                f"{path}: runtime modes must come from .env/config, not notebook options: "
                f"{duplicated_modes}"
            )

        missing_output_columns = sorted(
            column for column in REQUIRED_OUTPUT_COLUMNS if column not in code_source
        )
        if missing_output_columns:
            raise SystemExit(
                f"{path}: missing required submission columns: {missing_output_columns}"
            )

        if "ProductURLOrchestrator" not in combined:
            raise SystemExit(f"{path}: must call ProductURLOrchestrator directly")
        if "evaluate_acceptance" not in combined:
            raise SystemExit(f"{path}: must consume the canonical acceptance policy")

        for index, cell in enumerate(notebook.cells):
            if cell.cell_type != "code":
                continue
            try:
                ast.parse(str(cell.source), filename=f"{path.name}:cell-{index}")
            except SyntaxError as exc:
                raise SystemExit(f"{path}: invalid Python in code cell {index}: {exc}") from exc

        print(f"Validated {path.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
