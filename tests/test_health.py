from __future__ import annotations

from pathlib import Path

import pytest

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
    # Same check name as the healthy path, so consumers can key on it.
    assert model_check.name == "model_provider:echo"
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


def test_disk_check_defaults_to_memory_db_volume(tmp_path, monkeypatch):
    from odysseus.health import diagnostics

    seen = []
    real = diagnostics.check_disk_space

    def spy(path, warn, crit):
        seen.append(path)
        return real(path, warn, crit)

    monkeypatch.setattr(diagnostics, "check_disk_space", spy)
    memory = MemoryStore(tmp_path / "mem.sqlite3")
    run_diagnostics(OdysseusConfig(), memory, EchoProvider())
    assert seen == [tmp_path]


def test_config_check_warns_when_external_ollama_is_blocked():
    from odysseus.health.diagnostics import check_config

    blocked = OdysseusConfig(
        model={"provider": "ollama", "base_url": "http://192.0.2.10:11434"}
    )
    assert check_config(blocked).status == CheckStatus.WARNING
    local = OdysseusConfig(model={"provider": "ollama"})
    assert check_config(local).status == CheckStatus.OK
    allowed = OdysseusConfig(
        model={"provider": "ollama", "base_url": "http://192.0.2.10:11434"},
        identity={"allow_external_providers": True},
    )
    assert check_config(allowed).status == CheckStatus.OK


def test_pending_review_warn_threshold_is_configurable(tmp_path):
    from odysseus.config import HealthConfig
    from odysseus.memory.models import MemoryEntry

    store = MemoryStore(tmp_path / "mem.sqlite3")
    for i in range(3):
        store.submit_candidate(MemoryEntry(content=f"fact {i}", source="user", confidence=0.5))
    config = OdysseusConfig(health=HealthConfig(pending_review_warn_count=2))
    report = run_diagnostics(config, store, EchoProvider(), disk_path=tmp_path)
    check = next(c for c in report.checks if c.name == "memory_store")
    assert check.status == CheckStatus.WARNING
    default = run_diagnostics(OdysseusConfig(), store, EchoProvider(), disk_path=tmp_path)
    assert next(c for c in default.checks if c.name == "memory_store").status == CheckStatus.OK


def test_memory_store_check_warns_when_db_not_writable(tmp_path, monkeypatch):
    import os

    store = MemoryStore(tmp_path / "mem.sqlite3")
    real_access = os.access
    monkeypatch.setattr(
        os, "access",
        lambda p, mode, *a, **k: False if Path(p) == store.db_path and mode == os.W_OK
        else real_access(p, mode, *a, **k),
    )
    report = run_diagnostics(OdysseusConfig(), store, EchoProvider(), disk_path=tmp_path)
    check = next(c for c in report.checks if c.name == "memory_store")
    assert check.status == CheckStatus.WARNING
    assert "not writable" in check.detail


def test_dependencies_check_warns_on_unsupported_major_version(monkeypatch):
    from importlib import metadata

    from odysseus.health import diagnostics

    real = metadata.version
    monkeypatch.setattr(
        diagnostics.metadata, "version", lambda n: "1.10.0" if n == "pydantic" else real(n)
    )
    res = diagnostics.check_dependencies(("pydantic", "pytest"))
    assert res.status == CheckStatus.WARNING
    assert "pydantic==1.10.0" in res.detail


def test_dependencies_check_warns_below_the_supported_minimum(monkeypatch):
    from importlib import metadata

    from odysseus.health import diagnostics

    real = metadata.version
    installed = {"requests": "2.20.1"}
    monkeypatch.setattr(
        diagnostics.metadata, "version", lambda n: installed.get(n) or real(n)
    )
    res = diagnostics.check_dependencies(("requests", "pytest"))
    assert res.status == CheckStatus.WARNING
    assert "requests==2.20.1 (need >=2.28)" in res.detail
    assert "older than the supported minimum" in res.detail

    # The lowest supported release itself, and a pre-release of it, are fine.
    for version in ("2.28", "2.28.0", "2.28.0rc1", "2.31.0"):
        installed["requests"] = version
        assert diagnostics.check_dependencies(("requests",)).status == CheckStatus.OK, version

    # A version that cannot be read as major.minor is reported, not judged.
    installed["requests"] = "2.x"
    odd = diagnostics.check_dependencies(("requests",))
    assert odd.status == CheckStatus.OK
    assert "requests==2.x" in odd.detail


