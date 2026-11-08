"""System health and diagnostic reporting.

This module only *observes* -- it never changes config, memory or model
state. Every check is independent and failure-isolated: one check
raising never prevents the others from running or from being reported.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from odysseus.config import OdysseusConfig
from odysseus.memory.store import MemoryStore
from odysseus.models.base import ModelProvider


class CheckStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    detail: str


@dataclass
class HealthReport:
    generated_at: datetime
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def overall_status(self) -> CheckStatus:
        statuses = {c.status for c in self.checks}
        if CheckStatus.CRITICAL in statuses:
            return CheckStatus.CRITICAL
        if CheckStatus.WARNING in statuses:
            return CheckStatus.WARNING
        return CheckStatus.OK

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "overall_status": self.overall_status.value,
            "checks": [
                {"name": c.name, "status": c.status.value, "detail": c.detail}
                for c in self.checks
            ],
        }

    def summary_line(self) -> str:
        parts = [f"{c.name}={c.status.value}" for c in self.checks]
        return f"[{self.overall_status.value.upper()}] " + ", ".join(parts)


def _safe_check(name: str, fn) -> CheckResult:
    """Run one check, converting any exception into a CRITICAL result.

    This is what guarantees a single misbehaving check (e.g. a provider
    that raises something unexpected) can't take down the whole report.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - diagnostics must never crash
        return CheckResult(name=name, status=CheckStatus.CRITICAL, detail=f"check raised: {exc}")


def check_python_version() -> CheckResult:
    version = sys.version.split()[0]
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        return CheckResult(
            "python_version", CheckStatus.WARNING, f"Python {version} is older than 3.10"
        )
    return CheckResult("python_version", CheckStatus.OK, f"Python {version}")


def check_disk_space(path: Path, warn_percent: float, critical_percent: float) -> CheckResult:
    usage = shutil.disk_usage(path)
    used_percent = (usage.used / usage.total) * 100 if usage.total else 0.0
    detail = f"{used_percent:.1f}% used at {path}"
    if used_percent >= critical_percent:
        return CheckResult("disk_space", CheckStatus.CRITICAL, detail)
    if used_percent >= warn_percent:
        return CheckResult("disk_space", CheckStatus.WARNING, detail)
    return CheckResult("disk_space", CheckStatus.OK, detail)


def check_config(config: OdysseusConfig) -> CheckResult:
    # Config already passed pydantic validation to exist as an OdysseusConfig,
    # so this check focuses on policy-level sanity, not just schema validity.
    if not config.identity.allow_external_providers and config.model.provider not in (
        "echo",
        "ollama",
    ):
        return CheckResult(
            "config",
            CheckStatus.WARNING,
            f"model.provider={config.model.provider!r} is not a recognised local provider",
        )
    return CheckResult("config", CheckStatus.OK, "configuration loaded and valid")


def check_memory_store(store: MemoryStore) -> CheckResult:
    counts = store.count_by_status()
    pending = counts.get("pending", 0)
    detail = f"db={store.db_path} counts={counts}"
    if pending > 100:
        return CheckResult(
            "memory_store", CheckStatus.WARNING, f"{pending} pending review items; {detail}"
        )
    return CheckResult("memory_store", CheckStatus.OK, detail)


def check_model_provider(provider: ModelProvider) -> CheckResult:
    healthy, detail = provider.health_check()
    if healthy:
        return CheckResult(f"model_provider:{provider.name}", CheckStatus.OK, detail)
    # An unreachable *optional* local model is a WARNING, not CRITICAL --
    # the system must remain usable (via the echo fallback) without it.
    return CheckResult(f"model_provider:{provider.name}", CheckStatus.WARNING, detail)


def run_diagnostics(
    config: OdysseusConfig,
    memory_store: MemoryStore,
    model_provider: ModelProvider,
    disk_path: Path | None = None,
) -> HealthReport:
    """Run the full diagnostic suite and return a structured report."""
    path = disk_path or Path(".")
    checks = [
        _safe_check("python_version", check_python_version),
        _safe_check(
            "disk_space",
            lambda: check_disk_space(
                path, config.health.disk_warn_percent, config.health.disk_critical_percent
            ),
        ),
        _safe_check("config", lambda: check_config(config)),
        _safe_check("memory_store", lambda: check_memory_store(memory_store)),
        _safe_check("model_provider", lambda: check_model_provider(model_provider)),
    ]
    return HealthReport(generated_at=datetime.now(timezone.utc), checks=checks)
