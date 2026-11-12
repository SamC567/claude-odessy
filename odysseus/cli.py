"""Command-line entry point tying the Milestone A modules together.

Usage:
    python -m odysseus.cli chat "hello there"
    python -m odysseus.cli health
    python -m odysseus.cli memory list-pending
    python -m odysseus.cli memory list-approved
    python -m odysseus.cli memory list-rejected
    python -m odysseus.cli memory show <id> [--raw]
    python -m odysseus.cli memory search "words" [--limit N]
    python -m odysseus.cli memory approve <id>
    python -m odysseus.cli memory reject <id>
    python -m odysseus.cli memory forget <id>
    python -m odysseus.cli memory remember "fact" --source user --confidence 0.8
    python -m odysseus.cli config show
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

from odysseus.config import load_config
from odysseus.core.identity import JarvisIdentity
from odysseus.core.orchestrator import Orchestrator
from odysseus.exceptions import MemoryError_, OdysseusError
from odysseus.health.diagnostics import run_diagnostics
from odysseus.logging_setup import configure_logging
from odysseus.memory.store import MemoryStore
from odysseus.models.echo_provider import EchoProvider
from odysseus.models.registry import build_provider


# Bidirectional-text controls: invisible, and able to reorder how the rest of
# a line is displayed (so text can read differently from what is stored).
_BIDI_CONTROLS = frozenset("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _printable(value: object, multiline: bool = False) -> str:
    """Text from storage or a model made safe to print on a terminal.

    Review workflow (F009): a reviewer approves what the listing shows, so a
    stored value must not be able to change the listing itself. A newline in
    an entry could fake a second ``[id] ...`` line, and terminal escape
    sequences or bidi overrides could hide or reorder the real text. Control
    characters, line/paragraph separators and bidi controls are therefore
    shown as visible backslash escapes (``\\n``, ``\\x1b``, ``\\u202e``).
    Display only -- the stored entry is not modified.

    ``multiline=True`` is for a model reply (F001/F003), which is prose and
    may legitimately span lines and be written right-to-left: line breaks
    (``\\r\\n`` shown as a plain newline), tabs, line/paragraph separators
    and bidi controls are kept, while every other control character -- ESC
    above all, so no terminal escape sequence reaches the terminal -- is
    still shown as an escape.
    """
    text = str(value)
    if multiline:
        text = text.replace("\r\n", "\n")
    out = []
    for ch in text:
        category = unicodedata.category(ch)
        if multiline:
            unsafe = category == "Cc" and ch not in "\n\t"
        else:
            unsafe = category in ("Cc", "Zl", "Zp") or ch in _BIDI_CONTROLS
        out.append(ch.encode("unicode_escape").decode("ascii") if unsafe else ch)
    return "".join(out)


def _print_error(exc: object) -> None:
    """Print ``error: <message>`` on stderr without letting the message drive the terminal.

    A message can quote text that is not this program's: a path from the
    config file, an environment variable or ``--config``, a value from a
    corrupt memory row. Each line goes through the one-line ``_printable``
    (control characters and bidi controls shown as escapes). Line breaks are
    kept, because configuration errors are legitimately multi-line, but every
    continuation line is indented so that only the first line can start with
    ``error:`` -- a newline in a quoted value cannot add a second, forged
    error line.
    """
    lines = str(exc).replace("\r\n", "\n").split("\n")
    print("error: " + "\n  ".join(_printable(line) for line in lines), file=sys.stderr)


def _build_orchestrator(config_path: str | None) -> tuple[Orchestrator, object]:
    config = load_config(config_path)
    configure_logging(config.log_level, audit_log_path=config.audit_log_path)
    identity = JarvisIdentity.from_config(config.identity)
    provider = build_provider(config.model, config.identity.allow_external_providers)
    memory = MemoryStore(config.memory.db_path, config.memory.auto_approve_threshold)
    orchestrator = Orchestrator(
        identity=identity,
        provider=provider,
        memory=memory,
        memory_context_limit=config.memory.context_limit,
    )
    return orchestrator, config


def cmd_chat(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    try:
        result = orchestrator.respond(args.prompt)
    except ValueError as exc:
        # Invalid user input (empty/blank prompt): report cleanly instead of
        # a traceback, same convention as ``memory remember``.
        _print_error(exc)
        return 2
    # The reply is model output: it must not be able to drive the terminal.
    print(f"{orchestrator.identity.name}: {_printable(result.text, multiline=True)}")
    if result.memory_sources:
        # Source tracking (F009): say which approved memories informed the
        # answer, with the same [id] used by ``memory forget``. On stderr so
        # the answer on stdout stays unchanged.
        used = "; ".join(
            f"[{entry_id}] source={_printable(source)}" for entry_id, source in result.memory_sources
        )
        print(f"(memory used: {used})", file=sys.stderr)
    if result.degraded:
        # Only claim a provider fallback when one happened; a memory-only
        # degradation is still answered by the primary provider.
        prefix = f"fell back to {result.provider_used}; " if result.used_fallback else ""
        # The reason can quote text sent by the model server (its error body,
        # a redirect target), so it gets the one-line treatment.
        print(f"(degraded: {prefix}{_printable(result.degraded_reason)})", file=sys.stderr)
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    # disk_path is left unset so disk space is measured on the memory DB's
    # volume (the data that matters), not the process working directory.
    try:
        orchestrator, config = _build_orchestrator(args.config)
        memory, provider, memory_error = orchestrator.memory, orchestrator.provider, None
        fallback = orchestrator.fallback_provider
    except MemoryError_ as exc:
        # A corrupt/unreadable memory DB must still yield a diagnostic report
        # (CRITICAL memory_store) rather than only an error message.
        config = load_config(args.config)
        configure_logging(config.log_level, audit_log_path=config.audit_log_path)
        provider = build_provider(config.model, config.identity.allow_external_providers)
        memory, memory_error = None, str(exc)
        # Same default the Orchestrator would have used had it been built.
        fallback = EchoProvider()
    report = run_diagnostics(config, memory, provider,
                             audit_log_path=Path(config.audit_log_path),
                             memory_store_error=memory_error,
                             fallback_provider=fallback)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        # A detail can quote text chosen by the model server (installed model
        # names, an error body, a redirect target) or a path from config, so
        # every line gets the one-line treatment: one check, one line, and no
        # control character reaches the terminal. ``--json`` needs none of
        # this: json.dumps already escapes control characters.
        print(_printable(report.summary_line()))
        for check in report.checks:
            print(
                f"  - {_printable(check.name)}: {check.status.value} — "
                f"{_printable(check.detail)}"
            )
    return 1 if report.overall_status.value == "critical" else 0


def cmd_memory_list_pending(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    pending = orchestrator.memory.list_pending()
    if not pending:
        print("No pending review items.")
        return 0
    for entry in pending:
        print(
            f"[{entry.id}] ({entry.confidence:.2f}, {_printable(entry.source)}) "
            f"{_printable(entry.content)}"
        )
    return 0


def cmd_memory_list_approved(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    approved = orchestrator.memory.list_approved()
    if not approved:
        print("No approved memories.")
        return 0
    for entry in approved:
        print(
            f"[{entry.id}] ({entry.confidence:.2f}, {_printable(entry.source)}, "
            f"reviewer={_printable(entry.reviewer)}) {_printable(entry.content)}"
        )
    return 0


def cmd_memory_list_rejected(args: argparse.Namespace) -> int:
    # Review workflow (F009): rejected/retracted entries are kept, not
    # deleted, so the decision trail must be readable without opening SQLite.
    orchestrator, _ = _build_orchestrator(args.config)
    rejected = orchestrator.memory.list_rejected()
    if not rejected:
        print("No rejected or retracted memories.")
        return 0
    for entry in rejected:
        reviewed = entry.reviewed_at.isoformat(timespec="seconds") if entry.reviewed_at else "?"
        print(
            f"[{entry.id}] ({entry.confidence:.2f}, {_printable(entry.source)}, "
            f"reviewer={_printable(entry.reviewer)}, reviewed={reviewed}) "
            f"{_printable(entry.content)}"
        )
    return 0


def cmd_memory_show(args: argparse.Namespace) -> int:
    # Source tracking (F009): the one place the full stored record of an entry
    # is visible -- tags and creation time are otherwise write-only at the CLI.
    orchestrator, _ = _build_orchestrator(args.config)
    # ``getattr``: a store without the raw lookup simply has no --raw view.
    raw_row = getattr(orchestrator.memory, "raw_row", None)
    if args.raw:
        if raw_row is None:
            _print_error("this memory store cannot show raw stored values")
            return 2
        stored = raw_row(args.entry_id)
        if stored is None:
            print(f"error: No memory entry with id={args.entry_id}", file=sys.stderr)
            return 2
        # The values as stored, not decoded or validated: the one way to read
        # a row the store refuses as corrupt (health names such rows by id).
        # repr() keeps the stored type visible ('0.9' vs 0.9, b'...' for a
        # blob); _printable then covers what repr leaves alone (bidi controls).
        print(f"[{_printable(repr(stored.get('id')))}] raw stored values (not decoded or validated)")
        width = max(len(str(name)) for name in stored) + 1
        for name, value in stored.items():
            if name == "id":
                continue
            shown = "NULL" if value is None else _printable(repr(value))
            print(f"  {(str(name) + ':').ljust(width)} {shown}")
        return 0
    try:
        entry = orchestrator.memory.get(args.entry_id)
    except MemoryError_ as exc:
        # Say how the stored values can still be read, but only when they
        # can: if the raw lookup fails too, the database itself is the problem.
        try:
            readable_raw = raw_row is not None and raw_row(args.entry_id) is not None
        except MemoryError_:
            readable_raw = False
        if not readable_raw:
            raise
        _print_error(exc)
        print(
            f"  (run 'memory show {args.entry_id} --raw' to see the values as stored)",
            file=sys.stderr,
        )
        return 2
    if entry is None:
        print(f"error: No memory entry with id={args.entry_id}", file=sys.stderr)
        return 2

    def _when(value) -> str:
        return value.isoformat(timespec="seconds") if value else "-"

    print(f"[{entry.id}] {_printable(entry.content)}")
    print(f"  status:     {entry.status.value}")
    print(f"  source:     {_printable(entry.source)}")
    print(f"  confidence: {entry.confidence:.2f}")
    print(f"  tags:       {', '.join(_printable(t) for t in entry.tags) if entry.tags else '-'}")
    print(f"  created:    {_when(entry.created_at)}")
    print(f"  reviewer:   {_printable(entry.reviewer) if entry.reviewer else '-'}")
    print(f"  reviewed:   {_when(entry.reviewed_at)}")
    return 0


def cmd_memory_search(args: argparse.Namespace) -> int:
    # Retrieval (F009): show what ``MemoryStore.query`` returns for a text, in
    # ranked order, without calling a model. By default it uses the same limit
    # as ``chat`` (``memory.context_limit``), so the output is the set of
    # approved memories a chat with this text would put in the prompt.
    # Read-only: nothing is stored or audited.
    orchestrator, config = _build_orchestrator(args.config)
    if not args.query.strip():
        _print_error("search text must not be empty")
        return 2
    limit = args.limit if args.limit is not None else config.memory.context_limit
    if limit < 1:
        if args.limit is not None:
            _print_error("--limit must be at least 1")
            return 2
        print(
            "memory.context_limit is 0: chat adds no approved memory to the prompt. "
            "Use --limit N to search anyway."
        )
        return 0
    matches = orchestrator.memory.query(args.query, limit=limit)
    if not matches:
        print("No approved memories match.")
        return 0
    for entry in matches:
        print(
            f"[{entry.id}] ({entry.confidence:.2f}, {_printable(entry.source)}) "
            f"{_printable(entry.content)}"
        )
    return 0


def cmd_memory_remember(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    # Source tracking (F009): the store keeps an existing pending/approved
    # entry with the same content instead of storing it twice. Look first, so
    # the outcome can be reported as what it is. ``getattr``: a store without
    # the lookup is reported as before.
    find_duplicate = getattr(orchestrator.memory, "find_duplicate", None)
    existing = find_duplicate(args.content) if find_duplicate is not None else None
    try:
        entry = orchestrator.remember(
            content=args.content,
            source=args.source,
            confidence=args.confidence,
            tags=tuple(args.tags or ()),
        )
    except ValueError as exc:
        # Invalid user input (empty content/source, confidence outside 0..1):
        # report cleanly instead of a traceback.
        _print_error(exc)
        return 2
    if existing is not None and entry.id == existing.id:
        # Not "Submitted ... status=approved": that reads as if this
        # submission had been stored (and auto-approved). Nothing was stored,
        # and the provenance given on this command line is not kept on the entry
        # (only the audit log notes the duplicate's source).
        print(
            f"Already stored as entry [{entry.id}] with status={entry.status.value} "
            f"(source={_printable(entry.source)}, confidence={entry.confidence:.2f}); "
            "not added again. The source, confidence and tags given here were not stored with it."
        )
        return 0
    print(f"Submitted as entry [{entry.id}] with status={entry.status.value}")
    return 0


def cmd_memory_approve(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    entry = orchestrator.memory.approve(args.entry_id, reviewer=args.reviewer)
    print(f"Approved [{entry.id}]")
    return 0


def cmd_memory_reject(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    entry = orchestrator.memory.reject(args.entry_id, reviewer=args.reviewer)
    print(f"Rejected [{entry.id}]")
    return 0


def cmd_memory_forget(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    entry = orchestrator.memory.retract(args.entry_id, reviewer=args.reviewer)
    print(f"Retracted [{entry.id}] (no longer used in answers)")
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    _, config = _build_orchestrator(args.config)
    print(config.model_dump_json(indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="Odysseus/Jarvis Milestone A CLI")
    parser.add_argument("--config", default=None, help="Path to a YAML config file")
    sub = parser.add_subparsers(dest="command", required=True)

    chat = sub.add_parser("chat", help="Send a prompt and get a response")
    chat.add_argument("prompt")
    chat.set_defaults(func=cmd_chat)

    health = sub.add_parser("health", help="Run system health diagnostics")
    health.add_argument("--json", action="store_true")
    health.set_defaults(func=cmd_health)

    memory = sub.add_parser("memory", help="Manage persistent memory / review inbox")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)

    list_pending = memory_sub.add_parser("list-pending", help="List review-inbox items")
    list_pending.set_defaults(func=cmd_memory_list_pending)

    list_approved = memory_sub.add_parser(
        "list-approved", help="List approved memories (find ids for 'forget')"
    )
    list_approved.set_defaults(func=cmd_memory_list_approved)

    list_rejected = memory_sub.add_parser(
        "list-rejected", help="List rejected or retracted entries and who decided"
    )
    list_rejected.set_defaults(func=cmd_memory_list_rejected)

    show = memory_sub.add_parser(
        "show", help="Show one entry in full (status, source, tags, timestamps)"
    )
    show.add_argument("entry_id", type=int)
    show.add_argument(
        "--raw",
        action="store_true",
        help="Print the values exactly as stored, without decoding (works for a corrupt row)",
    )
    show.set_defaults(func=cmd_memory_show)

    search = memory_sub.add_parser(
        "search", help="Show which approved memories a text retrieves (no model call)"
    )
    search.add_argument("query")
    search.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum results (default: memory.context_limit, the number chat uses)",
    )
    search.set_defaults(func=cmd_memory_search)

    remember = memory_sub.add_parser("remember", help="Submit a candidate memory")
    remember.add_argument("content")
    remember.add_argument("--source", required=True)
    remember.add_argument("--confidence", type=float, required=True)
    remember.add_argument("--tags", nargs="*")
    remember.set_defaults(func=cmd_memory_remember)

    approve = memory_sub.add_parser("approve", help="Approve a pending entry")
    approve.add_argument("entry_id", type=int)
    approve.add_argument("--reviewer", default="cli-user")
    approve.set_defaults(func=cmd_memory_approve)

    reject = memory_sub.add_parser("reject", help="Reject a pending entry")
    reject.add_argument("entry_id", type=int)
    reject.add_argument("--reviewer", default="cli-user")
    reject.set_defaults(func=cmd_memory_reject)

    forget = memory_sub.add_parser("forget", help="Retract a previously approved entry")
    forget.add_argument("entry_id", type=int)
    forget.add_argument("--reviewer", default="cli-user")
    forget.set_defaults(func=cmd_memory_forget)

    config_cmd = sub.add_parser("config", help="Inspect effective configuration")
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True)
    show = config_sub.add_parser("show", help="Print effective configuration as JSON")
    show.set_defaults(func=cmd_config_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except OdysseusError as exc:
        _print_error(exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
