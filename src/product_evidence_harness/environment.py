from __future__ import annotations

import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from dotenv import dotenv_values, load_dotenv


class EnvironmentValidationError(ValueError):
    """Raised when runtime configuration violates a security or cost invariant."""


_PLACEHOLDER_MARKERS = (
    "your_",
    "replace_",
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
_SECRET_KEYS = {
    "SERPAPI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "LLM_API_KEY",
}


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

    The validator is deliberately fail-closed. It rejects placeholder secrets,
    ambiguous aliases, malformed booleans/numbers, insecure local secret files,
    non-HTTPS LLM endpoints, and settings that can violate the one-credit search
    contract. Secret values are never included in returned diagnostics.
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
        _reject_duplicate_keys(env_path)
        if strict_file_permissions and os.name == "posix":
            _validate_file_permissions(env_path)
            permissions_checked = True
        load_dotenv(env_path, override=False)
        file_loaded = True
        checks.append("environment_file_parsed")
    elif env_path:
        # Managed runtimes may inject secrets directly. Missing .env is allowed only
        # when the required variables are already available in the process environment.
        checks.append("environment_file_absent_using_process_environment")

    values = dict(os.environ if environ is None else environ)
    if env_path and file_loaded and environ is not None:
        # Explicit test/runtime mappings take precedence without mutating the process.
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

    llm_enabled = _strict_bool(values, "PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING", False)
    llm_configured = False
    if llm_enabled:
        _validate_llm_environment(values)
        llm_configured = True
        checks.append("llm_credentials_and_transport_validated")
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
    )
    enabled = [name for name in forbidden_true if _strict_bool(values, name, False)]
    if enabled:
        raise EnvironmentValidationError(
            "One-credit workflow forbids these settings: " + ", ".join(enabled)
        )

    organic = _strict_int(values, "PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES", 1, minimum=1, maximum=1)
    ai_mode = _strict_int(values, "PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES", 0, minimum=0, maximum=0)
    if organic != 1 or ai_mode != 0:  # defensive; bounds above already enforce this
        raise EnvironmentValidationError("One-credit workflow requires organic=1 and AI Mode=0")

    results = _strict_int(values, "PRODUCT_HARNESS_SERP_RESULTS", 100, minimum=1, maximum=100)
    if results > 100:
        raise EnvironmentValidationError("PRODUCT_HARNESS_SERP_RESULTS cannot exceed 100")


def _validate_llm_environment(values: Mapping[str, str]) -> None:
    key = _coalesced(values, "AZURE_OPENAI_API_KEY", "LLM_API_KEY")
    version = _coalesced(values, "AZURE_OPENAI_API_VERSION", "LLM_API_VERSION")
    endpoint = _coalesced(values, "AZURE_OPENAI_ENDPOINT", "LLM_ENDPOINT")
    deployment = _coalesced(values, "AZURE_OPENAI_DEPLOYMENT", "LLM_DEPLOYMENT")

    _validate_alias_consistency(values, "AZURE_OPENAI_API_KEY", "LLM_API_KEY")
    _validate_alias_consistency(values, "AZURE_OPENAI_API_VERSION", "LLM_API_VERSION")
    _validate_alias_consistency(values, "AZURE_OPENAI_ENDPOINT", "LLM_ENDPOINT")
    _validate_alias_consistency(values, "AZURE_OPENAI_DEPLOYMENT", "LLM_DEPLOYMENT")

    _validate_secret("AZURE_OPENAI_API_KEY/LLM_API_KEY", key, minimum_length=16)
    if not version or _looks_like_placeholder(version):
        raise EnvironmentValidationError("LLM API version is missing or still a placeholder")
    if not deployment or _looks_like_placeholder(deployment):
        raise EnvironmentValidationError("LLM deployment is missing or still a placeholder")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", deployment):
        raise EnvironmentValidationError("LLM deployment contains unsupported characters")

    parsed = urlparse(endpoint)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise EnvironmentValidationError("LLM endpoint must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EnvironmentValidationError("LLM endpoint must not contain credentials, query parameters, or fragments")
    if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        raise EnvironmentValidationError("Loopback LLM endpoints are not allowed in strict production mode")

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


def _reject_duplicate_keys(path: Path) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    key_pattern = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = key_pattern.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
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
