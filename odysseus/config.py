"""Configuration loading, separated from application logic.

Precedence (highest wins):
    1. Explicit keyword overrides passed to ``load_config``
    2. Environment variables (prefixed ``ODYSSEUS_``)
    3. YAML config file (default: ``config/default.yaml``)
    4. Built-in defaults on the pydantic models below

No secrets live in this module or in the shipped YAML. Real credentials
are supplied only via environment variables at deploy time (see
``config/.env.example``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from odysseus.exceptions import ConfigError

ENV_PREFIX = "ODYSSEUS_"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"


_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ModelProviderConfig(BaseModel):
    """Configuration for the replaceable model-provider layer (F003)."""

    provider: str = Field(
        default="echo",
        description="Which provider implementation to use: 'echo', 'ollama', or a custom key.",
    )
    base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for a local model server (e.g. Ollama).",
    )
    model_name: str = Field(default="llama3", description="Model identifier to request.")
    timeout_seconds: float = Field(default=10.0, gt=0)
    max_retries: int = Field(default=1, ge=0)

    @field_validator("base_url")
    @classmethod
    def _base_url_is_http(cls, value: str) -> str:
        # A malformed endpoint (no scheme, ftp://, empty host) would otherwise
        # only fail at request time, deep inside the provider.
        parsed = urlparse(value.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("model.base_url must be an http(s) URL with a host")
        if parsed.username is not None or parsed.password is not None:
            # base_url is echoed in diagnostics/audit output; credentials
            # embedded in it would leak there and into the config file.
            raise ValueError("model.base_url must not embed credentials (user:pass@host)")
        return value.strip()

    @model_validator(mode="after")
    def _ollama_needs_model_name(self) -> "ModelProviderConfig":
        # A blank model would only fail at request time (HTTP 400 from the
        # server); the echo provider tolerates it, so only check for ollama.
        if self.provider == "ollama" and not self.model_name.strip():
            raise ValueError("model.model_name must not be blank for the ollama provider")
        return self


class MemoryConfig(BaseModel):
    """Configuration for persistent memory + review inbox (F009)."""

    db_path: str = Field(
        default="data/odysseus_memory.sqlite3",
        description="Path to the SQLite database file, relative to the project root.",
    )
    auto_approve_threshold: float | None = Field(
        default=None,
        description=(
            "If set, candidate memories with confidence >= this value may be "
            "auto-approved instead of requiring manual review. None means "
            "every candidate requires manual review (safest default)."
        ),
        ge=0.0,
        le=1.0,
    )
    context_limit: int = Field(
        default=3,
        description=(
            "Maximum number of approved memories the orchestrator adds to the "
            "model prompt for one interaction. 0 means approved memory is "
            "never added to the prompt (it is still stored and reviewable)."
        ),
        ge=0,
        le=50,
    )

    @field_validator("context_limit", mode="before")
    @classmethod
    def _context_limit_is_a_whole_number(cls, value: Any) -> Any:
        # pydantic would otherwise read YAML ``true`` as 1 and ``2.0`` as 2;
        # a count that is not written as a whole number is a mistake.
        if isinstance(value, (bool, float)):
            raise ValueError("memory.context_limit must be a whole number")
        return value


class HealthConfig(BaseModel):
    """Configuration for system health & diagnostics (F073)."""

    disk_warn_percent: float = Field(default=85.0, ge=0, le=100)
    disk_critical_percent: float = Field(default=95.0, ge=0, le=100)
    model_check_timeout_seconds: float = Field(default=3.0, gt=0)
    ram_warn_available_percent: float = Field(default=15.0, ge=0, le=100)
    ram_critical_available_percent: float = Field(default=5.0, ge=0, le=100)
    gpu_vram_warn_free_percent: float = Field(default=5.0, ge=0, le=100)
    pending_review_warn_count: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def _thresholds_are_ordered(self) -> "HealthConfig":
        # Inverted thresholds would make the WARNING band unreachable and
        # silently mislead operators, so reject them at load time.
        if self.disk_warn_percent > self.disk_critical_percent:
            raise ValueError("health.disk_warn_percent must be <= disk_critical_percent")
        if self.ram_warn_available_percent < self.ram_critical_available_percent:
            raise ValueError(
                "health.ram_warn_available_percent must be >= ram_critical_available_percent"
            )
        return self


class IdentityConfig(BaseModel):
    """Configuration for the central Jarvis identity/orchestration layer (F001)."""

    name: str = Field(default="Jarvis")
    persona: str = Field(
        default="A private, local-first assistant foundation for the Odysseus project."
    )
    allow_external_providers: bool = Field(
        default=False,
        description=(
            "Explicit permission gate: if False, orchestration must not route "
            "requests to any non-local/external model provider, even if one "
            "is configured."
        ),
    )


class OdysseusConfig(BaseModel):
    """Top-level configuration object for the whole system."""

    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    model: ModelProviderConfig = Field(default_factory=ModelProviderConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    log_level: str = Field(default="INFO")
    audit_log_path: str = Field(
        default="data/audit.log",
        description=(
            "File the audit trail is appended to. A relative path is resolved "
            "against the process working directory (same as memory.db_path)."
        ),
    )

    @field_validator("audit_log_path")
    @classmethod
    def _audit_log_path_is_set(cls, value: str) -> str:
        # A blank path would silently switch the audit trail to stderr-only
        # (not persisted); make turning persistence off impossible by typo.
        if not value.strip():
            raise ValueError("audit_log_path must not be blank")
        return value.strip()

    @field_validator("log_level")
    @classmethod
    def _log_level_is_known(cls, value: str) -> str:
        # An unknown level would otherwise surface as a raw ValueError from
        # logging.setLevel at CLI start-up; reject it at load time instead.
        normalised = value.strip().upper()
        if normalised not in _LOG_LEVELS:
            raise ValueError(f"log_level must be one of {', '.join(_LOG_LEVELS)}")
        return normalised


# Top-level fields that are plain values rather than sections; these take a
# single-segment env override (ODYSSEUS_<FIELD>) instead of SECTION__FIELD.
_TOP_LEVEL_SCALAR_FIELDS = frozenset({"log_level", "audit_log_path"})


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse YAML config at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Config at {path} must be a mapping at the top level.")
    return data


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Apply ``ODYSSEUS_SECTION__FIELD=value`` environment overrides.

    Example: ``ODYSSEUS_MODEL__PROVIDER=ollama`` overrides ``model.provider``.
    Top-level scalar fields have no section: ``ODYSSEUS_LOG_LEVEL=DEBUG``
    overrides ``log_level`` (likewise ``ODYSSEUS_AUDIT_LOG_PATH``). A single-segment name that is a section (e.g.
    ``ODYSSEUS_MODEL``) is ignored, as are unknown names.
    """
    data = dict(data)
    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        path = key[len(ENV_PREFIX) :].lower().split("__")
        if len(path) == 1 and path[0] in _TOP_LEVEL_SCALAR_FIELDS:
            data[path[0]] = value
            continue
        if len(path) != 2:
            continue
        section, field = path
        data.setdefault(section, {})
        if not isinstance(data[section], dict):
            continue
        data[section] = dict(data[section])
        data[section][field] = value
    return data


def load_config(
    path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> OdysseusConfig:
    """Load configuration from YAML + environment, with optional overrides.

    A missing *default* file (or an empty file) just means "use the
    defaults". An explicitly given ``path`` that does not exist is a
    ``ConfigError`` (a typo'd path must not silently fall back to
    defaults). Also raises ``ConfigError`` for malformed YAML or values
    that fail validation.
    """
    yaml_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if path is not None and not yaml_path.is_file():
        raise ConfigError(f"Config file not found: {yaml_path}")
    data = _read_yaml(yaml_path)
    data = _apply_env_overrides(data)
    if overrides:
        for section, fields in overrides.items():
            data.setdefault(section, {})
            data[section] = {**data.get(section, {}), **fields}
    try:
        return OdysseusConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc
