"""Command-line entry point tying the Milestone A modules together.

Usage:
    python -m odysseus.cli chat "hello there"
    python -m odysseus.cli health
    python -m odysseus.cli memory list-pending
    python -m odysseus.cli memory list-approved
    python -m odysseus.cli memory approve <id>
    python -m odysseus.cli memory reject <id>
    python -m odysseus.cli memory remember "fact" --source user --confidence 0.8
    python -m odysseus.cli config show
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from odysseus.config import load_config
from odysseus.core.identity import JarvisIdentity
from odysseus.core.orchestrator import Orchestrator
from odysseus.exceptions import MemoryError_, OdysseusError
from odysseus.health.diagnostics import run_diagnostics
from odysseus.logging_setup import configure_logging
from odysseus.memory.store import MemoryStore
from odysseus.models.registry import build_provider


def _build_orchestrator(config_path: str | None) -> tuple[Orchestrator, object]:
    config = load_config(config_path)
    configure_logging(config.log_level, audit_log_path="data/audit.log")
    identity = JarvisIdentity.from_config(config.identity)
    provider = build_provider(config.model, config.identity.allow_external_providers)
    memory = MemoryStore(config.memory.db_path, config.memory.auto_approve_threshold)
    orchestrator = Orchestrator(identity=identity, provider=provider, memory=memory)
    return orchestrator, config


def cmd_chat(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    try:
        result = orchestrator.respond(args.prompt)
    except ValueError as exc:
        # Invalid user input (empty/blank prompt): report cleanly instead of
        # a traceback, same convention as ``memory remember``.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{orchestrator.identity.name}: {result.text}")
    if result.degraded:
        # Only claim a provider fallback when one happened; a memory-only
        # degradation is still answered by the primary provider.
        prefix = f"fell back to {result.provider_used}; " if result.used_fallback else ""
        print(f"(degraded: {prefix}{result.degraded_reason})", file=sys.stderr)
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    # disk_path is left unset so disk space is measured on the memory DB's
    # volume (the data that matters), not the process working directory.
    try:
        orchestrator, config = _build_orchestrator(args.config)
        memory, provider, memory_error = orchestrator.memory, orchestrator.provider, None
    except MemoryError_ as exc:
        # A corrupt/unreadable memory DB must still yield a diagnostic report
        # (CRITICAL memory_store) rather than only an error message.
        config = load_config(args.config)
        configure_logging(config.log_level, audit_log_path="data/audit.log")
        provider = build_provider(config.model, config.identity.allow_external_providers)
        memory, memory_error = None, str(exc)
    report = run_diagnostics(config, memory, provider,
                             audit_log_path=Path("data/audit.log"),
                             memory_store_error=memory_error)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(report.summary_line())
        for check in report.checks:
            print(f"  - {check.name}: {check.status.value} — {check.detail}")
    return 1 if report.overall_status.value == "critical" else 0


def cmd_memory_list_pending(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    pending = orchestrator.memory.list_pending()
    if not pending:
        print("No pending review items.")
        return 0
    for entry in pending:
        print(f"[{entry.id}] ({entry.confidence:.2f}, {entry.source}) {entry.content}")
    return 0


def cmd_memory_list_approved(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
    approved = orchestrator.memory.list_approved()
    if not approved:
        print("No approved memories.")
        return 0
    for entry in approved:
        print(
            f"[{entry.id}] ({entry.confidence:.2f}, {entry.source}, "
            f"reviewer={entry.reviewer}) {entry.content}"
        )
    return 0


def cmd_memory_remember(args: argparse.Namespace) -> int:
    orchestrator, _ = _build_orchestrator(args.config)
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
        print(f"error: {exc}", file=sys.stderr)
        return 2
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
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
