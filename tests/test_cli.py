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


def test_cli_memory_remember_rejects_invalid_input_cleanly(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "memory", "remember", "x",
               "--source", "user", "--confidence", "2"])
    assert rc == 2
    assert "confidence" in capsys.readouterr().err


def test_cli_health_measures_disk_at_memory_db_directory(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "health"])
    assert rc == 0
    assert f"used at {tmp_path}" in capsys.readouterr().out


def test_cli_health_reports_corrupt_memory_db_instead_of_erroring(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    (tmp_path / "mem.sqlite3").write_bytes(b"this is not a sqlite database" * 200)
    rc = main(["--config", str(config_path), "health"])
    out = capsys.readouterr().out
    assert rc == 1  # CRITICAL overall
    assert "memory_store: critical" in out
    assert "python_version" in out  # the rest of the report is still produced


def test_cli_chat_memory_only_degradation_does_not_claim_provider_fallback(
    tmp_path, capsys, monkeypatch
):
    from odysseus.exceptions import MemoryError_
    from odysseus.memory.store import MemoryStore

    def boom(self, *args, **kwargs):
        raise MemoryError_("disk I/O error")

    monkeypatch.setattr(MemoryStore, "query", boom)
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "chat", "hello"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "memory unavailable" in err
    assert "fell back" not in err


def test_cli_survives_unusable_audit_log_location(tmp_path, capsys, monkeypatch):
    """A file where the ``data`` directory should be must not crash every command."""
    import logging

    from odysseus.logging_setup import AUDIT_LOGGER_NAME

    config_path = _write_config(tmp_path)
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    (workdir / "data").write_text("not a directory")  # blocks data/audit.log
    monkeypatch.chdir(workdir)

    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    collector = _Collect()
    logging.getLogger("odysseus").addHandler(collector)
    try:
        rc = main(["--config", str(config_path), "health"])
        assert rc == 0  # audit_log is a WARNING, not a crash
        out = capsys.readouterr().out
        assert "audit_log: warning" in out

        # The degradation is announced, and the audit trail still goes somewhere.
        assert any(
            r.levelno == logging.WARNING and "NOT persisted" in r.getMessage() for r in records
        )
        handlers = logging.getLogger(AUDIT_LOGGER_NAME).handlers
        assert handlers and not any(isinstance(h, logging.FileHandler) for h in handlers)

        assert main(["--config", str(config_path), "chat", "hello"]) == 0
    finally:
        logging.getLogger("odysseus").removeHandler(collector)


def test_cli_chat_rejects_blank_prompt_cleanly(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    for prompt in ("", "   "):
        rc = main(["--config", str(config_path), "chat", prompt])
        captured = capsys.readouterr()
        assert rc == 2
        assert "error: prompt must not be empty" in captured.err
        assert "Jarvis:" not in captured.out


def test_cli_reports_uncreatable_memory_db_directory(tmp_path, capsys):
    """A file where the memory DB's directory should be: report it, no traceback."""
    blocker = tmp_path / "data"
    blocker.write_text("not a directory")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"memory:\n  db_path: {blocker / 'sub' / 'mem.sqlite3'}\n"
        f"model:\n  provider: echo\n"
    )
    rc = main(["--config", str(config_path), "health"])
    out = capsys.readouterr().out
    assert rc == 1  # CRITICAL overall
    assert "memory_store: critical" in out
    assert "python_version" in out  # the rest of the report is still produced

    rc = main(["--config", str(config_path), "chat", "hello"])
    assert rc == 2
    assert "error: Could not create memory database directory" in capsys.readouterr().err


def test_cli_chat_reports_which_memories_informed_the_answer(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    main(base + ["memory", "remember", "Sam likes pizza", "--source", "user-note",
                 "--confidence", "0.9"])
    main(base + ["memory", "remember", "pizza is pending", "--source", "unreviewed",
                 "--confidence", "0.9"])
    main(base + ["memory", "approve", "1"])
    capsys.readouterr()

    assert main(base + ["chat", "what about pizza?"]) == 0
    captured = capsys.readouterr()
    assert "(memory used: [1] source=user-note)" in captured.err
    # Unreviewed memory is never used, so it is never cited either.
    assert "unreviewed" not in captured.err
    assert "memory used" not in captured.out


def test_cli_chat_cites_no_memory_when_none_was_used(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    assert main(["--config", str(config_path), "chat", "hello"]) == 0
    assert "memory used" not in capsys.readouterr().err


def test_cli_memory_list_rejected_shows_decision_trail(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path), "memory"]
    assert main(base + ["list-rejected"]) == 0
    assert "No rejected or retracted memories." in capsys.readouterr().out
    main(base + ["remember", "wrong fact", "--source", "guess", "--confidence", "0.2"])
    main(base + ["remember", "stale fact", "--source", "note", "--confidence", "0.9"])
    main(base + ["reject", "1", "--reviewer", "alice"])
    main(base + ["approve", "2"])
    main(base + ["forget", "2", "--reviewer", "bob"])
    capsys.readouterr()
    assert main(base + ["list-rejected"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert "[1]" in lines[0] and "wrong fact" in lines[0] and "reviewer=alice" in lines[0]
    assert "[2]" in lines[1] and "stale fact" in lines[1] and "reviewer=bob" in lines[1]
    assert "reviewed=20" in lines[0]


def test_cli_memory_show_displays_full_record_including_tags(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path), "memory"]
    main(base + ["remember", "likes green tea", "--source", "user-note",
                 "--confidence", "0.7", "--tags", "food", "drink"])
    capsys.readouterr()

    assert main(base + ["show", "1"]) == 0
    out = capsys.readouterr().out
    assert "[1] likes green tea" in out
    assert "status:     pending" in out
    assert "source:     user-note" in out
    assert "confidence: 0.70" in out
    assert "tags:       food, drink" in out
    assert "created:    20" in out
    assert "reviewer:   -" in out and "reviewed:   -" in out

    main(base + ["approve", "1", "--reviewer", "alice"])
    capsys.readouterr()
    assert main(base + ["show", "1"]) == 0
    out = capsys.readouterr().out
    assert "status:     approved" in out
    assert "reviewer:   alice" in out
    assert "reviewed:   20" in out


def test_cli_memory_show_unknown_id_is_a_clean_error(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    assert main(["--config", str(config_path), "memory", "show", "99"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "No memory entry with id=99" in captured.err
