from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src" / "product_evidence_harness" / "artifact_diagnostics_runtime.py"


def _load_isolated_module():
    spec = importlib.util.spec_from_file_location("isolated_artifact_diagnostics_runtime", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optional_matplotlib_absence_does_not_break_agent_bootstrap(monkeypatch) -> None:
    module = _load_isolated_module()
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "src.product_evidence_harness" and "artifact_diagnostics" in tuple(fromlist or ()):
            error = ModuleNotFoundError("No module named 'matplotlib'")
            error.name = "matplotlib"
            raise error
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module.apply_artifact_diagnostics_runtime_patch()
    assert module._PATCHED is False


def test_unrelated_missing_dependency_is_not_suppressed(monkeypatch) -> None:
    module = _load_isolated_module()
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "src.product_evidence_harness" and "artifact_diagnostics" in tuple(fromlist or ()):
            error = ModuleNotFoundError("No module named 'unexpected_runtime_package'")
            error.name = "unexpected_runtime_package"
            raise error
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    try:
        module.apply_artifact_diagnostics_runtime_patch()
    except ModuleNotFoundError as exc:
        assert exc.name == "unexpected_runtime_package"
    else:
        raise AssertionError("Unexpected runtime dependency errors must not be hidden")
