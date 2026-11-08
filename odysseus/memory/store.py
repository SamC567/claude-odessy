"""SQLite-backed persistent memory store with a review-inbox workflow.

Design choices:
    - SQLite (stdlib ``sqlite3``) keeps this dependency-free and
      trivially portable; the schema is simple enough to migrate to
      another backend later without changing the ``MemoryStore`` API.
    - Every write goes through this one class, so it is the single
      place that enforces "candidates start PENDING, never APPROVED".
    - All failures are raised as ``MemoryError_`` / ``ReviewInboxError``
      so callers never need to know this is SQLite under the hood.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from odysseus.exceptions import MemoryError_, ReviewInboxError
from odysseus.logging_setup import audit
from odysseus.memory.models import MemoryEntry, MemoryStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewer TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_entries(status);
"""


def _escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards so user text is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    return MemoryEntry(
        id=row["id"],
        content=row["content"],
        source=row["source"],
        confidence=row["confidence"],
        status=MemoryStatus(row["status"]),
        tags=tuple(json.loads(row["tags"])),
        created_at=datetime.fromisoformat(row["created_at"]),
        reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
        reviewer=row["reviewer"],
    )


class MemoryStore:
    """Persistent memory with structured storage, retrieval, and review inbox."""

    def __init__(self, db_path: str | Path, auto_approve_threshold: float | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.auto_approve_threshold = auto_approve_threshold
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
        except sqlite3.Error as exc:
            raise MemoryError_(f"Could not open memory database at {self.db_path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            except sqlite3.Error as exc:
                raise MemoryError_(f"Could not initialise memory schema: {exc}") from exc

    # -- Writing -----------------------------------------------------

    def submit_candidate(self, entry: MemoryEntry) -> MemoryEntry:
        """Add a new candidate memory. Always lands as PENDING in the review inbox,

        unless ``auto_approve_threshold`` is configured and the entry's
        confidence meets it -- an explicit, auditable opt-in rather than
        a silent default.
        """
        status = MemoryStatus.PENDING
        reviewed_at = None
        reviewer = None
        if (
            self.auto_approve_threshold is not None
            and entry.confidence >= self.auto_approve_threshold
        ):
            status = MemoryStatus.APPROVED
            reviewed_at = datetime.now(timezone.utc)
            reviewer = "auto-approval-rule"

        with closing(self._connect()) as conn:
            try:
                cur = conn.execute(
                    "INSERT INTO memory_entries "
                    "(content, source, confidence, status, tags, created_at, reviewed_at, reviewer) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry.content,
                        entry.source,
                        entry.confidence,
                        status.value,
                        json.dumps(list(entry.tags)),
                        entry.created_at.isoformat(),
                        reviewed_at.isoformat() if reviewed_at else None,
                        reviewer,
                    ),
                )
                conn.commit()
            except sqlite3.Error as exc:
                raise MemoryError_(f"Could not store memory candidate: {exc}") from exc

        new_id = cur.lastrowid
        audit(
            "memory.submit_candidate",
            id=new_id,
            source=entry.source,
            confidence=entry.confidence,
            status=status.value,
        )
        stored = self.get(new_id)
        assert stored is not None
        return stored

    # -- Reading -------------------------------------------------------

    def get(self, entry_id: int) -> MemoryEntry | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return _row_to_entry(row) if row else None

    def list_pending(self) -> list[MemoryEntry]:
        """All entries waiting in the review inbox."""
        return self._list_by_status(MemoryStatus.PENDING)

    def list_approved(self) -> list[MemoryEntry]:
        """All permanent (approved) memory entries."""
        return self._list_by_status(MemoryStatus.APPROVED)

    def _list_by_status(self, status: MemoryStatus) -> list[MemoryEntry]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM memory_entries WHERE status = ? ORDER BY created_at ASC",
                (status.value,),
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def query(self, text: str, limit: int = 20) -> list[MemoryEntry]:
        """Simple keyword search over APPROVED memory only.

        Matches entries whose content contains any "significant" word
        (length >= 3) from ``text``, OR the whole ``text`` as a
        substring. This is a deliberately simple retrieval strategy --
        good enough for Milestone A's "structured storage and
        retrieval" requirement -- and is the one place a smarter
        retriever (embeddings, FTS5, etc.) would plug in later without
        changing the ``MemoryStore`` API.

        Pending/rejected entries are never surfaced to normal retrieval --
        only reviewed, permanent memory is queryable this way.
        """
        words = [w for w in text.split() if len(w) >= 3]
        patterns = {text} | set(words)
        clauses = " OR ".join(["content LIKE ? ESCAPE '\\'"] * len(patterns))
        params: list[object] = [MemoryStatus.APPROVED.value]
        params.extend(f"%{_escape_like(p)}%" for p in patterns)
        params.append(limit)
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_entries "
                f"WHERE status = ? AND ({clauses}) "
                f"ORDER BY confidence DESC, created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    # -- Review inbox ----------------------------------------------------

    def approve(self, entry_id: int, reviewer: str) -> MemoryEntry:
        return self._review(entry_id, MemoryStatus.APPROVED, reviewer)

    def reject(self, entry_id: int, reviewer: str) -> MemoryEntry:
        return self._review(entry_id, MemoryStatus.REJECTED, reviewer)

    def retract(self, entry_id: int, reviewer: str) -> MemoryEntry:
        """Withdraw a previously APPROVED entry (it becomes REJECTED).

        The row is kept (not deleted) so provenance and the audit trail
        survive and the action is inspectable; the entry simply stops
        being returned by ``query``.
        """
        return self._review(
            entry_id, MemoryStatus.REJECTED, reviewer, expected=MemoryStatus.APPROVED
        )

    def _review(
        self,
        entry_id: int,
        status: MemoryStatus,
        reviewer: str,
        expected: MemoryStatus = MemoryStatus.PENDING,
    ) -> MemoryEntry:
        existing = self.get(entry_id)
        if existing is None:
            raise ReviewInboxError(f"No memory entry with id={entry_id}")
        if existing.status != expected:
            raise ReviewInboxError(
                f"Entry {entry_id} is {existing.status.value}; "
                f"only {expected.value} entries can be {status.value} here"
            )
        now = datetime.now(timezone.utc)
        with closing(self._connect()) as conn:
            try:
                conn.execute(
                    "UPDATE memory_entries SET status = ?, reviewed_at = ?, reviewer = ? "
                    "WHERE id = ?",
                    (status.value, now.isoformat(), reviewer, entry_id),
                )
                conn.commit()
            except sqlite3.Error as exc:
                raise MemoryError_(f"Could not update memory entry {entry_id}: {exc}") from exc
        audit(
            "memory.review",
            id=entry_id,
            decision=status.value,
            reviewer=reviewer,
            previous=expected.value,
        )
        updated = self.get(entry_id)
        assert updated is not None
        return updated

    def count_by_status(self) -> dict[str, int]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as n FROM memory_entries GROUP BY status"
            ).fetchall()
        return {row["status"]: row["n"] for row in rows}