def test_dependencies_check_reports_a_wrong_major_and_a_too_old_minor_together(monkeypatch):
    from odysseus.health import diagnostics

    installed = {"pydantic": "1.10.0", "requests": "2.5.0", "PyYAML": "6.0.1"}
    monkeypatch.setattr(diagnostics.metadata, "version", lambda n: installed[n])
    res = diagnostics.check_dependencies()
    assert res.status == CheckStatus.WARNING
    assert "pydantic==1.10.0 (need 2.x)" in res.detail
    assert "requests==2.5.0 (need >=2.28)" in res.detail
    # A wrong major version is named once, not also as "too old".
    assert res.detail.count("pydantic==") == 1


def test_dependency_version_tables_agree_with_requirements_txt():
    import re

    from odysseus.health import diagnostics

    text = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text()
    majors, minimums = {}, {}
    for line in text.splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)>=(\d+)\.(\d+),<(\d+)\.0", line.strip())
        if match:
            name, low_major, low_minor, below = match.groups()
            assert int(below) == int(low_major) + 1, line
            majors[name] = int(low_major)
            minimums[name] = (int(low_major), int(low_minor))
    assert set(majors) == set(diagnostics.REQUIRED_DEPENDENCIES)
    assert majors == diagnostics.SUPPORTED_MAJOR_VERSIONS
    assert minimums == diagnostics.MINIMUM_VERSIONS


def test_audit_log_check_warns_when_not_writable_and_ok_otherwise(tmp_path, monkeypatch):
    import os

    store = MemoryStore(tmp_path / "mem.sqlite3")
    log = tmp_path / "logs" / "audit.log"  # dir doesn't exist yet -> parent checked
    report = run_diagnostics(OdysseusConfig(), store, EchoProvider(), tmp_path, audit_log_path=log)
    assert next(c for c in report.checks if c.name == "audit_log").status == CheckStatus.OK

    real_access = os.access
    monkeypatch.setattr(
        os, "access",
        lambda p, mode, *a, **k: False if Path(p) == tmp_path and mode == os.W_OK
        else real_access(p, mode, *a, **k),
    )
    report = run_diagnostics(OdysseusConfig(), store, EchoProvider(), tmp_path, audit_log_path=log)
    check = next(c for c in report.checks if c.name == "audit_log")
    assert check.status == CheckStatus.WARNING
    assert "not writable" in check.detail


def test_audit_log_check_warns_when_path_is_wrong_kind_of_entry(tmp_path):
    from odysseus.health.diagnostics import check_audit_log

    blocker = tmp_path / "logs"
    blocker.write_text("not a directory")  # file where the log dir should be
    assert check_audit_log(blocker / "audit.log").status == CheckStatus.WARNING

    as_dir = tmp_path / "audit.log"
    as_dir.mkdir()  # directory where the log file should be
    assert check_audit_log(as_dir).status == CheckStatus.WARNING


def test_safe_check_failure_detail_names_exception_type():
    from odysseus.health.diagnostics import _safe_check

    def boom():
        raise KeyError("x")

    result = _safe_check("demo", boom)
    assert result.status == CheckStatus.CRITICAL
    assert "KeyError" in result.detail


def test_empty_report_is_not_reported_healthy():
    from datetime import datetime, timezone

    from odysseus.health.diagnostics import CheckStatus, HealthReport

    report = HealthReport(generated_at=datetime.now(timezone.utc))
    assert report.overall_status == CheckStatus.WARNING


def test_fallback_provider_gets_its_own_check(tmp_path):
    """The provider the orchestrator degrades to is diagnosed too (F073)."""
    config = OdysseusConfig()
    memory = MemoryStore(tmp_path / "mem.sqlite3")

    class Primary(EchoProvider):
        name = "primary"

    report = run_diagnostics(
        config, memory, Primary(), disk_path=tmp_path, fallback_provider=EchoProvider()
    )
    by_name = {c.name: c for c in report.checks}
    assert by_name["model_provider:primary"].status == CheckStatus.OK
    assert by_name["fallback_provider:echo"].status == CheckStatus.OK
    assert report.overall_status == CheckStatus.OK

    # Omitted, or the very same object as the primary: no separate check.
    same = EchoProvider()
    for kwargs in ({}, {"fallback_provider": same}):
        report = run_diagnostics(config, memory, same, disk_path=tmp_path, **kwargs)
        assert not [c for c in report.checks if c.name.startswith("fallback_provider")]


