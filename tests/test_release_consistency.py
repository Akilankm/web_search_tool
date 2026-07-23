from importlib.metadata import version
from pathlib import Path

from product_url_v2 import ACCEPTANCE_POLICY_VERSION, __version__


ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent() -> None:
    assert __version__ == "2.0.0"
    assert version("product-url-resolver") == __version__


def test_notebook_entry_points_are_present() -> None:
    assert (ROOT / "notebooks" / "01_resolve_one_product.ipynb").is_file()
    assert (ROOT / "notebooks" / "02_resolve_csv_batch.ipynb").is_file()
    assert (ROOT / "environment.yml").is_file()


def test_service_infrastructure_is_absent() -> None:
    forbidden_paths = (
        ROOT / "apps" / "product_url_ui.py",
        ROOT / "src" / "product_url_v2" / "api.py",
        ROOT / "src" / "product_url_v2" / "browser_service.py",
        ROOT / "src" / "product_url_v2" / "ui_presenter.py",
        ROOT / "docker-compose.yml",
        ROOT / "scripts" / "start.sh",
        ROOT / "scripts" / "run_ui.sh",
        ROOT / "scripts" / "resolve_ports.py",
    )
    assert not [path for path in forbidden_paths if path.exists()]


def test_runtime_dependencies_are_base_only() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").casefold()
    for forbidden in ("fastapi", "streamlit", "uvicorn", "docker"):
        assert forbidden not in pyproject


def test_documentation_declares_notebook_release() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Version: `2.0.0`" in readme
    assert f"Acceptance policy: `{ACCEPTANCE_POLICY_VERSION}`" in readme
    assert "notebooks/01_resolve_one_product.ipynb" in readme
    assert "notebooks/02_resolve_csv_batch.ipynb" in readme
