"""System health and diagnostic reporting.

This module only *observes* -- it never changes config, memory or model
state. Every check is independent and failure-isolated: one check
raising never prevents the others from running or from being reported.
"""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
import sys
from importlib import metadata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from odysseus.config import OdysseusConfig
from odysseus.memory.store import MemoryStore
from odysseus.models.base import ModelProvider
from odysseus.models.registry import is_loopback_url


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


REQUIRED_DEPENDENCIES = ("pydantic", "PyYAML", "requests")


def check_dependencies(required: tuple[str, ...] = REQUIRED_DEPENDENCIES) -> CheckResult:
    """Report whether each required third-party package is installed (F073).

    Read-only: uses installed-distribution metadata, no imports, no network.
    """
    versions: list[str] = []
    missing: list[str] = []
    for name in required:
        try:
            versions.append(f"{name}=={metadata.version(name)}")
        except metadata.PackageNotFoundError:
            missing.append(name)
    if missing:
        return CheckResult(
            "dependencies", CheckStatus.CRITICAL, "missing: " + ", ".join(missing)
        )
    return CheckResult("dependencies", CheckStatus.OK, ", ".join(versions))


def _read_memory_bytes() -> tuple[int, int] | None:
    """Return (total, available) physical RAM in bytes, or None if unknown.

    Stdlib only: /proc/meminfo on Linux, GlobalMemoryStatusEx on Windows.
    """
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        values: dict[str, int] = {}
        for line in meminfo.read_text().splitlines():
            key, _, rest = line.partition(":")
            parts = rest.split()
            if parts and parts[0].isdigit():
                values[key] = int(parts[0]) * 1024
        if "MemTotal" in values and "MemAvailable" in values:
            return values["MemTotal"], values["MemAvailable"]
        return None
    if sys.platform == "win32":
        import ctypes

        class _MemStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemStatus()
        status.dwLength = ctypes.sizeof(_MemStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullTotalPhys, status.ullAvailPhys
    return None


def check_hardware(
    warn_available_percent: float = 15.0,
    critical_available_percent: float = 5.0,
    memory_reader=_read_memory_bytes,
) -> CheckResult:
    """Report CPU count and RAM headroom (F073). Read-only, stdlib only.

    GPU/VRAM is covered separately by ``check_gpu``.
    """
    cpus = os.cpu_count() or 0
    mem = memory_reader()
    if mem is None or mem[0] <= 0:
        return CheckResult(
            "hardware", CheckStatus.WARNING, f"cpus={cpus}; RAM could not be determined"
        )
    total, available = mem
    avail_pct = available / total * 100
    gib = 1024**3
    detail = f"cpus={cpus}; RAM {available / gib:.1f}/{total / gib:.1f} GiB available ({avail_pct:.1f}%)"
    if avail_pct <= critical_available_percent:
        return CheckResult("hardware", CheckStatus.CRITICAL, detail)
    if avail_pct <= warn_available_percent:
        return CheckResult("hardware", CheckStatus.WARNING, detail)
    return CheckResult("hardware", CheckStatus.OK, detail)


def _read_gpus() -> list[tuple[str, int, int]] | None:
    """Return [(name, total_mib, free_mib)] via nvidia-smi, [] if no NVIDIA GPU,
    or None if the query failed. Local subprocess only, no network."""
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
        gpus = []
        for line in out.strip().splitlines():
            name, total, free = (p.strip() for p in line.rsplit(",", 2))
            gpus.append((name, int(total), int(free)))
        return gpus
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def check_gpu(gpu_reader=_read_gpus, warn_free_percent: float = 5.0) -> CheckResult:
    """Report NVIDIA GPU / VRAM headroom (F073). Read-only.

    No GPU is OK (the GPU is optional; the echo fallback needs none). A query
    that fails is a WARNING. Other vendors (AMD/Apple) are not detected yet.
    """
    gpus = gpu_reader()
    if gpus is None:
        return CheckResult("gpu", CheckStatus.WARNING, "nvidia-smi present but query failed")
    if not gpus:
        return CheckResult("gpu", CheckStatus.OK, "no NVIDIA GPU detected (optional)")
    detail = "; ".join(f"{n}: {f}/{t} MiB VRAM free" for n, t, f in gpus)
    low = [n for n, t, f in gpus if t > 0 and f / t * 100 <= warn_free_percent]
    if low:
        return CheckResult("gpu", CheckStatus.WARNING, "VRAM nearly full on " + ", ".join(low) + "; " + detail)
    return CheckResult("gpu", CheckStatus.OK, detail)


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
    if (
        config.model.provider == "ollama"
        and not config.identity.allow_external_providers
        and not is_loopback_url(config.model.base_url)
    ):
        # build_provider() silently substitutes the echo fallback here; make
        # the (safe) override visible instead of reporting a clean config.
        return CheckResult(
            "config",
            CheckStatus.WARNING,
            f"model.base_url={config.model.base_url!r} is not loopback and "
            "identity.allow_external_providers is false: the echo fallback will be used",
        )
    return CheckResult("config", CheckStatus.OK, "configuration loaded and valid")


def check_memory_store(store: MemoryStore, pending_warn_count: int = 100) -> CheckResult:
    ok, problem = store.integrity_check()
    if not ok:
        return CheckResult(
            "memory_store",
            CheckStatus.CRITICAL,
            f"integrity check failed: {problem}; db={store.db_path}",
        )
    counts = store.count_by_status()
    pending = counts.get("pending", 0)
    detail = f"db={store.db_path} counts={counts}"
    if pending > pending_warn_count:
        return CheckResult(
            "memory_store", CheckStatus.WARNING, f"{pending} pending review items; {detail}"
        )
    return CheckResult("memory_store", CheckStatus.OK, detail)


def check_model_provider(
    provider: ModelProvider, timeout_seconds: float | None = None
) -> CheckResult:
    # Older/third-party providers may still define ``health_check(self)``
    # without the timeout parameter; call them as before (compatibility).
    try:
        accepts_timeout = "timeout_seconds" in inspect.signature(provider.health_check).parameters
    except (TypeError, ValueError):
        accepts_timeout = False
    if accepts_timeout and timeout_seconds is not None:
        healthy, detail = provider.health_check(timeout_seconds)
    else:
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
    # Default to the volume holding the memory DB (the data that matters),
    # falling back to the working directory if its folder doesn't exist yet.
    if disk_path is not None:
        path = disk_path
    else:
        db_dir = Path(memory_store.db_path).parent
        path = db_dir if db_dir.exists() else Path(".")
    checks = [
        _safe_check("python_version", check_python_version),
        _safe_check(
            "disk_space",
            lambda: check_disk_space(
                path, config.health.disk_warn_percent, config.health.disk_critical_percent
            ),
        ),
        _safe_check("dependencies", check_dependencies),
        _safe_check(
            "hardware",
            lambda: check_hardware(
                config.health.ram_warn_available_percent,
                config.health.ram_critical_available_percent,
                memory_reader=_read_memory_bytes,
            ),
        ),
        _safe_check(
            "gpu",
            lambda: check_gpu(warn_free_percent=config.health.gpu_vram_warn_free_percent),
        ),
        _safe_check("config", lambda: check_config(config)),
        _safe_check("memory_store", lambda: check_memory_store(
                memory_store, config.health.pending_review_warn_count
            ),
        ),
        _safe_check(
            f"model_provider:{model_provider.name}",
            lambda: check_model_provider(
                model_provider, config.health.model_check_timeout_seconds
            ),
        ),
    ]
    return HealthReport(generated_at=datetime.now(timezone.utc), checks=checks)
