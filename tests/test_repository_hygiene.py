from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_only_supported_notebook_remains() -> None:
    notebooks = sorted(path.name for path in (ROOT / "notebooks").glob("*.ipynb"))
    assert notebooks == ["01_run_product_evidence.ipynb"]


def test_supported_notebook_is_clean_and_renderable() -> None:
    notebook = json.loads((ROOT / "notebooks" / "01_run_product_evidence.ipynb").read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert notebook["cells"]
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell.get("execution_count") is None
            assert cell.get("outputs") == []


def test_obsolete_public_entry_points_are_removed() -> None:
    obsolete = [
        "main.py",
        "batch_main.py",
        "docs/README.md",
        "docs/SECURE_ENVIRONMENT.md",
        "examples/toy_feature_schema.json",
        "notebooks/00_notebook_gateway.ipynb",
        "notebooks/01_single_product_harness.ipynb",
        "notebooks/02_batch_product_harness.ipynb",
        "notebooks/03_offline_product_artifact.ipynb",
        "notebooks/04_review_artifact_reader.ipynb",
    ]
    assert [path for path in obsolete if (ROOT / path).exists()] == []


def test_final_docs_and_runtime_files_exist() -> None:
    required = [
        "README.md",
        ".env.example",
        "docker-compose.yml",
        "docker/agent.Dockerfile",
        "docker/browser.Dockerfile",
        "requirements/agent.txt",
        "requirements/browser.txt",
        "requirements/test.txt",
        "scripts/azureml_startup.sh",
        "scripts/preflight_azureml.py",
        "scripts/wait_for_stack.py",
        "docs/AZUREML_OPERATIONS.md",
        "docs/SECURITY.md",
        "examples/features_to_code.example.json",
        "inputs/private/toy_features.json",
    ]
    assert [path for path in required if not (ROOT / path).is_file()] == []


def test_default_toy_feature_schema_is_valid_and_intentional() -> None:
    path = ROOT / "inputs" / "private" / "toy_features.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert set(payload) == {"features_to_code"}
    names = [
        item if isinstance(item, str) else item["name"]
        for item in payload["features_to_code"]
    ]
    assert names == ["brand", "manufacturer", "minimum recommended age"]


def test_gitignore_tracks_only_the_approved_default_private_schema() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "inputs/private/*" in text
    assert "!inputs/private/toy_features.json" in text
    assert "inputs/private/\n" not in text


def test_dockerfiles_do_not_reference_missing_pdm_lock() -> None:
    for path in (ROOT / "docker").glob("*.Dockerfile"):
        text = path.read_text(encoding="utf-8")
        assert "pdm.lock" not in text
        assert "pdm install" not in text


def test_compose_exposes_only_the_agent() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '${AGENT_HOST_PORT:-8788}:8000' in text
    assert 'BROWSER_BASE_URL: http://browser:9000' in text
    assert 'condition: service_healthy' in text
    assert '9000:9000' not in text
    assert '/var/run/docker.sock' not in text


def test_readme_points_to_the_only_supported_paths() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "notebooks/01_run_product_evidence.ipynb" in text
    assert "scripts/azureml_startup.sh" in text
    assert "inputs/private/toy_features.json" in text
    assert "docs/AZUREML_OPERATIONS.md" in text
    assert "docs/SECURITY.md" in text
