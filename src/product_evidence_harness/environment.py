from __future__ import annotations

import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values, load_dotenv


class EnvironmentValidationError(ValueError):
    """Raised when runtime configuration violates a security or cost invariant."""


_PLACEHOLDER_MARKERS = (
    "your_",
    "your-",
    "replace_",
    "replace-",
    "changeme",
    "change_me",
    "example",
    "dummy",
    "placeholder",
    "<",
    ">",
)

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off"}
_ENV_KEY_PATTERN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


@dataclass(frozen=True, slots=True)
class EnvironmentValidationReport:
    env_file: str | None
    env_file_loaded: bool
    env_file_permissions_checked: bool
    serpapi_configured: bool
    llm_feature_reasoning_enabled: bool
    llm_configured: bool
    one_credit_contract_enforced: bool
    checks_passed: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a secret-free diagnostic payload safe for logs and artifacts."""
        return asdict(self)


def validate_runtime_environment(
    env_file: str | Path | None = ".env",
    *,
    require_serpapi: bool = True,
    enforce_one_credit: bool = True,
    strict_file_permissions: bool = True,
    environ: Mapping[str, str] | None = None,
) -> EnvironmentValidationReport:
    """Load and validate runtime configuration before any paid network call.

    The validator rejects placeholder SerpAPI secrets, malformed booleans and
    numbers, insecure local secret files, and settings that can violate the
    search-credit contract. Enterprise-provided LLM credentials and endpoint
    strings are treated as opaque values and are validated only for presence.
    Secret values are never included in returned diagnostics.
    """

    env_path = Path(env_file).expanduser() if env_file else None
    file_loaded = False
    permissions_checked = False
    checks: list[str] = []

    if env_path and env_path.exists():
        if env_path.is_symlink():
            raise EnvironmentValidationError(f"Refusing symlinked environment file: {env_path}")
        if not env_path.is_file():
            raise EnvironmentValidationError(f"Environment path is not a regular file: {env_path}")
        _validate_env_file_syntax(env_path)
        if strict_file_permissions and os.name == "posix":
            _validate_file_permissions(env_path)
            permissions_checked = True
        load_dotenv(env_path, override=False)
        file_loaded = True
        checks.append("environment_file_parsed")
    elif env_path:
        checks.append("environment_file_absent_using_process_environment")

    values = dict(os.environ if environ is None else environ)
    if env_path and file_loaded and environ is not None:
        parsed = {key: value for key, value in dotenv_values(env_path).items() if value is not None}
        values = {**parsed, **values}

    workflow = _text(values, "PRODUCT_HARNESS_WORKFLOW", "one_credit_feature_aware")
    if workflow != "one_credit_feature_aware":
        raise EnvironmentValidationError(
            "PRODUCT_HARNESS_WORKFLOW must be 'one_credit_feature_aware' for the production runner"
        )
    checks.append("workflow_identity_validated")

    serp_key = _text(values, "SERPAPI_API_KEY")
    if require_serpapi:
        _validate_secret("SERPAPI_API_KEY", serp_key, minimum_length=20)
        checks.append("serpapi_secret_validated")

    if enforce_one_credit:
        _enforce_one_credit_settings(values)
        checks.append("one_credit_cost_controls_validated")

    _validate_operational_settings(values)
    checks.append("runtime_bounds_validated")

    llm_enabled = _strict_bool(values, "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING", False)
    llm_configured = False
    if llm_enabled:
        _validate_llm_environment(values)
        llm_configured = True
        checks.append("llm_required_fields_present")
    else:
        checks.append("llm_feature_reasoning_disabled")

    return EnvironmentValidationReport(
        env_file=str(env_path) if env_path else None,
        env_file_loaded=file_loaded,
        env_file_permissions_checked=permissions_checked,
        serpapi_configured=bool(serp_key),
        llm_feature_reasoning_enabled=llm_enabled,
        llm_configured=llm_configured,
        one_credit_contract_enforced=enforce_one_credit,
        checks_passed=tuple(checks),
    )


def _enforce_one_credit_settings(values: Mapping[str, str]) -> None:
    forbidden_true = (
        "PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE",
        "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING",
        "PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK",
        "PRODUCT_HARNESS_ENABLE_LLM",
        "PRODUCT_HARNESS_ENABLE_LLM_ADJUDICATION",
    )
    enabled = [name for name in forbidden_true if _strict_bool(values, name, False)]
    if enabled:
        raise EnvironmentValidationError(
            "One-credit workflow forbids legacy/expansive settings: " + ", ".join(enabled)
        )

    organic = _strict_int(values, "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES", 1, minimum=1, maximum=1)
    ai_mode = _strict_int(values, "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES", 0, minimum=0, maximum=0)
    if organic != 1 or ai_mode != 0:
        raise EnvironmentValidationError("One-credit workflow requires organic=1 and AI Mode=0")

    _strict_int(values, "PRODUCT_HARNESS_SERP_RESULTS", 100, minimum=1, maximum=100)
    if _text(values, "PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS"):
        _strict_int(values, "PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS", 1, minimum=0, maximum=1)


def _validate_operational_settings(values: Mapping[str, str]) -> None:
    _strict_int(values, "PRODUCT_HARNESS_MAX_SCRAPES", 8, minimum=1, maximum=30)
    _strict_int(values, "PRODUCT_HARNESS_MAX_CANDIDATE_POOL", 30, minimum=1, maximum=100)
    _strict_int(values, "PRODUCT_HARNESS_SCRAPE_CONCURRENCY", 4, minimum=1, maximum=16)
    _strict_int(values, "PRODUCT_HARNESS_STATIC_TIMEOUT_SECONDS", 10, minimum=1, maximum=60)
    _strict_int(values, "PRODUCT_HARNESS_CRAWL_PAGE_TIMEOUT_MS", 45000, minimum=5000, maximum=120000)
    _strict_float(values, "PRODUCT_HARNESS_MIN_VERIFIED_CONFIDENCE", 0.80, minimum=0.0, maximum=1.0)
    _strict_float(values, "PRODUCT_HARNESS_MIN_REVIEW_CONFIDENCE", 0.30, minimum=0.0, maximum=1.0)
    for name, default in (
        ("PRODUCT_HARNESS_STATIC_FETCH_FIRST", True),
        ("PRODUCT_HARNESS_BROWSER_FALLBACK_ONLY", True),
        ("PRODUCT_HARNESS_COUNTRY_FIRST", True),
        ("PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK", True),
        ("PRODUCT_HARNESS_ALLOW_EAN_CONFLICT", False),
        ("PRODUCT_HARNESS_RETURN_REJECTED_REFERENCE_AS_PRODUCT_URL", False),
        ("PRODUCT_HARNESS_WRITE_OUTPUTS", True),
        ("PRODUCT_HARNESS_WRITE_REVIEW_PACK", True),
        ("PRODUCT_HARNESS_WRITE_MARKDOWN_REPORTS", False),
        ("PRODUCT_HARNESS_WRITE_TRACE_JSON", False),
        ("PRODUCT_HARNESS_WRITE_DEBUG_CSVS", False),
    ):
        _strict_bool(values, name, default)

    output_dir = _text(values, "PRODUCT_HARNESS_OUTPUT_DIR", "output")
    if not output_dir or "\x00" in output_dir:
        raise EnvironmentValidationError("PRODUCT_HARNESS_OUTPUT_DIR is invalid")


def _validate_llm_environment(values: Mapping[str, str]) -> None:
    required = {
        "AZURE_OPENAI_API_KEY/LLM_API_KEY": _coalesced(values, "AZURE_OPENAI_API_KEY", "LLM_API_KEY"),
        "AZURE_OPENAI_API_VERSION/LLM_API_VERSION": _coalesced(
            values, "AZURE_OPENAI_API_VERSION", "LLM_API_VERSION"
        ),
        "AZURE_OPENAI_ENDPOINT/LLM_ENDPOINT": _coalesced(
            values, "AZURE_OPENAI_ENDPOINT", "LLM_ENDPOINT"
        ),
        "AZURE_OPENAI_DEPLOYMENT/LLM_DEPLOYMENT": _coalesced(
            values, "AZURE_OPENAI_DEPLOYMENT", "LLM_DEPLOYMENT"
        ),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise EnvironmentValidationError(
            "Missing required LLM configuration: " + ", ".join(missing)
        )

    _strict_int(values, "LLM_MAX_TOKENS", 1600, minimum=1, maximum=32768)
    _strict_float(values, "LLM_TEMPERATURE", 0.0, minimum=0.0, maximum=2.0)
    _strict_float(values, "LLM_CONNECT_TIMEOUT", 15.0, minimum=1.0, maximum=120.0)
    _strict_float(values, "LLM_READ_TIMEOUT", 120.0, minimum=5.0, maximum=600.0)
    _strict_int(values, "LLM_MAX_RETRIES", 2, minimum=0, maximum=5)
    _strict_int(values, "PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT", 2, minimum=0, maximum=4)


def _validate_secret(name: str, value: str, *, minimum_length: int) -> None:
    if not value:
        raise EnvironmentValidationError(f"{name} is required")
    if _looks_like_placeholder(value):
        raise EnvironmentValidationError(f"{name} still contains an example/placeholder value")
    if len(value) < minimum_length:
        raise EnvironmentValidationError(f"{name} is shorter than the minimum accepted length")
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise EnvironmentValidationError(f"{name} contains whitespace or control characters")


def _validate_alias_consistency(values: Mapping[str, str], primary: str, alias: str) -> None:
    left = _text(values, primary)
    right = _text(values, alias)
    if left and right and left != right:
        raise EnvironmentValidationError(f"Conflicting values supplied for {primary} and {alias}")


def _coalesced(values: Mapping[str, str], primary: str, alias: str) -> str:
    return _text(values, primary) or _text(values, alias)


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _validate_env_file_syntax(path: Path) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    malformed_lines: list[int] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_KEY_PATTERN.match(line)
        if not match:
            malformed_lines.append(line_number)
            continue
        key = match.group(1)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    if malformed_lines:
        rendered = ", ".join(str(number) for number in malformed_lines[:10])
        raise EnvironmentValidationError(f"Malformed .env assignment line(s): {rendered}")
    if duplicates:
        raise EnvironmentValidationError(
            "Duplicate environment keys are not allowed: " + ", ".join(sorted(duplicates))
        )


def _validate_file_permissions(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise EnvironmentValidationError(
            f"Environment file permissions are too broad ({oct(mode)}). Run: chmod 600 {path}"
        )


def _strict_bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    normalized = str(raw).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise EnvironmentValidationError(f"{name} must be an explicit boolean (true/false)")


def _strict_int(
    values: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = values.get(name)
    try:
        value = default if raw is None or str(raw).strip() == "" else int(str(raw).strip())
    except ValueError as exc:
        raise EnvironmentValidationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise EnvironmentValidationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _strict_float(
    values: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw = values.get(name)
    try:
        value = default if raw is None or str(raw).strip() == "" else float(str(raw).strip())
    except ValueError as exc:
        raise EnvironmentValidationError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise EnvironmentValidationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _text(values: Mapping[str, str], name: str, default: str = "") -> str:
    value = values.get(name, default)
    return str(value or "").strip()