def test_unhealthy_fallback_is_warning_alone_and_critical_with_unhealthy_primary(tmp_path):
    config = OdysseusConfig()
    memory = MemoryStore(tmp_path / "mem.sqlite3")

    class Down(EchoProvider):
        name = "down"

        def health_check(self, timeout_seconds=None):
            return False, "pretend unreachable"

    class Exploding(EchoProvider):
        name = "exploding"

        def health_check(self, timeout_seconds=None):
            raise RuntimeError("boom")

    def fallback_check(primary, fallback):
        report = run_diagnostics(
            config, memory, primary, disk_path=tmp_path, fallback_provider=fallback
        )
        return [c for c in report.checks if c.name.startswith("fallback_provider")][0], report

    # Safety net gone but the primary still answers: WARNING.
    check, report = fallback_check(EchoProvider(), Down())
    assert check.name == "fallback_provider:down"
    assert check.status == CheckStatus.WARNING
    assert report.overall_status == CheckStatus.WARNING

    # Neither can answer: CRITICAL, and the detail says why.
    check, report = fallback_check(Down(), Down())
    assert check.status == CheckStatus.CRITICAL
    assert "no model provider can answer" in check.detail
    assert report.overall_status == CheckStatus.CRITICAL

    # A healthy fallback keeps an unreachable primary at WARNING overall.
    check, report = fallback_check(Down(), EchoProvider())
    assert check.status == CheckStatus.OK
    assert report.overall_status == CheckStatus.WARNING

    # A fallback whose check raises is isolated like any other check.
    check, report = fallback_check(EchoProvider(), Exploding())
    assert check.name == "fallback_provider:exploding"
    assert check.status == CheckStatus.CRITICAL
    assert "boom" in check.detail
    assert any(c.name == "disk_space" for c in report.checks)


@pytest.mark.parametrize("allow_external", [False, True])
@pytest.mark.parametrize("name", ["olama", "Ollama", "openai"])
def test_config_check_warns_for_unknown_provider_whatever_the_external_gate(name, allow_external):
    """An unknown model.provider is answered by the echo fallback regardless of
    identity.allow_external_providers, so the config check must say so in both
    cases (it used to report OK when the gate was open)."""
    from odysseus.health.diagnostics import check_config
    from odysseus.models.registry import build_provider

    cfg = OdysseusConfig(
        model={"provider": name},
        identity={"allow_external_providers": allow_external},
    )
    # The premise: no real model is built for this name, gate open or not.
    built = build_provider(cfg.model, cfg.identity.allow_external_providers)
    assert built.name == "echo"

    result = check_config(cfg)
    assert result.status == CheckStatus.WARNING
    assert repr(name) in result.detail
    assert "echo fallback will be used" in result.detail
    assert "ollama" in result.detail  # names the values that would work


def test_config_check_known_providers_follow_the_registry():
    from odysseus.health.diagnostics import check_config
    from odysseus.models.registry import BUILTIN_PROVIDERS

    assert BUILTIN_PROVIDERS == {"echo", "ollama"}
    for name in BUILTIN_PROVIDERS:
        cfg = OdysseusConfig(model={"provider": name})
        assert check_config(cfg).status == CheckStatus.OK


def _approved_entries(store, count):
    from odysseus.memory.models import MemoryEntry

    ids = []
    for i in range(count):
        entry = store.submit_candidate(
            MemoryEntry(content=f"fact number {i}", source="test", confidence=0.9)
        )
        store.approve(entry.id, reviewer="tester")
        ids.append(entry.id)
    return ids


def _damage_row(store, entry_id, column, value):
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(store.db_path)) as conn:
        conn.execute(f"UPDATE memory_entries SET {column} = ? WHERE id = ?", (value, entry_id))
        conn.commit()


