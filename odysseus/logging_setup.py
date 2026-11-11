"""Centralised logging configuration.

Every module gets its logger via ``logging.getLogger(__name__)`` as usual;
this module just configures handlers/formatters once, consistently, and
is where an audit-log handler is attached (every autonomous action should
be logged per the project's security requirements).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_CONFIGURED = False

AUDIT_LOGGER_NAME = "odysseus.audit"


def configure_logging(level: str = "INFO", audit_log_path: str | Path | None = None) -> None:
    """Configure root + audit logging. Safe to call multiple times (idempotent)."""
    global _CONFIGURED

    root = logging.getLogger("odysseus")
    root.setLevel(level.upper())

    if not _CONFIGURED:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
        root.addHandler(handler)
        root.propagate = False
        _CONFIGURED = True

    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.setLevel("INFO")
    # Reset handlers so repeated calls (e.g. in tests) don't duplicate output.
    audit_logger.handlers = []
    if audit_log_path:
        path = Path(audit_log_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(path, encoding="utf-8")
        except OSError as exc:
            # An unusable audit log location must not take the whole system
            # down (the health check reports it as a WARNING). Keep the trail
            # visible on stderr and say loudly that it is not being persisted.
            audit_logger.addHandler(logging.StreamHandler(stream=sys.stderr))
            root.warning(
                "audit log %s is not writable (%s: %s); audit records go to "
                "stderr only and are NOT persisted",
                path, type(exc).__name__, exc,
            )
        else:
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            audit_logger.addHandler(file_handler)
    else:
        audit_logger.addHandler(logging.StreamHandler(stream=sys.stderr))
    audit_logger.propagate = False


def audit(action: str, **details: object) -> None:
    """Record an auditable autonomous action.

    Every autonomous action (model call, memory write, review-inbox
    decision, etc.) should go through this so there is a durable,
    human-readable trail of what the system did and why.
    """
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    detail_str = " ".join(f"{k}={v!r}" for k, v in details.items())
    logger.info("%s %s", action, detail_str)
