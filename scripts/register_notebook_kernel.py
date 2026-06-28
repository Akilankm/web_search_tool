"""Register the project in-project virtualenv as a Jupyter kernel."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KERNEL_NAME = "product-evidence-harness"
DISPLAY_NAME = "Product Evidence Harness (.venv)"


def main() -> None:
    venv_python = PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    python_exe = str(venv_python if venv_python.exists() else Path(sys.executable))
    subprocess.run(
        [
            python_exe,
            "-m",
            "ipykernel",
            "install",
            "--user",
            "--name",
            KERNEL_NAME,
            "--display-name",
            DISPLAY_NAME,
        ],
        check=True,
    )
    print(f"Registered Jupyter kernel: {DISPLAY_NAME} [{KERNEL_NAME}]")
    print(f"Python interpreter: {python_exe}")


if __name__ == "__main__":
    main()