@pytest.mark.parametrize(
    "column,value",
    [("status", "archived"), ("tags", "not json"), ("created_at", "yesterday")],
)
def test_memory_store_check_warns_about_an_unreadable_row(tmp_path, column, value):
    from odysseus.exceptions import MemoryError_
    from odysseus.health.diagnostics import check_memory_store

    store = MemoryStore(tmp_path / "mem.sqlite3")
    ids = _approved_entries(store, 3)
    assert check_memory_store(store).status == CheckStatus.OK
    assert store.unreadable_entry_ids() == []

    _damage_row(store, ids[1], column, value)

    # SQLite itself is satisfied, but the row cannot be shown.
    assert store.integrity_check() == (True, "ok")
    with pytest.raises(MemoryError_):
        store.get(ids[1])
    assert store.unreadable_entry_ids() == [ids[1]]
    result = check_memory_store(store)
    assert result.status == CheckStatus.WARNING
    assert "1 stored memory entry cannot be read" in result.detail
    assert f"id {ids[1]}" in result.detail
    # The check observes only: the damaged row is still there, unchanged.
    assert sum(store.count_by_status().values()) == 3
    assert store.unreadable_entry_ids() == [ids[1]]


def test_memory_store_check_caps_the_unreadable_ids_it_names(tmp_path):
    from odysseus.health.diagnostics import check_memory_store

    store = MemoryStore(tmp_path / "mem.sqlite3")
    ids = _approved_entries(store, 8)
    for entry_id in ids[:7]:
        _damage_row(store, entry_id, "tags", "{")
    result = check_memory_store(store)
    assert result.status == CheckStatus.WARNING
    assert "7 stored memory entries cannot be read" in result.detail
    assert "and 2 more" in result.detail
    assert f"{ids[5]}" not in result.detail.split("):")[0].split("(id ")[1]


def test_run_diagnostics_reports_an_unreadable_memory_row(tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite3")
    ids = _approved_entries(store, 1)
    _damage_row(store, ids[0], "status", "archived")
    report = run_diagnostics(OdysseusConfig(), store, EchoProvider(), disk_path=tmp_path)
    check = [c for c in report.checks if c.name == "memory_store"][0]
    assert check.status == CheckStatus.WARNING
    assert report.overall_status == CheckStatus.WARNING


def test_memory_store_check_accepts_a_store_without_the_unreadable_scan(tmp_path):
    from odysseus.health.diagnostics import check_memory_store

    real = MemoryStore(tmp_path / "mem.sqlite3")

    class OlderStore:
        db_path = real.db_path
        integrity_check = staticmethod(real.integrity_check)
        count_by_status = staticmethod(real.count_by_status)

    assert check_memory_store(OlderStore()).status == CheckStatus.OK


def test_memory_store_check_mentions_quarantined_rows(tmp_path):
    from odysseus.health.diagnostics import check_memory_store

    store = MemoryStore(tmp_path / "mem.sqlite3")
    ids = _approved_entries(store, 3)
    assert store.count_quarantined() == 0
    assert "quarantined" not in check_memory_store(store).detail

    _damage_row(store, ids[0], "tags", "not json")
    _damage_row(store, ids[2], "status", "archived")
    store.quarantine(ids[0], reviewer="tester")

    # One row is aside, one is still unreadable: the warning names both facts.
    assert store.count_quarantined() == 1
    result = check_memory_store(store)
    assert result.status == CheckStatus.WARNING
    assert "1 stored memory entry cannot be read" in result.detail
    assert "quarantined=1" in result.detail

    store.quarantine(ids[2], reviewer="tester")
    assert store.count_quarantined() == 2
    result = check_memory_store(store)
    # Quarantined rows are dealt with, so they do not degrade the status.
    assert result.status == CheckStatus.OK
    assert "counts={'approved': 1}" in result.detail
    assert "quarantined=2 (see `memory list-quarantined`)" in result.detail


def test_count_quarantined_does_not_create_the_quarantine_table(tmp_path):
    import sqlite3
    from contextlib import closing

    store = MemoryStore(tmp_path / "mem.sqlite3")
    _approved_entries(store, 1)
    assert store.count_quarantined() == 0
    with closing(sqlite3.connect(store.db_path)) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "memory_quarantine" not in tables


def test_run_diagnostics_reports_quarantined_rows_without_degrading(tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite3")
    ids = _approved_entries(store, 2)
    _damage_row(store, ids[1], "created_at", "yesterday")
    store.quarantine(ids[1], reviewer="tester")
    report = run_diagnostics(OdysseusConfig(), store, EchoProvider(), disk_path=tmp_path)
    check = [c for c in report.checks if c.name == "memory_store"][0]
    assert check.status == CheckStatus.OK
    assert "quarantined=1" in check.detail
