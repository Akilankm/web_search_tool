from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_uses_repository_local_artifact_directory() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert compose.count("./data/artifacts:/data/artifacts") == 2
    assert "./data/artifacts:/app/output" in compose
    assert "PRODUCT_HARNESS_OUTPUT_DIR: /data/artifacts" in compose
    assert "./artifacts:/data/artifacts" not in compose


def test_startup_creates_fresh_clone_runtime_layout_and_uses_invoking_user() -> None:
    startup = (ROOT / "scripts" / "azureml_startup.sh").read_text(encoding="utf-8")

    assert "mkdir -p data/artifacts data/runtime inputs/private secrets" in startup
    assert 'RUNTIME_UID="$(id -u)"' in startup
    assert 'RUNTIME_GID="$(id -g)"' in startup
    assert "Artifacts will be written under $PROJECT_DIR/data/artifacts/<row_id>/" in startup


def test_generated_runtime_data_is_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "data/artifacts/" in gitignore
    assert "data/runtime/" in gitignore
