from __future__ import annotations

import os

import pytest

from odysseus.config import load_config
from odysseus.exceptions import ConfigError


def test_defaults_with_empty_file(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    config = load_config(empty)
    assert config.identity.name == "Jarvis"
    assert config.model.provider == "echo"
    assert config.memory.auto_approve_threshold is None


def test_loads_yaml_file(tmp_path):
    path = tmp_path / "custom.yaml"
    path.write_text("identity:\n  name: TestBot\nmodel:\n  provider: ollama\n")
    config = load_config(path)
    assert config.identity.name == "TestBot"
    assert config.model.provider == "ollama"


def test_env_override(tmp_path, monkeypatch):
    path = tmp_path / "custom.yaml"
    path.write_text("model:\n  provider: echo\n")
    monkeypatch.setenv("ODYSSEUS_MODEL__PROVIDER", "ollama")
    config = load_config(path)
    assert config.model.provider == "ollama"


def test_explicit_overrides_win(tmp_path, monkeypatch):
    path = tmp_path / "custom.yaml"
    path.write_text("model:\n  provider: echo\n")
    monkeypatch.setenv("ODYSSEUS_MODEL__PROVIDER", "ollama")
    config = load_config(path, overrides={"model": {"provider": "echo"}})
    assert config.model.provider == "echo"


def test_malformed_yaml_raises(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("identity: [this is: not, valid")
    with pytest.raises(ConfigError):
        load_config(path)


def test_non_mapping_yaml_raises(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n")
    with pytest.raises(ConfigError):
        load_config(path)


def test_invalid_value_raises(tmp_path):
    path = tmp_path / "bad_value.yaml"
    path.write_text("memory:\n  auto_approve_threshold: 5.0\n")  # out of 0..1 range
    with pytest.raises(ConfigError):
        load_config(path)


def test_inverted_health_thresholds_are_rejected(tmp_path):
    bad_disk = tmp_path / "disk.yaml"
    bad_disk.write_text("health:\n  disk_warn_percent: 95\n  disk_critical_percent: 85\n")
    with pytest.raises(ConfigError):
        load_config(bad_disk)
    bad_ram = tmp_path / "ram.yaml"
    bad_ram.write_text(
        "health:\n  ram_warn_available_percent: 5\n  ram_critical_available_percent: 15\n"
    )
    with pytest.raises(ConfigError):
        load_config(bad_ram)


def test_unknown_log_level_is_rejected_and_known_is_normalised(tmp_path):
    bad = tmp_path / "level.yaml"
    bad.write_text("log_level: LOUD\n")
    with pytest.raises(ConfigError):
        load_config(bad)
    good = tmp_path / "ok.yaml"
    good.write_text("log_level: debug\n")
    assert load_config(good).log_level == "DEBUG"


@pytest.mark.parametrize("url", ["localhost:11434", "ftp://localhost", "http://", ""])
def test_malformed_model_base_url_is_rejected(tmp_path, url):
    bad = tmp_path / "url.yaml"
    bad.write_text(f"model:\n  base_url: '{url}'\n")
    with pytest.raises(ConfigError):
        load_config(bad)
    good = tmp_path / "ok.yaml"
    good.write_text("model:\n  base_url: ' http://127.0.0.1:11434 '\n")
    assert load_config(good).model.base_url == "http://127.0.0.1:11434"


def test_explicit_missing_config_path_is_an_error(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "typo.yaml")
    # The default path stays optional.
    assert load_config() is not None


def test_ollama_provider_rejects_blank_model_name(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("model:\n  provider: ollama\n  model_name: '  '\n")
    with pytest.raises(ConfigError):
        load_config(bad)
    ok = tmp_path / "ok.yaml"
    ok.write_text("model:\n  provider: echo\n  model_name: ''\n")
    assert load_config(ok).model.provider == "echo"
