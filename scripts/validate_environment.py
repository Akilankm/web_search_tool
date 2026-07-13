#!/usr/bin/env python3
"""Validate strict three-stage runtime invariants without network calls."""

from __future__ import annotations

import argparse
import json
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
            "without network access."
        )
    )
    parser.add_argument("--env-file", default=".env")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = validate_runtime_environment(args.env_file)
    except EnvironmentValidationError as exc:
        print(
            json.dumps({"status": "invalid", "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 2

    print(json.dumps({"status": "valid", **report.to_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
