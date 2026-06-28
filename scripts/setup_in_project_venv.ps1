$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

if (-not (Get-Command pdm -ErrorAction SilentlyContinue)) {
    Write-Host "PDM is not installed or not on PATH. Install it first:" -ForegroundColor Red
    Write-Host "  py -m pip install --user pdm"
    exit 1
}

Write-Host "Project root: $ProjectRoot"
Write-Host "Configuring PDM to use an in-project virtual environment at .venv/"
pdm config --local python.use_venv true
pdm config --local venv.in_project true
pdm config --local venv.with_pip true
pdm config --local venv.prompt 'product-evidence-harness-py{python_version}'

Write-Host "Installing runtime + notebook + dev dependencies into .venv/"
pdm install -G notebook -G dev

Write-Host "Ensuring pip is available inside .venv/ for emergency/manual installs"
pdm run python -m ensurepip --upgrade | Out-Null

Write-Host "Registering Jupyter kernel"
pdm run python scripts/register_notebook_kernel.py

Write-Host "Validating imports/tests"
pdm run python -m compileall -q src main.py batch_main.py
pdm run pytest -q

Write-Host ""
Write-Host "Done. Use one of:"
Write-Host "  pdm run python main.py --help"
Write-Host "  pdm run python batch_main.py --help"
Write-Host "  pdm venv activate | Invoke-Expression    # optional shell activation"
Write-Host "Notebook kernel: Product Evidence Harness (.venv)"
