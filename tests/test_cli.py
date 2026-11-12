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


def test_cli_audit_log_path_is_configurable(tmp_path, capsys, monkeypatch):
    """``audit_log_path`` decides where the audit trail goes and what ``health`` checks."""
    import logging

    from odysseus.logging_setup import AUDIT_LOGGER_NAME

    audit_path = tmp_path / "trail" / "my-audit.log"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"memory:\n  db_path: {(tmp_path / 'mem.sqlite3').as_posix()}\n"
        f"model:\n  provider: echo\n"
        f"audit_log_path: {audit_path.as_posix()}\n"
    )
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    try:
        assert main(["--config", str(config_path), "chat", "hello"]) == 0
        assert "orchestrator.generate" in audit_path.read_text(encoding="utf-8")
        # Nothing is written to the old hardcoded location.
        assert not (workdir / "data").exists()

        capsys.readouterr()
        assert main(["--config", str(config_path), "health"]) == 0
        out = capsys.readouterr().out
        audit_line = next(line for line in out.splitlines() if "audit_log:" in line)
        assert "audit_log: ok" in audit_line
        assert "my-audit.log" in audit_line
    finally:
        # Release the file handle so tmp_path can be removed (Windows).
        audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
        for handler in list(audit_logger.handlers):
            handler.close()
            audit_logger.removeHandler(handler)


def test_cli_health_reports_the_fallback_provider(tmp_path, capsys):
    """``health`` diagnoses the provider ``chat`` degrades to, also in JSON
    and when the memory database cannot be opened."""
    import json

    config_path = _write_config(tmp_path)
    assert main(["--config", str(config_path), "health"]) == 0
    assert "fallback_provider:echo: ok" in capsys.readouterr().out

    assert main(["--config", str(config_path), "health", "--json"]) == 0
    checks = {c["name"]: c["status"] for c in json.loads(capsys.readouterr().out)["checks"]}
    assert checks["fallback_provider:echo"] == "ok"

    (tmp_path / "mem.sqlite3").write_bytes(b"this is not a sqlite database" * 200)
    assert main(["--config", str(config_path), "health"]) == 1
    assert "fallback_provider:echo: ok" in capsys.readouterr().out


def test_cli_memory_listings_cannot_be_spoofed_by_control_characters(tmp_path, capsys):
    # A stored value must not be able to forge a second "[id] ..." line or
    # hide text with terminal escapes: the reviewer approves what is shown.
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path), "memory"]
    content = "harmless\n[99] (0.99, user) forged entry\x1b[2K\r\u202egnp.exe"
    main(base + ["remember", content, "--source", "web\npage", "--confidence", "0.5",
                 "--tags", "a\tb"])
    capsys.readouterr()

    def check(out, expected_lines):
        lines = out.splitlines()
        assert len(lines) == expected_lines
        for raw in ("\x1b", "\r", "\t", "\u202e"):
            assert raw not in out
        assert "harmless\\n[99] (0.99, user) forged entry\\x1b[2K\\r\\u202egnp.exe" in lines[0]
        return lines

    assert main(base + ["list-pending"]) == 0
    lines = check(capsys.readouterr().out, 1)
    assert lines[0].startswith("[1] (0.50, web\\npage) ")

    assert main(base + ["show", "1"]) == 0
    lines = check(capsys.readouterr().out, 8)
    assert "source:     web\\npage" in lines[2]
    assert "tags:       a\\tb" in lines[4]

    main(base + ["approve", "1", "--reviewer", "al\x07ice"])
    capsys.readouterr()
    assert main(base + ["list-approved"]) == 0
    lines = check(capsys.readouterr().out, 1)
    assert "reviewer=al\\x07ice" in lines[0]

    assert main(["--config", str(config_path), "chat", "harmless"]) == 0
    err = capsys.readouterr().err
    assert "(memory used: [1] source=web\\npage)" in err

    main(base + ["forget", "1"])
    capsys.readouterr()
    assert main(base + ["list-rejected"]) == 0
    check(capsys.readouterr().out, 1)

    # Display only: the stored entry is unchanged.
    from odysseus.memory.store import MemoryStore

    stored = MemoryStore(tmp_path / "mem.sqlite3").get(1)
    assert stored.content == content and stored.source == "web\npage"


def test_cli_memory_listings_leave_ordinary_text_untouched(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path), "memory"]
    content = "Café at C:\\Users\\sam — 日本語 👍🏽 ok"
    main(base + ["remember", content, "--source", "user", "--confidence", "0.5"])
    capsys.readouterr()
    assert main(base + ["list-pending"]) == 0
    assert capsys.readouterr().out == f"[1] (0.50, user) {content}\n"


