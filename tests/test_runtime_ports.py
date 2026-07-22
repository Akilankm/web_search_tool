from __future__ import annotations

import importlib.util
import socket
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "resolve_ports.py"
SPEC = importlib.util.spec_from_file_location("resolve_ports", MODULE_PATH)
assert SPEC and SPEC.loader
resolve_ports = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resolve_ports)


def test_select_available_port_skips_an_occupied_preferred_port() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(("0.0.0.0", 0))
        preferred = occupied.getsockname()[1]
        selected = resolve_ports.select_available_port(preferred, max_scan=20)
    assert selected != preferred
    assert selected > preferred


def test_runtime_ports_are_written_outside_the_credential_env(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PRODUCT_URL_HOST_PORT=8788\n"
        "PRODUCT_URL_UI_PORT=8501\n"
        "PCA_LLM_API_KEY=nokey\n",
        encoding="utf-8",
    )
    original = env_path.read_text(encoding="utf-8")
    ports = resolve_ports.resolve_ports(
        resolve_ports.parse_env_file(env_path),
        process_env={},
    )
    output = tmp_path / ".runtime" / "ports.env"
    resolve_ports.write_runtime_env(output, ports)

    assert env_path.read_text(encoding="utf-8") == original
    assert "PCA_LLM_API_KEY" not in output.read_text(encoding="utf-8")
    assert set(ports) == {"PRODUCT_URL_HOST_PORT", "PRODUCT_URL_UI_PORT"}
    assert ports["PRODUCT_URL_HOST_PORT"] != ports["PRODUCT_URL_UI_PORT"]


def test_process_environment_can_override_preferred_ports() -> None:
    ports = resolve_ports.resolve_ports(
        {"PRODUCT_URL_HOST_PORT": "8788", "PRODUCT_URL_UI_PORT": "8501"},
        process_env={"PRODUCT_URL_HOST_PORT": "18788", "PRODUCT_URL_UI_PORT": "18501"},
    )
    assert ports["PRODUCT_URL_HOST_PORT"] >= 18788
    assert ports["PRODUCT_URL_UI_PORT"] >= 18501
