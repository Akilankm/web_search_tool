#!/usr/bin/env python3
"""Validate strict three-stage runtime invariants without network calls."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from product_evidence_harness.environment import EnvironmentValidationError  # noqa: E402
from product_evidence_harness.three_stage_environment import (  # noqa: E402
    validate_runtime_environment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate .env security, SerpAPI configuration, LLM configuration, "
            "the exact three-credit search campaign, and strict final URL gates "
            "without network access. Azure ML cloudfiles permissions are handled automatically."
        )
    )
    parser.add_argument("--env-file", default=".env")
    parser.add_argument(
        "--strict-env-permissions",
        action="store_true",
        help="Require POSIX mode 0600 even on Azure ML cloudfiles mounts",
    )
    return parser.parse_args()


def prepare_permission_policy(path: Path, *, strict: bool) -> tuple[bool, str]:
    if os.name != "posix":
        return False, "platform-default"
    try:
        path.chmod(0o600)
    except OSError:
        pass
    mode = stat.S_IMODE(path.stat().st_mode)
    if not mode & 0o077:
        return True, "strict-0600"
    cloudfiles = "/cloudfiles/" in path.expanduser().absolute().as_posix().lower()
    if cloudfiles and not strict:
        return False, "azureml-cloudfiles-auto-fallback"
    return True, "strict-rejected-if-broad"


def main() -> int:
    args = parse_args()
    env_path = Path(args.env_file).expanduser()
    if not env_path.is_file():
        print(json.dumps({"status": "invalid", "error": ".env is missing"}, indent=2), file=sys.stderr)
        return 2

    strict_permissions, permission_policy = prepare_permission_policy(
        env_path,
        strict=args.strict_env_permissions,
    )
    try:
        report = validate_runtime_environment(
            env_path,
            strict_file_permissions=strict_permissions,
        )
    except (EnvironmentValidationError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "invalid",
                    "env_permission_policy": permission_policy,
                    "error": str(exc),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "status": "valid",
                "env_permission_policy": permission_policy,
                **report.to_dict(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
