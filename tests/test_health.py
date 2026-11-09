from __future__ import annotations

from pathlib import Path

from odysseus.config import OdysseusConfig
from odysseus.health.diagnostics import CheckStatus, run_diagnostics
from odysseus.memory.store import MemoryStore
from odysseus.models.echo_provider import EchoProvider


def test_run_diagnostics_all_ok_with_echo_provider(tmp_path):
    config = OdysseusConfig()
    memory = MemoryStore(tmp_path / "mem.sqlite3")
    provider = EchoProvider()
    report = run_diagnostics(config, memory, provider, disk_path=tmp_path)
    assert report.overall_status == CheckStatus.OK
    names = {c.name for c in report.checks}
    assert "python_version" in names
    assert "disk_space" in names
    assert "memory_store" in names
    assert "model_provider:echo" in names


def test_a_failing_check_does_not_crash_the_whole_report(tmp_path, monkeypatch):
    config = OdysseusConfig()
    memory = MemoryStore(tmp_path / "mem.sqlite3")
    provider = EchoProvider()

    class ExplodingProvider(EchoProvider):
        def health_check(self):
            raise RuntimeError("boom")

    report = run_diagnostics(config, memory, ExplodingProvider(), disk_path=tmp_path)
    model_check = [c for c in report.checks if c.name.startswith("model_provider")][0]
    assert model_check.status == CheckStatus.CRITICAL
    assert "boom" in model_check.detail
    # Other checks still ran despite the exploding one.
    assert any(c.name == "disk_space" for c in report.checks)


def test_unreachable_optional_model_is_warning_not_critical(tmp_path):
    config = OdysseusConfig()
    memory = MemoryStore(tmp_path / "mem.sqlite3")

    class UnhealthyProvider(EchoProvider):
        def health_check(self):
            return False, "pretend unreachable"

    report = run_diagnostics(config, memory, UnhealthyProvider(), disk_path=tmp_path)
    model_check = [c for c in report.checks if c.name.startswith("model_provider")][0]
    assert model_check.status == CheckStatus.WARNING
    assert report.overall_status == CheckStatus.WARNING


def test_as_dict_and_summary_line(tmp_path):
    config = OdysseusConfig()
    memory = MemoryStore(tmp_path / "mem.sqlite3")
    report = run_diagnostics(config, memory, EchoProvider(), disk_path=tmp_path)
    d = report.as_dict()
    assert d["overall_status"] == "ok"
    assert isinstance(d["checks"], list)
    assert "OK" in report.summary_line()


def test_dependencies_check_ok_and_reports_missing():
    from odysseus.health.diagnostics import check_dependencies

    ok = check_dependencies(("pytest",))
    assert ok.status == CheckStatus.OK
    assert "pytest==" in ok.detail
    bad = check_dependencies(("pytest", "definitely-not-installed-pkg"))
    assert bad.status == CheckStatus.CRITICAL
    assert "definitely-not-installed-pkg" in bad.detail


def test_run_diagnostics_includes_dependencies(tmp_path):
    memory = MemoryStore(tmp_path / "mem.sqlite3")
    report = run_diagnostics(OdysseusConfig(), memory, EchoProvider(), disk_path=tmp_path)
    assert any(c.name == "dependencies" for c in report.checks)


def test_hardware_check_thresholds_and_unknown():
    from odysseus.health.diagnostics import check_hardware

    gib = 1024**3
    assert check_hardware(memory_reader=lambda: (16 * gib, 8 * gib)).status == CheckStatus.OK
    assert check_hardware(memory_reader=lambda: (16 * gib, 2 * gib)).status == CheckStatus.WARNING
    crit = check_hardware(memory_reader=lambda: (16 * gib, gib // 4))
    assert crit.status == CheckStatus.CRITICAL
    assert "cpus=" in crit.detail
    assert check_hardware(memory_reader=lambda: None).status == CheckStatus.WARNING


def test_run_diagnostics_includes_hardware(tmp_path):
    memory = MemoryStore(tmp_path / "mem.sqlite3")
    report = run_diagnostics(OdysseusConfig(), memory, EchoProvider(), disk_path=tmp_path)
    assert any(c.name == "hardware" for c in report.checks)


def test_run_diagnostics_uses_configured_ram_thresholds(tmp_path, monkeypatch):
    from odysseus.health import diagnostics

    gib = 1024**3
    monkeypatch.setattr(diagnostics, "_read_memory_bytes", lambda: (16 * gib, 8 * gib))
    memory = MemoryStore(tmp_path / "mem.sqlite3")

    def hw(cfg):
        report = run_diagnostics(cfg, memory, EchoProvider(), disk_path=tmp_path)
        return next(c for c in report.checks if c.name == "hardware")

    assert hw(OdysseusConfig()).status == CheckStatus.OK  # 50% available
    strict = OdysseusConfig(
        health={"ram_warn_available_percent": 60.0, "ram_critical_available_percent": 40.0}
    )
    assert hw(strict).status == CheckStatus.WARNING
    strict.health.ram_critical_available_percent = 50.0
    assert hw(strict).status == CheckStatus.CRITICAL


def test_gpu_check_states_and_in_report(tmp_path):
    from odysseus.health.diagnostics import check_gpu

    assert check_gpu(lambda: []).status == CheckStatus.OK
    assert check_gpu(lambda: None).status == CheckStatus.WARNING
    assert check_gpu(lambda: [("RTX", 8000, 4000)]).status == CheckStatus.OK
    full = check_gpu(lambda: [("RTX", 8000, 100)])
    assert full.status == CheckStatus.WARNING and "RTX" in full.detail
    memory = MemoryStore(tmp_path / "mem.sqlite3")
    report = run_diagnostics(OdysseusConfig(), memory, EchoProvider(), disk_path=tmp_path)
    assert any(c.name == "gpu" for c in report.checks)


def test_gpu_vram_threshold_is_configurable(tmp_path):
    from odysseus.config import HealthConfig
    from odysseus.health.diagnostics import check_gpu

    gpus = lambda: [("RTX", 8000, 1200)]  # 15% free
    assert check_gpu(gpus).status == CheckStatus.OK
    assert check_gpu(gpus, warn_free_percent=20.0).status == CheckStatus.WARNING
    assert HealthConfig(gpu_vram_warn_free_percent=20.0).gpu_vram_warn_free_percent == 20.0


def test_run_diagnostics_passes_configured_model_check_timeout(tmp_path):
    from odysseus.config import OdysseusConfig
    from odysseus.health.diagnostics import check_model_provider

    seen = []

    class _Timed:
        name = "timed"

        def health_check(self, timeout_seconds=None):
            seen.append(timeout_seconds)
            return True, "ok"

    class _Legacy:
        name = "legacy"

        def health_check(self):
            return True, "ok"

    check_model_provider(_Timed(), 2.5)
    assert seen == [2.5]
    assert check_model_provider(_Legacy(), 2.5).status.value == "ok"


def test_memory_store_check_detects_corrupt_database(tmp_path):
    from odysseus.health.diagnostics import CheckStatus, check_memory_store

    db = tmp_path / "mem.sqlite3"
    store = MemoryStore(db)
    assert store.integrity_check() == (True, "ok")
    assert check_memory_store(store).status == CheckStatus.OK
    # Corrupt the file in place (keep the header, clobber later pages).
    data = bytearray(db.read_bytes())
    for i in range(100, len(data)):
        data[i] = 0xFF
    db.write_bytes(bytes(data))
    result = check_memory_store(store)
    assert result.status == CheckStatus.CRITICAL
