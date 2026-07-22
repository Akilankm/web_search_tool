#!/usr/bin/env python3
"""Resolve free host ports without mutating the credential-bearing .env file."""

from __future__ import annotations

import argparse
import os
import socket
from pathlib import Path
from typing import Mapping


DEFAULT_AGENT_PORT = 8788
DEFAULT_UI_PORT = 8501
MAX_SCAN = 200


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def port_is_available(port: int, host: str = "0.0.0.0") -> bool:
    if not 1 <= int(port) <= 65535:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, int(port)))
        except OSError:
            return False
    return True


def select_available_port(preferred: int, *, reserved: set[int] | None = None, max_scan: int = MAX_SCAN) -> int:
    reserved = reserved or set()
    for candidate in range(int(preferred), min(65535, int(preferred) + int(max_scan)) + 1):
        if candidate not in reserved and port_is_available(candidate):
            return candidate
    raise RuntimeError(f"no free TCP port found from {preferred} through {min(65535, preferred + max_scan)}")


def resolve_ports(env_values: Mapping[str, str], process_env: Mapping[str, str] | None = None) -> dict[str, int]:
    process_env = process_env or os.environ
    preferred_agent = _port(process_env.get("PRODUCT_URL_HOST_PORT") or env_values.get("PRODUCT_URL_HOST_PORT"), DEFAULT_AGENT_PORT)
    preferred_ui = _port(process_env.get("PRODUCT_URL_UI_PORT") or env_values.get("PRODUCT_URL_UI_PORT"), DEFAULT_UI_PORT)
    agent_port = select_available_port(preferred_agent)
    ui_port = select_available_port(preferred_ui, reserved={agent_port})
    return {"PRODUCT_URL_HOST_PORT": agent_port, "PRODUCT_URL_UI_PORT": ui_port}


def write_runtime_env(path: Path, ports: Mapping[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(f"{key}={int(value)}\n" for key, value in ports.items()), encoding="utf-8")
    temporary.replace(path)


def _port(value: str | None, default: int) -> int:
    try:
        parsed = int(str(value or default).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid TCP port value: {value!r}") from exc
    if not 1 <= parsed <= 65535:
        raise ValueError(f"TCP port must be between 1 and 65535: {parsed}")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--output", default=".runtime/ports.env")
    args = parser.parse_args()

    ports = resolve_ports(parse_env_file(Path(args.env_file)))
    write_runtime_env(Path(args.output), ports)
    for key, value in ports.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
