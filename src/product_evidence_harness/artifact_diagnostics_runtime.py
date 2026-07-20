from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_PATCHED = False


class _EnumeratedRecordsFrame:
    """Proxy a DataFrame so the legacy mindmap loop receives (index, row) pairs."""

    def __init__(self, frame: Any) -> None:
        self._frame = frame

    def to_dict(self, *args: Any, **kwargs: Any) -> Any:
        records = self._frame.to_dict(*args, **kwargs)
        orient = kwargs.get("orient")
        if orient is None and args:
            orient = args[0]
        if orient != "records":
            return records

        if all(
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[0], int)
            and isinstance(item[1], Mapping)
            for item in records
        ):
            return records

        return list(enumerate(records))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._frame, name)


def apply_artifact_diagnostics_runtime_patch() -> None:
    """Repair notebook mindmap iteration without making notebook libraries agent dependencies.

    The production agent image intentionally excludes matplotlib because chart rendering belongs
    to the notebook/diagnostic surface. The global compatibility bootstrap is imported by Uvicorn,
    so a missing optional notebook dependency must not prevent the agent from binding its API port.
    """

    global _PATCHED
    if _PATCHED:
        return

    try:
        from src.product_evidence_harness import artifact_diagnostics as diagnostics
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".", 1)[0] in {"matplotlib"}:
            return
        raise

    original = diagnostics._build_mindmap
    if getattr(original, "_artifact_route_enumeration_fixed", False):
        _PATCHED = True
        return

    def fixed_build_mindmap(*args: Any, **kwargs: Any):
        search_steps_df = kwargs.get("search_steps_df")
        if search_steps_df is not None:
            kwargs["search_steps_df"] = _EnumeratedRecordsFrame(search_steps_df)
        return original(*args, **kwargs)

    fixed_build_mindmap._artifact_route_enumeration_fixed = True  # type: ignore[attr-defined]
    diagnostics._build_mindmap = fixed_build_mindmap
    _PATCHED = True