def _approve_three_pizza_memories(base):
    for n, fact in enumerate(("Sam likes pizza", "pizza night is Friday",
                              "the pizza place closes at ten"), start=1):
        main(base + ["memory", "remember", fact, "--source", f"note-{n}",
                     "--confidence", "0.9"])
        main(base + ["memory", "approve", str(n)])


def test_cli_chat_obeys_configured_memory_context_limit(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"memory:\n  db_path: {tmp_path / 'mem.sqlite3'}\n  context_limit: 1\n"
        f"model:\n  provider: echo\n"
    )
    base = ["--config", str(config_path)]
    _approve_three_pizza_memories(base)
    capsys.readouterr()

    assert main(base + ["chat", "what about pizza?"]) == 0
    err = capsys.readouterr().err
    assert err.count("source=note-") == 1


def test_cli_chat_memory_context_limit_zero_keeps_memory_out_of_the_prompt(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    _approve_three_pizza_memories(base)
    capsys.readouterr()

    # Default limit: all three matching memories are cited.
    assert main(base + ["chat", "what about pizza?"]) == 0
    assert capsys.readouterr().err.count("source=note-") == 3

    config_path.write_text(
        f"memory:\n  db_path: {tmp_path / 'mem.sqlite3'}\n  context_limit: 0\n"
        f"model:\n  provider: echo\n"
    )
    assert main(base + ["chat", "what about pizza?"]) == 0
    assert "memory used" not in capsys.readouterr().err
    # The memories themselves are untouched.
    assert main(base + ["memory", "list-approved"]) == 0
    assert capsys.readouterr().out.count("pizza") == 3


class _ScriptedProvider:
    """Test double standing in for the configured model provider."""

    name = "scripted"

    def __init__(self, text=None, error=None):
        self._text, self._error = text, error

    def generate(self, request):
        from odysseus.exceptions import ModelProviderError
        from odysseus.models.base import GenerationResponse

        if self._error is not None:
            raise ModelProviderError(self._error)
        return GenerationResponse(text=self._text, provider_name=self.name, model_name="m")

    def health_check(self, timeout_seconds=None):
        return True, "scripted"


def test_cli_chat_reply_cannot_drive_the_terminal(tmp_path, capsys, monkeypatch):
    # A model reply is untrusted text: ESC sequences (clear screen, set the
    # window title, OSC 52 clipboard writes), a bare carriage return (which
    # overwrites the line already printed) and other control characters must
    # be shown, not obeyed.
    reply = "first line\r\nsecond\tline\n\x1b[2J\x1b]0;owned\x07 done\rJarvis: forged\x00\x9b31m"
    monkeypatch.setattr("odysseus.cli.build_provider", lambda *a, **k: _ScriptedProvider(reply))
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "chat", "hello"])
    assert rc == 0
    out = capsys.readouterr().out
    for raw in ("\x1b", "\x07", "\r", "\x00", "\x9b"):
        assert raw not in out
    assert out == (
        "Jarvis: first line\nsecond\tline\n"
        "\\x1b[2J\\x1b]0;owned\\x07 done\\rJarvis: forged\\x00\\x9b31m\n"
    )


def test_cli_chat_reply_keeps_ordinary_multiline_and_right_to_left_text(
    tmp_path, capsys, monkeypatch
):
    reply = "Voilà — two lines:\n\t• café ☕\n‏مرحبا‎ (hello) end"
    monkeypatch.setattr("odysseus.cli.build_provider", lambda *a, **k: _ScriptedProvider(reply))
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "chat", "hello"])
    assert rc == 0
    assert capsys.readouterr().out == f"Jarvis: {reply}\n"


