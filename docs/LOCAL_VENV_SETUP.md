# Local in-project virtual environment setup

This project is configured to use a repository-local virtual environment:

```text
web_search_tool/.venv/
```

This keeps CLI runs, notebooks, VS Code, and AzureML interactive sessions on the same interpreter.

## Why `.venv/` in the project?

PDM's current virtualenv behavior prefers virtual environments by default, and first install can create a venv under `<project_root>/.venv`. PDM also exposes project-level settings for `python.use_venv` and `venv.in_project`, so this repository pins that behavior in `pdm.toml`.

## One-command setup

Linux/macOS/Git Bash:

```bash
bash scripts/setup_in_project_venv.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_in_project_venv.ps1
```

The setup script does all of this:

```text
1. configures PDM local settings
2. creates/uses .venv/ inside the project
3. installs runtime + notebook + dev dependencies
4. registers the Jupyter kernel
5. validates compile + tests
```

## Manual setup

```bash
pdm config --local python.use_venv true
pdm config --local venv.in_project true
pdm config --local venv.with_pip true
pdm install -G notebook -G dev
pdm run python scripts/register_notebook_kernel.py
```

## Run commands without activating the venv

```bash
pdm run python main.py --help
pdm run python batch_main.py --help
pdm run pytest -q
```

## Optional activation

Linux/macOS/Git Bash:

```bash
eval $(pdm venv activate)
```

PowerShell:

```powershell
pdm venv activate | Invoke-Expression
```

## Notebook kernel

Select this kernel in Jupyter/VS Code:

```text
Product Evidence Harness (.venv)
```

Kernel name:

```text
product-evidence-harness
```

## Files that matter

```text
pyproject.toml             # dependencies and PDM scripts
pdm.toml                   # project-local PDM config for .venv
scripts/setup_in_project_venv.sh
scripts/setup_in_project_venv.ps1
scripts/register_notebook_kernel.py
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```
