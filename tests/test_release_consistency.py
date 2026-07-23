from importlib.metadata import version
from pathlib import Path

from product_url_v2 import ACCEPTANCE_POLICY_VERSION, __version__
from product_url_v2.api import VERSION as API_VERSION
from product_url_v2.browser_service import VERSION as BROWSER_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_services() -> None:
    assert __version__ == "1.3.0"
    assert API_VERSION == __version__
    assert BROWSER_VERSION == __version__
    assert version("product-url-resolver") == __version__


def test_ui_consumes_canonical_policy_key_without_legacy_alias() -> None:
    ui = (ROOT / "apps" / "product_url_ui.py").read_text(encoding="utf-8")

    assert "acceptance_policy" in ui
    assert "acceptance_policy_module" in ui
    assert "url_delivery_policy" not in ui


def test_documentation_declares_canonical_release() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Version: `1.3.0`" in readme
    assert f"Acceptance policy: `{ACCEPTANCE_POLICY_VERSION}`" in readme
    assert "src/product_url_v2/policy.py" in readme
