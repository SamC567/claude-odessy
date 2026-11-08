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
