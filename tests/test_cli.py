from __future__ import annotations

from odysseus.cli import main


def _write_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"memory:\n  db_path: {tmp_path / 'mem.sqlite3'}\n"
        f"model:\n  provider: echo\n"
    )
    return config_path


def test_cli_chat_smoke(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "chat", "hello"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Jarvis:" in out


def test_cli_health_smoke(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "health"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "python_version" in out


def test_cli_memory_remember_and_list(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    rc = main(
        [
            "--config",
            str(config_path),
            "memory",
            "remember",
            "a test fact",
            "--source",
            "test",
            "--confidence",
            "0.5",
        ]
    )
    assert rc == 0
    capsys.readouterr()
    rc = main(["--config", str(config_path), "memory", "list-pending"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "a test fact" in out


def test_cli_memory_list_approved_and_forget(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path), "memory"]
    assert main(base + ["list-approved"]) == 0
    assert "No approved memories." in capsys.readouterr().out
    main(base + ["remember", "approved fact", "--source", "t", "--confidence", "0.5"])
    main(base + ["approve", "1"])
    capsys.readouterr()
    assert main(base + ["list-approved"]) == 0
    out = capsys.readouterr().out
    assert "[1]" in out and "approved fact" in out and "reviewer=cli-user" in out
    main(base + ["forget", "1"])
    capsys.readouterr()
    main(base + ["list-approved"])
    assert "No approved memories." in capsys.readouterr().out


def test_cli_config_show(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "config", "show"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"provider": "echo"' in out
