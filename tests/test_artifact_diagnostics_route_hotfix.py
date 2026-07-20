from __future__ import annotations

import pandas as pd

from src.product_evidence_harness import artifact_diagnostics


def test_artifact_mindmap_enumerates_search_stage_records() -> None:
    nodes_df, edges_df = artifact_diagnostics._build_mindmap(
        result={
            "product": {
                "main_text": "Example product",
                "country_code": "CH",
                "retailer_name": None,
                "ean": None,
            },
            "product_identification": {
                "resolution_status": "RESOLVED",
                "leading_hypothesis": {"canonical_name": "Example product"},
            },
            "job_status": "COMPLETED",
            "primary_url": "https://manufacturer.example/product",
            "primary_url_role": "manufacturer",
            "source_selection": {"selection_reason": "Official exact product page"},
            "primary_url_acceptance": {"accepted": True},
            "url_delivery": {"delivered": True},
        },
        belief={},
        search_steps_df=pd.DataFrame(
            [
                {"name": "manufacturer_primary"},
                {"name": "country_alternative"},
                {"name": "global_fallback"},
            ]
        ),
        candidates_df=pd.DataFrame(),
        business_steps_df=pd.DataFrame(),
        visual_summary={},
    )

    search_label = nodes_df.loc[nodes_df["node_id"] == "search", "label"].iloc[0]
    assert "manufacturer_primary" in search_label
    assert "country_alternative" in search_label
    assert "global_fallback" in search_label
    assert not edges_df.empty
