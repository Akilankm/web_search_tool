from __future__ import annotations

from pathlib import Path

from src.product_evidence_harness.one_credit_pipeline import OneCreditConfig


ROOT = Path(__file__).resolve().parents[1]


def test_compose_uses_repository_local_artifact_directory() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert compose.count("./data/artifacts:/data/artifacts") == 2
    assert "PRODUCT_HARNESS_OUTPUT_DIR: /data/artifacts" in compose
    assert "./artifacts:/data/artifacts" not in compose
    assert "/app/output" not in compose


def test_one_credit_writer_inherits_configured_output_directory() -> None:
    assert OneCreditConfig().output_dir == ""


def test_startup_is_single_command_azureml_bootstrap() -> None:
    startup = (ROOT / "scripts" / "azureml_startup.sh").read_text(encoding="utf-8")

    assert "mkdir -p data/artifacts data/runtime data/batch_runs inputs/private secrets" in startup
    assert 'RUNTIME_UID="$(id -u)"' in startup
    assert 'RUNTIME_GID="$(id -g)"' in startup
    assert "--env-permission-mode" in startup
    assert "docker compose down --remove-orphans" in startup
    assert "--force-recreate" in startup
    assert "--build" in startup
    assert "data/runtime/stack_health.json" in startup
    assert "Product evidence platform is ready." in startup
    assert "Available FEATURE_SET values:" in startup
    assert "01_single_product.ipynb" in startup
    assert "02_batch_products.ipynb" in startup
    assert "03_artifact_diagnostics.ipynb" in startup
    assert "run_leadership_demo.sh --install" in startup
    assert "forward port 8501 privately" in startup


def test_waiter_surfaces_configuration_errors_and_writes_health_snapshot() -> None:
    waiter = (ROOT / "scripts" / "wait_for_stack.py").read_text(encoding="utf-8")

    assert "extract_configuration_error" in waiter
    assert "Agent configuration validation failed" in waiter
    assert "stack_health.json" in waiter
    assert "Stack is healthy and notebook-ready." in waiter


def test_generated_runtime_data_is_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "data/artifacts/" in gitignore
    assert "data/runtime/" in gitignore
    assert "data/batch_runs/" in gitignore
