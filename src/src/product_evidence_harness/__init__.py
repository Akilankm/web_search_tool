"""Compatibility bridge for legacy ``src.product_evidence_harness`` imports.

When notebooks add ``<repo>/src`` to ``sys.path``, the real package is available
as ``product_evidence_harness``. This bridge exposes the same package directory
under the legacy ``src.product_evidence_harness`` namespace so old internal
imports continue to resolve until they are fully migrated.
"""

from __future__ import annotations

from pathlib import Path

_REAL_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "product_evidence_harness"
__path__ = [str(_REAL_PACKAGE_DIR)]
