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

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from odysseus.exceptions import ConfigError

ENV_PREFIX = "ODYSSEUS_"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"


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


class HealthConfig(BaseModel):
    """Configuration for system health & diagnostics (F073)."""

    disk_warn_percent: float = Field(default=85.0, ge=0, le=100)
    disk_critical_percent: float = Field(default=95.0, ge=0, le=100)
    model_check_timeout_seconds: float = Field(default=3.0, gt=0)
    ram_warn_available_percent: float = Field(default=15.0, ge=0, le=100)
    ram_critical_available_percent: float = Field(default=5.0, ge=0, le=100)

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
    """
    data = dict(data)
    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        path = key[len(ENV_PREFIX) :].lower().split("__")
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

    Never raises on a missing file; a missing/empty file just means
    "use the defaults". Raises ``ConfigError`` for malformed YAML or
    values that fail validation.
    """
    yaml_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
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