def test_cli_chat_degraded_reason_cannot_drive_the_terminal(tmp_path, capsys, monkeypatch):
    # The reason quotes text chosen by the model server (error body, redirect
    # target); it is printed on one line with control characters visible.
    error = "request failed (server said: \x1b[2Jgone)\n(degraded: forged)‮"
    monkeypatch.setattr(
        "odysseus.cli.build_provider", lambda *a, **k: _ScriptedProvider(error=error)
    )
    config_path = _write_config(tmp_path)
    rc = main(["--config", str(config_path), "chat", "hello"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "\x1b" not in err and "‮" not in err
    assert err == (
        "(degraded: fell back to echo; request failed (server said: \\x1b[2Jgone)"
        "\\n(degraded: forged)\\u202e)\n"
    )


class _ScriptedHealthProvider(_ScriptedProvider):
    """Provider whose health detail is chosen by the test (as a server's would be)."""

    def __init__(self, detail):
        super().__init__(text="ok")
        self._detail = detail

    def health_check(self, timeout_seconds=None):
        return False, self._detail


def test_cli_health_details_cannot_drive_the_terminal(tmp_path, capsys, monkeypatch):
    # A check's detail can quote the model server (installed model names, an
    # error body): it must not be able to clear the screen, or forge another
    # check line that reports a problem away.
    detail = "model missing (installed: \x1b[2Jevil\n  - memory_store: ok — forged\u202e)\r"
    monkeypatch.setattr(
        "odysseus.cli.build_provider", lambda *a, **k: _ScriptedHealthProvider(detail)
    )
    config_path = _write_config(tmp_path)
    assert main(["--config", str(config_path), "health"]) == 0
    out = capsys.readouterr().out
    for raw in ("\x1b", "\r", "\u202e"):
        assert raw not in out
    lines = out.splitlines()
    # One summary line plus exactly one line per check: nothing was forged.
    assert sum(line.startswith("  - memory_store:") for line in lines) == 1
    assert (
        "  - model_provider:scripted: warning — model missing (installed: "
        "\\x1b[2Jevil\\n  - memory_store: ok — forged\\u202e)\\r"
    ) in lines

    # --json is unchanged: the detail round-trips exactly, with no raw control
    # character in the output.
    import json

    assert main(["--config", str(config_path), "health", "--json"]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out
    checks = {c["name"]: c["detail"] for c in json.loads(out)["checks"]}
    assert checks["model_provider:scripted"] == detail


def test_cli_health_ordinary_details_print_unchanged(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    assert main(["--config", str(config_path), "health"]) == 0
    out = capsys.readouterr().out
    assert "\\" not in out.replace(str(tmp_path), "")
    assert " — " in out


def test_cli_error_message_cannot_drive_the_terminal(tmp_path, capsys, monkeypatch):
    # An error can quote text that is not the program's own -- here a database
    # path from the environment. It must not clear the screen, reorder the
    # line, or add a second line that itself looks like an ``error:`` report.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    hostile = blocker / "a\x1b[2Jb\nerror: forged‮\r" / "mem.sqlite3"
    monkeypatch.setenv("ODYSSEUS_MEMORY__DB_PATH", str(hostile))
    config_path = _write_config(tmp_path)

    rc = main(["--config", str(config_path), "chat", "hello"])
    err = capsys.readouterr().err
    assert rc == 2
    for raw in ("\x1b", "\r", "‮"):
        assert raw not in err
    assert "\\x1b[2J" in err  # shown, not obeyed
    error_lines = [line for line in err.splitlines() if line.startswith("error:")]
    assert len(error_lines) == 1
    assert error_lines[0].startswith("error: Could not create memory database directory")
    assert "forged" in err  # nothing is dropped, only made visible


def test_cli_multiline_config_error_stays_readable(tmp_path, capsys):
    # Guard: configuration errors are legitimately multi-line and must stay so.
    config_path = tmp_path / "config.yaml"
    config_path.write_text("log_level: LOUD\n")
    rc = main(["--config", str(config_path), "chat", "hello"])
    err = capsys.readouterr().err
    assert rc == 2
    lines = err.splitlines()
    assert lines[0].startswith("error: Invalid configuration:")
    assert any("log_level must be one of" in line for line in lines[1:])
    assert "\\n" not in err


def test_cli_memory_remember_says_when_the_fact_is_already_stored(tmp_path, capsys):
    # F009 source tracking: a duplicate submission is not stored, so the CLI
    # must not report it as "Submitted" and must say its provenance was dropped.
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path), "memory"]
    assert main(base + ["remember", "Sam likes pizza", "--source", "user-note",
                        "--confidence", "0.9"]) == 0
    assert "Submitted as entry [1] with status=pending" in capsys.readouterr().out
    main(base + ["approve", "1"])
    capsys.readouterr()

    rc = main(base + ["remember", "  sam LIKES   pizza ", "--source", "web\npage",
                      "--confidence", "0.2", "--tags", "food"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Submitted" not in out
    assert "Already stored as entry [1] with status=approved" in out
    # The kept entry's provenance is shown, not the one just typed.
    assert "source=user-note, confidence=0.90" in out
    assert "not stored with it" in out
    assert len(out.splitlines()) == 1

    main(base + ["show", "1"])
    shown = capsys.readouterr().out
    assert "source:     user-note" in shown and "tags:       -" in shown

    # A retracted fact can be proposed again and is reported as new.
    main(base + ["forget", "1"])
    capsys.readouterr()
    assert main(base + ["remember", "Sam likes pizza", "--source", "user-note",
                        "--confidence", "0.9"]) == 0
    assert "Submitted as entry [2] with status=pending" in capsys.readouterr().out


def test_cli_memory_remember_existing_source_cannot_drive_the_terminal(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path), "memory"]
    main(base + ["remember", "a fact", "--source", "web\n[9] forged\x1b[2J", "--confidence", "0.5"])
    capsys.readouterr()
    main(base + ["remember", "a fact", "--source", "x", "--confidence", "0.5"])
    out = capsys.readouterr().out
    assert "\x1b" not in out and len(out.splitlines()) == 1
    assert "Already stored as entry [1]" in out


def _remember_and_approve(base, content, source, confidence, tags=()):
    args = ["memory", "remember", content, "--source", source, "--confidence", confidence]
    if tags:
        args += ["--tags", *tags]
    assert main(base + args) == 0


def test_cli_memory_search_shows_ranked_approved_matches_only(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    _remember_and_approve(base, "Sam likes pizza", "user-note", "0.5")
    _remember_and_approve(base, "Sam likes pizza with olives", "diary", "0.4")
    _remember_and_approve(base, "pizza is pending", "unreviewed", "0.9")
    _remember_and_approve(base, "The cat is called Tom", "vet", "0.9", tags=("pets",))
    for entry_id in ("1", "2", "4"):
        assert main(base + ["memory", "approve", entry_id]) == 0
    capsys.readouterr()

    assert main(base + ["memory", "search", "pizza olives?"]) == 0
    captured = capsys.readouterr()
    # Best match first (two terms beat one), with id, confidence and source.
    assert captured.out.splitlines() == [
        "[2] (0.40, diary) Sam likes pizza with olives",
        "[1] (0.50, user-note) Sam likes pizza",
    ]
    # Unreviewed memory is not retrievable, and a search is not an answer.
    assert "unreviewed" not in captured.out
    assert "Jarvis:" not in captured.out

    # Tags are searched as well, as in chat retrieval.
    assert main(base + ["memory", "search", "pets"]) == 0
    assert capsys.readouterr().out.splitlines() == ["[4] (0.90, vet) The cat is called Tom"]

    assert main(base + ["memory", "search", "umbrella"]) == 0
    assert capsys.readouterr().out.strip() == "No approved memories match."


def test_cli_memory_search_explain_names_the_terms_each_memory_matched(tmp_path, capsys):
    """F009: `memory search --explain` says why the entries are in this order."""
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    _remember_and_approve(base, "Sam likes pizza", "user-note", "0.9")
    _remember_and_approve(base, "Sam likes pizza with olives", "diary", "0.4")
    _remember_and_approve(base, "The cat is called Tom", "vet", "0.9", tags=("pets",))
    for entry_id in ("1", "2", "3"):
        assert main(base + ["memory", "approve", entry_id]) == 0
    capsys.readouterr()

    assert main(base + ["memory", "search", "pizza olives?", "--explain"]) == 0
    captured = capsys.readouterr()
    # The lower-confidence entry is first because it matched more terms.
    assert captured.out.splitlines() == [
        'Search terms (3): "pizza olives?", "pizza", "olives"',
        "[2] (0.40, diary) Sam likes pizza with olives",
        '    matched 2 of 3: "pizza", "olives"',
        "[1] (0.90, user-note) Sam likes pizza",
        '    matched 1 of 3: "pizza"',
    ]

    # A match through a tag is explained too.
    assert main(base + ["memory", "search", "pets", "--explain"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        'Search terms (1): "pets"',
        "[3] (0.90, vet) The cat is called Tom",
        '    matched 1 of 1: "pets"',
    ]

    # Without the flag the output is exactly what it was.
    assert main(base + ["memory", "search", "pizza olives?"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "[2] (0.40, diary) Sam likes pizza with olives",
        "[1] (0.90, user-note) Sam likes pizza",
    ]

    assert main(base + ["memory", "search", "umbrella", "--explain"]) == 0
    assert capsys.readouterr().out.strip() == "No approved memories match."


def test_cli_memory_search_explain_cannot_forge_lines_or_drive_the_terminal(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    _remember_and_approve(base, "pizza night", "a", "0.9")
    assert main(base + ["memory", "approve", "1"]) == 0
    capsys.readouterr()

    assert main(base + ["memory", "search", "pizza\n[9] forged \x1b[2J", "--explain"]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and len(out.splitlines()) == 3
    assert out.splitlines()[1:] == ["[1] (0.90, a) pizza night", '    matched 1 of 4: "pizza"']


def test_cli_memory_search_limit_defaults_to_what_chat_uses(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"memory:\n  db_path: {tmp_path / 'mem.sqlite3'}\n  context_limit: 1\n"
        f"model:\n  provider: echo\n"
    )
    base = ["--config", str(config_path)]
    _remember_and_approve(base, "pizza on Friday", "a", "0.9")
    _remember_and_approve(base, "pizza on Sunday", "b", "0.5")
    assert main(base + ["memory", "approve", "1"]) == 0
    assert main(base + ["memory", "approve", "2"]) == 0
    capsys.readouterr()

    assert main(base + ["memory", "search", "pizza"]) == 0
    assert capsys.readouterr().out.splitlines() == ["[1] (0.90, a) pizza on Friday"]

    assert main(base + ["memory", "search", "pizza", "--limit", "5"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 2

    assert main(base + ["memory", "search", "pizza", "--limit", "0"]) == 2
    assert "error: --limit must be at least 1" in capsys.readouterr().err


def test_cli_memory_search_with_context_limit_zero_says_so(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"memory:\n  db_path: {tmp_path / 'mem.sqlite3'}\n  context_limit: 0\n"
        f"model:\n  provider: echo\n"
    )
    base = ["--config", str(config_path)]
    _remember_and_approve(base, "pizza on Friday", "a", "0.9")
    assert main(base + ["memory", "approve", "1"]) == 0
    capsys.readouterr()

    assert main(base + ["memory", "search", "pizza"]) == 0
    out = capsys.readouterr().out
    assert "memory.context_limit is 0" in out and "pizza on Friday" not in out

    assert main(base + ["memory", "search", "pizza", "--limit", "3"]) == 0
    assert "[1] (0.90, a) pizza on Friday" in capsys.readouterr().out


def test_cli_memory_search_rejects_blank_text_and_escapes_stored_text(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    assert main(base + ["memory", "search", "   "]) == 2
    assert "error: search text must not be empty" in capsys.readouterr().err

    _remember_and_approve(base, "pizza\n[9] (1.00, admin) forged", "src\x1b[2J", "0.9")
    assert main(base + ["memory", "approve", "1"]) == 0
    capsys.readouterr()
    assert main(base + ["memory", "search", "pizza"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == ["[1] (0.90, src\\x1b[2J) pizza\\n[9] (1.00, admin) forged"]


def test_cli_memory_id_or_limit_beyond_sqlite_range_is_not_a_traceback(tmp_path, capsys):
    """F009: an id or --limit larger than a 64-bit integer is handled like any
    other unknown id / generous limit, not an OverflowError traceback."""
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path), "memory"]
    huge = "99999999999999999999999"
    assert main(base + ["remember", "Sam likes pizza", "--source", "user", "--confidence", "0.8"]) == 0
    assert main(base + ["approve", "1", "--reviewer", "sam"]) == 0
    capsys.readouterr()

    assert main(base + ["show", huge]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"No memory entry with id={huge}" in captured.err

    assert main(base + ["search", "pizza", "--limit", huge]) == 0
    assert capsys.readouterr().out.splitlines() == ["[1] (0.80, user) Sam likes pizza"]


def _corrupt_row(tmp_path, column, value):
    """Store one fact through the CLI, then hand-edit a column as a bad restore would."""
    import sqlite3

    config_path = _write_config(tmp_path)
    assert main(
        ["--config", str(config_path), "memory", "remember", "the gate code is 4471",
         "--source", "user", "--confidence", "0.9", "--tags", "home"]
    ) == 0
    conn = sqlite3.connect(tmp_path / "mem.sqlite3")
    conn.execute(f"UPDATE memory_entries SET {column} = ? WHERE id = 1", (value,))
    conn.commit()
    conn.close()
    return config_path


def test_cli_memory_show_raw_prints_a_corrupt_row_as_stored(tmp_path, capsys):
    """F009: a row the store refuses as corrupt can still be read, undecoded."""
    config_path = _corrupt_row(tmp_path, "status", "archived")
    capsys.readouterr()

    rc = main(["--config", str(config_path), "memory", "show", "1", "--raw"])

    captured = capsys.readouterr()
    assert rc == 0
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert lines[0] == "[1] raw stored values (not decoded or validated)"
    fields = {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in lines[1:]}
    assert fields["content"] == "'the gate code is 4471'"
    assert fields["status"] == "'archived'"
    assert fields["source"] == "'user'"
    assert fields["confidence"] == "0.9"
    assert fields["tags"] == "'[\"home\"]'"
    assert fields["reviewed_at"] == "NULL"
    assert fields["reviewer"] == "NULL"


def test_cli_memory_show_on_a_corrupt_row_points_to_raw(tmp_path, capsys):
    config_path = _corrupt_row(tmp_path, "tags", "not json")
    capsys.readouterr()

    rc = main(["--config", str(config_path), "memory", "show", "1"])

    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == ""
    err_lines = captured.err.splitlines()
    assert err_lines[0].startswith("error: Corrupt memory row id=1")
    assert err_lines[1] == "  (run 'memory show 1 --raw' to see the values as stored)"


def test_cli_memory_show_raw_cannot_forge_lines_or_drive_the_terminal(tmp_path, capsys):
    config_path = _corrupt_row(tmp_path, "source", "user\n[2] forged \x1b[2J‮")
    capsys.readouterr()

    rc = main(["--config", str(config_path), "memory", "show", "1", "--raw"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "\x1b" not in out and "‮" not in out
    assert not any(line.startswith("[2]") for line in out.splitlines())
    assert len(out.splitlines()) == 9  # header + the 8 other columns, one line each


def test_cli_memory_show_raw_unknown_id_is_a_clean_error(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    for entry_id in ("999", str(2**70)):
        rc = main(["--config", str(config_path), "memory", "show", entry_id, "--raw"])
        captured = capsys.readouterr()
        assert rc == 2
        assert captured.out == ""
        assert f"No memory entry with id={entry_id}" in captured.err


def test_cli_memory_show_raw_changes_nothing(tmp_path, capsys):
    """Read-only: the corrupt row is still stored exactly as it was."""
    import sqlite3

    config_path = _corrupt_row(tmp_path, "created_at", "yesterday")
    db = tmp_path / "mem.sqlite3"

    def dump():
        conn = sqlite3.connect(db)
        try:
            return conn.execute("SELECT * FROM memory_entries").fetchall()
        finally:
            conn.close()

    before = dump()
    assert main(["--config", str(config_path), "memory", "show", "1", "--raw"]) == 0
    assert dump() == before


def test_cli_memory_list_approved_tag_lists_only_that_tag(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    _remember_and_approve(base, "The cat is called Tom", "vet", "0.9", tags=("Pets",))
    _remember_and_approve(base, "Pets are mentioned here only", "note", "0.5", tags=("misc",))
    _remember_and_approve(base, "Untagged fact", "note", "0.5")
    _remember_and_approve(base, "Pending fact", "note", "0.5", tags=("pets",))
    for entry_id in ("1", "2", "3"):
        assert main(base + ["memory", "approve", entry_id]) == 0
    capsys.readouterr()

    assert main(base + ["memory", "list-approved", "--tag", "pets"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines() == ["[1] (0.90, vet, reviewer=cli-user) The cat is called Tom"]

    # A whole-tag match, not a substring: "pet" is not the tag "Pets".
    assert main(base + ["memory", "list-approved", "--tag", "pet"]) == 0
    assert capsys.readouterr().out.strip() == 'No approved memories tagged "pet".'

    # Without --tag the listing is unchanged.
    assert main(base + ["memory", "list-approved"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 3


def test_cli_memory_list_approved_blank_tag_is_a_clean_error(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    _remember_and_approve(base, "The cat is called Tom", "vet", "0.9", tags=("pets",))
    assert main(base + ["memory", "approve", "1"]) == 0
    capsys.readouterr()
    assert main(base + ["memory", "list-approved", "--tag", "  "]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "error: tag must not be empty"


def test_cli_memory_list_approved_tag_cannot_forge_lines_or_drive_the_terminal(tmp_path, capsys):
    config_path = _write_config(tmp_path)
    base = ["--config", str(config_path)]
    assert main(base + ["memory", "list-approved", "--tag", "x\n[9] (1.00, forged) fact\x1b[2J"]) == 0
    out = capsys.readouterr().out
    assert len(out.splitlines()) == 1
    assert "\x1b" not in out and "\\n" in out and "\\x1b" in out
