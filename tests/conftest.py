"""Pytest bootstrap.

The project uses PDM with ``distribution = false``, so the ``serp_hybrid_url_finder``
package is not installed into site-packages. Adding ``src`` to ``sys.path`` lets the
tests import it directly (this mirrors the ``pythonpath = ["src"]`` pytest setting and
keeps the suite runnable even when invoked without the project's pytest config).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
