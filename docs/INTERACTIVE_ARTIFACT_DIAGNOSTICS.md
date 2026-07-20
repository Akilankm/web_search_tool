# Interactive Artifact Diagnostics

`notebooks/03_artifact_diagnostics.ipynb` is the primary human exploration surface for one completed product artifact.

It is intentionally **not** a sequence of static charts and large DataFrames. The notebook reconstructs the observable agent process once and presents it as a compact tabbed Plotly workspace.

## Input

Set `ARTIFACT_PATH` to either the product artifact directory or any file inside it:

```python
ARTIFACT_PATH = PROJECT_ROOT / "data" / "artifacts" / "ROW-001"
RUN_DIAGNOSTICS = True
```

All of these resolve to the same product artifact:

```text
data/artifacts/ROW-001/
data/artifacts/ROW-001/orchestrated_result.json
data/artifacts/ROW-001/candidates.csv
data/artifacts/ROW-001/business_judgement_review.md
```

The diagnostics notebook is offline. It does not call the agent service, browser, SerpAPI or enterprise LLM.

## Primary output

The notebook writes:

```text
data/artifacts/<row_id>/artifact_diagnostics_interactive.html
```

The HTML is self-contained and embeds Plotly JavaScript. It does not require internet access and can be opened independently of Jupyter.

## Interactive workspace

### Decision Map

Use this first to understand the complete observable path:

```text
input
→ product interpretation
→ search route
→ candidate validation
→ text and visual evidence
→ source authority
→ business judgments
→ final outcome
```

Interactions:

- hover a node for its full recorded detail;
- pan and zoom into dense sections;
- hide or isolate process groups from the legend;
- reset the view from the Plotly toolbar.

### Judgment Timeline

This is the primary human-equivalence view. Each recorded judgment exposes on hover:

- business question;
- observable evidence considered;
- evidence sources;
- agent judgment;
- explicit business rule;
- rejected alternative and reason;
- resulting next action;
- visual-evidence use;
- confidence and final outcome.

Ask the human coder to find the first step where their judgment differs. That first divergence becomes the next development requirement.

### Candidates

The candidate explorer compares URLs using requested-feature coverage and recorded confidence.

Interactions:

- use the dropdown to focus on selected, eligible or rejected candidates;
- click legend items to isolate decision classes;
- hover a candidate to inspect URL, source role, identity state, browser state, scrapability, decision reasons, rejection reasons and missing features;
- box-select a region to compare similar candidates.

The visual is an investigation aid. It does not replace the strict deterministic URL acceptance gates.

### Evidence

The evidence explorer is a click-to-zoom hierarchy:

```text
all evidence
→ extraction method
→ source
→ requested feature
```

This makes text, browser and visual evidence explorable without presenting a large feature table. Hover the feature level to see the coded value, status, confidence, evidence text/location and source URL.

### Artifacts

The artifact map is a click-to-zoom treemap grouped by file type. Tile area follows file size. Hover a file to see its purpose, path, size and whether it belongs to the formal artifact contract.

## Secondary outputs

The notebook can also write:

```text
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

These remain useful for audit and export. They are deliberately not rendered as large notebook tables because the interactive HTML is the primary comprehension layer.

## Dependency boundary

Interactive diagnostics use:

```text
plotly
ipywidgets
```

These are notebook dependencies only. They are not added to `requirements/agent.txt`, and the production agent container must not import `interactive_artifact_diagnostics.py` during startup.

## Trust boundary

The dashboard visualizes only recorded artifact data:

```text
observable evidence
→ explicit business rule
→ recorded judgment
→ resulting action
```

It does not expose or reconstruct hidden chain-of-thought. Empty or missing artifact fields remain visibly absent rather than being invented.
