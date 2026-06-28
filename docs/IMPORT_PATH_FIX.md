# Import Path Fix

The package uses the standard `src/` layout. Runtime imports must use:

```python
from product_evidence_harness import ProductEvidenceHarness
from product_evidence_harness.config import HarnessConfig
```

They must not use:

```python
from src.product_evidence_harness import ...
```

In notebooks, add the repository `src` directory to `sys.path`:

```python
from pathlib import Path
import sys

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
```

Then import normally:

```python
from product_evidence_harness import ProductEvidenceHarness, ProductQuery
```

A regression test now prevents `src.product_evidence_harness` imports from coming back.
