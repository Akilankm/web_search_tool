from __future__ import annotations

import pandas as pd


_PATCHED = False


class _IndexedRecordFrame(pd.DataFrame):
    """Provide indexed records for the initial diagnostics implementation.

    The mindmap builder expects ``(index, record)`` pairs while a normal
    DataFrame returns only records for ``orient='records'``. Keeping this
    adapter isolated preserves the public diagnostics API and avoids changing
    any artifact data.
    """

    @property
    def _constructor(self):
        return _IndexedRecordFrame

    def to_dict(self, orient="dict", *args, **kwargs):
        records = super().to_dict(orient=orient, *args, **kwargs)
        if orient == "records":
            return list(enumerate(records))
        return records


def apply_artifact_diagnostics_compatibility() -> None:
    global _PATCHED
    if _PATCHED:
        return

    from src.product_evidence_harness import artifact_diagnostics as diagnostics

    original = diagnostics._build_mindmap
    if getattr(original, "_indexed_search_records_compatible", False):
        _PATCHED = True
        return

    def compatible_build_mindmap(
        *,
        result,
        belief,
        search_steps_df,
        candidates_df,
        business_steps_df,
        visual_summary,
    ):
        indexed_search_steps = _IndexedRecordFrame(search_steps_df.copy())
        return original(
            result=result,
            belief=belief,
            search_steps_df=indexed_search_steps,
            candidates_df=candidates_df,
            business_steps_df=business_steps_df,
            visual_summary=visual_summary,
        )

    compatible_build_mindmap._indexed_search_records_compatible = True
    diagnostics._build_mindmap = compatible_build_mindmap
    _PATCHED = True
