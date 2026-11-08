from __future__ import annotations

import os

import pytest

from odysseus.config import load_config
from odysseus.exceptions import ConfigError


def test_defaults_without_file(tmp_path):
    config = load_config(tmp_path / "does-not-exist.yaml")
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
