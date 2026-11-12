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


_PUNCT = ".,;:!?\"'()[]{}<>"


_MAX_QUERY_TERMS = 50


# SQLite stores integers in 64 bits. Binding a larger Python int raises a raw
# ``OverflowError`` (not a ``sqlite3.Error``), which would escape this class's
# typed errors, so ids and limits are checked against this range first.
_SQLITE_MAX_INT = 2**63 - 1
_SQLITE_MIN_INT = -(2**63)


# English function words that say nothing about a query's topic. Without this,
# almost any question ("What is the capital of France?") matched every approved
# entry containing "the" or "what", so unrelated memories were injected into
# the model prompt. Deliberately small and conservative: only words of three or
# more letters (shorter ones are already ignored) and no word that is commonly
# also a name or noun ("will", "can", "may"). English only.
_STOP_WORDS = frozenset(
    """
    the and but for nor not are was were been being has have had does did
    what which who whom whose when where why how this that these those
    with from into about than then there here you your yours she her hers
    him his its our ours they them their theirs any some
    """.split()
)


def _escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards so user text is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Separates content and tags in the text a query is matched against, so a
# phrase cannot match across the boundary between them (ASCII unit separator).
_FIELD_SEP = "\x1f"


def _searchable_text(content: str | None, tags_json: str | None) -> str:
    """Case-folded text ``query`` matches against: the content plus the tags.

    Registered as the SQL function ``searchable``. Tags are decoded from
    their stored JSON so a tag matches as the text the user typed (the raw
    JSON escapes non-ASCII characters). It must not raise: an unreadable
    tags value simply contributes nothing, and the row is then judged on
    its content alone (``_row_to_entry`` still reports it as corrupt if it
    is returned).
    """
    parts = [content or ""]
    try:
        tags = json.loads(tags_json) if tags_json else []
    except (ValueError, TypeError):
        tags = []
    if isinstance(tags, list):
        parts.extend(t for t in tags if isinstance(t, str))
    return _FIELD_SEP.join(parts).casefold()


def _decode_tags(tags_json: str | None) -> tuple[str, ...]:
    """Decode the stored ``tags`` column, which this store only ever writes as a JSON list.

    Any other JSON value is refused rather than coerced: ``tuple()`` of a
    JSON string yields one "tag" per character and of a JSON object its
    keys, which would display tags nobody stored (and that ``query``
    ignores). Raises ``ValueError``/``TypeError`` for the caller to wrap.
    """
    tags = json.loads(tags_json)
    if not isinstance(tags, list):
        raise ValueError(f"tags must be a JSON list, found a JSON {type(tags).__name__}")
    return tuple(tags)


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    try:
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            source=row["source"],
            confidence=row["confidence"],
            status=MemoryStatus(row["status"]),
            tags=_decode_tags(row["tags"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row["reviewed_at"] else None,
            reviewer=row["reviewer"],
        )
    except (ValueError, TypeError) as exc:
        # A hand-edited/corrupt row must surface as the store's typed error so
        # callers (e.g. the orchestrator) can degrade instead of crashing.
        raise MemoryError_(f"Corrupt memory row id={row['id']}: {exc}") from exc


class MemoryStore:
    """Persistent memory with structured storage, retrieval, and review inbox."""

    def __init__(self, db_path: str | Path, auto_approve_threshold: float | None = None) -> None:
        if auto_approve_threshold is not None and not (
            isinstance(auto_approve_threshold, (int, float))
            and not isinstance(auto_approve_threshold, bool)
            and 0.0 <= auto_approve_threshold <= 1.0
        ):
            # Direct construction bypasses config validation; a negative value
            # would silently auto-approve every candidate (skipping review).
            raise ValueError("auto_approve_threshold must be a number between 0.0 and 1.0")
        self.db_path = Path(db_path)
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # A file where the data directory should be, or an unwritable
            # parent: surface it as the store's typed error (like every other
            # storage failure) so callers can report or degrade, not crash.
            raise MemoryError_(
                f"Could not create memory database directory {self.db_path.parent}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        self.auto_approve_threshold = auto_approve_threshold
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0)
        except sqlite3.Error as exc:
            raise MemoryError_(f"Could not open memory database at {self.db_path}: {exc}") from exc
        conn.row_factory = sqlite3.Row
        return conn

    def _read(self, sql: str, params=(), *, one: bool = False, setup=None):
        """Run a read-only query, converting sqlite3 failures to MemoryError_."""
        try:
            with closing(self._connect()) as conn:
                if setup is not None:
                    setup(conn)
                cur = conn.execute(sql, params)
                return cur.fetchone() if one else cur.fetchall()
        except sqlite3.Error as exc:
            raise MemoryError_(f"Could not read memory database at {self.db_path}: {exc}") from exc

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
        if not isinstance(entry, MemoryEntry):
            raise TypeError(
                f"submit_candidate expects a MemoryEntry, got {type(entry).__name__}"
            )
        duplicate = self._find_live_duplicate(entry.content)
        if duplicate is not None:
            audit(
                "memory.duplicate_candidate",
                id=duplicate.id,
                source=entry.source,
                status=duplicate.status.value,
            )
            return duplicate

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

    def _find_live_duplicate(self, content: str) -> MemoryEntry | None:
        """Existing PENDING/APPROVED entry with the same content (ignoring case
        and surrounding/repeated whitespace), if any. REJECTED entries do not
        count, so a previously rejected fact can be proposed again."""
        wanted = " ".join(content.split()).casefold()
        rows = self._read(
            "SELECT * FROM memory_entries WHERE status IN (?, ?) ORDER BY id ASC",
            (MemoryStatus.PENDING.value, MemoryStatus.APPROVED.value),
        )
        for row in rows:
            if " ".join(row["content"].split()).casefold() == wanted:
                return _row_to_entry(row)
        return None

    def find_duplicate(self, content: str) -> MemoryEntry | None:
        """The PENDING/APPROVED entry ``submit_candidate`` would return instead of
        storing ``content`` again, or ``None`` if it would be stored as new (F009).

        Read-only. Lets a caller tell "kept the existing entry" apart from
        "stored a new one": in the first case the source, confidence and tags
        of the new submission are not stored (the audit log notes its source only).
        """
        if not isinstance(content, str):
            raise TypeError(f"content must be a string, got {type(content).__name__}")
        return self._find_live_duplicate(content)

    # -- Reading -------------------------------------------------------

    def get(self, entry_id: int) -> MemoryEntry | None:
        if (
            isinstance(entry_id, int)
            and not isinstance(entry_id, bool)
            and not _SQLITE_MIN_INT <= entry_id <= _SQLITE_MAX_INT
        ):
            # No row can have an id SQLite cannot store; say "not found"
            # (as for any other unknown id) instead of an OverflowError.
            return None
        row = self._read(
            "SELECT * FROM memory_entries WHERE id = ?", (entry_id,), one=True
        )
        return _row_to_entry(row) if row else None

    def list_pending(self) -> list[MemoryEntry]:
        """All entries waiting in the review inbox."""
        return self._list_by_status(MemoryStatus.PENDING)

    def list_approved(self) -> list[MemoryEntry]:
        """All permanent (approved) memory entries."""
        return self._list_by_status(MemoryStatus.APPROVED)

    def list_rejected(self) -> list[MemoryEntry]:
        """All rejected or retracted entries (never used in answers).

        Kept so every review decision stays inspectable: who rejected or
        withdrew what, and when (``reviewer`` / ``reviewed_at``).
        """
        return self._list_by_status(MemoryStatus.REJECTED)

    def _list_by_status(self, status: MemoryStatus) -> list[MemoryEntry]:
        rows = self._read(
            "SELECT * FROM memory_entries WHERE status = ? ORDER BY created_at ASC",
            (status.value,),
        )
        return [_row_to_entry(r) for r in rows]

    def query(self, text: str, limit: int = 20) -> list[MemoryEntry]:
        """Simple keyword search over APPROVED memory only.

        Matches entries whose content or tags contain any "significant" word
        (length >= 3 and not an English stop word such as "the"/"what",
        see ``_STOP_WORDS``) from ``text``, OR the whole ``text`` as a
        substring (of the content or of a single tag). Results are ordered by how many distinct query terms
        they match, then confidence, then recency. This is a deliberately
        simple retrieval strategy --
        good enough for Milestone A's "structured storage and
        retrieval" requirement -- and is the one place a smarter
        retriever (embeddings, FTS5, etc.) would plug in later without
        changing the ``MemoryStore`` API.

        Pending/rejected entries are never surfaced to normal retrieval --
        only reviewed, permanent memory is queryable this way.
        """
        if not isinstance(text, str):
            raise TypeError(f"query text must be a string, got {type(text).__name__}")
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(f"query limit must be an int, got {type(limit).__name__}")
        if not text.strip() or limit <= 0:
            # A blank query would otherwise match every approved entry, and a
            # negative LIMIT means "no limit" in SQLite.
            return []
        # A limit beyond SQLite's integer range means "all of them".
        limit = min(limit, _SQLITE_MAX_INT)
        # Strip surrounding punctuation so "pizza?" matches "pizza".
        # Stop words are not search terms on their own; the whole text is
        # still matched below, so a query that *is* a stop word ("the") or a
        # phrase containing one ("the umbrella") keeps working.
        words = [
            w
            for w in (t.strip(_PUNCT) for t in text.split())
            if len(w) >= 3 and w.casefold() not in _STOP_WORDS
        ]
        # Bound the OR-chain: SQLite rejects expression trees deeper than 1000,
        # so an unbounded query (e.g. a pasted document) would raise a raw
        # sqlite3.OperationalError. Keep the whole text plus the first
        # distinct words (order-preserving, deterministic).
        distinct_words = list(dict.fromkeys(words))[:_MAX_QUERY_TERMS]
        patterns = {text} | set(distinct_words)
        # Unicode-aware case-insensitive match: SQLite's built-in LIKE only
        # folds ASCII, so fold both sides with str.casefold() (same rule the
        # duplicate check uses). Tags are searched too, so an entry filed
        # under a tag is found by that word even when its content does not
        # repeat it.
        match = "searchable(content, tags) LIKE ? ESCAPE '\\'"
        clauses = " OR ".join([match] * len(patterns))
        # Relevance first: an entry matching more of the query's distinct
        # terms outranks one matching fewer, so a high-confidence entry that
        # only shares a common word (e.g. "the") cannot crowd the relevant
        # one out of a small ``limit``. Confidence/recency break ties.
        relevance = " + ".join([f"({match})"] * len(patterns))
        likes = [f"%{_escape_like(p.casefold())}%" for p in sorted(patterns)]
        params: list[object] = [MemoryStatus.APPROVED.value, *likes, *likes, limit]
        rows = self._read(
            f"SELECT * FROM memory_entries "
            f"WHERE status = ? AND ({clauses}) "
            f"ORDER BY {relevance} DESC, confidence DESC, created_at DESC LIMIT ?",
            params,
            setup=lambda conn: conn.create_function(
                "searchable", 2, _searchable_text, deterministic=True
            ),
        )
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
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ReviewInboxError("A non-empty reviewer is required for review decisions")
        reviewer = reviewer.strip()  # keep the recorded identity free of stray whitespace
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
                # Status guard in the UPDATE itself: a concurrent reviewer who
                # changed the entry since the check above must not be overwritten.
                cur = conn.execute(
                    "UPDATE memory_entries SET status = ?, reviewed_at = ?, reviewer = ? "
                    "WHERE id = ? AND status = ?",
                    (status.value, now.isoformat(), reviewer, entry_id, expected.value),
                )
                conn.commit()
            except sqlite3.Error as exc:
                raise MemoryError_(f"Could not update memory entry {entry_id}: {exc}") from exc
        if cur.rowcount != 1:
            raise ReviewInboxError(
                f"Entry {entry_id} changed status concurrently; review not applied"
            )
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
        rows = self._read("SELECT status, COUNT(*) as n FROM memory_entries GROUP BY status")
        return {row["status"]: row["n"] for row in rows}

    def unreadable_entry_ids(self) -> list[int]:
        """Ids of stored rows that cannot be decoded into a ``MemoryEntry`` (F009/F073).

        Such a row (unknown status, tags that are not a JSON list, a bad
        timestamp -- e.g. after a hand edit or a partial restore) passes
        SQLite's own integrity check, yet makes every listing or query that
        returns it raise ``MemoryError_``. Read-only: reads every row once
        and changes nothing. Raises ``MemoryError_`` only if the database
        itself cannot be read.
        """
        bad: list[int] = []
        for row in self._read("SELECT * FROM memory_entries ORDER BY id ASC"):
            try:
                _row_to_entry(row)
            except MemoryError_:
                bad.append(row["id"])
        return bad

    def integrity_check(self) -> tuple[bool, str]:
        """Run SQLite ``PRAGMA quick_check`` (F009/F073). Read-only.

        Returns (ok, detail); never raises on database errors.
        """
        try:
            with closing(self._connect()) as conn:
                rows = [r[0] for r in conn.execute("PRAGMA quick_check").fetchall()]
        except (sqlite3.Error, MemoryError_) as exc:
            return False, str(exc)
        if rows == ["ok"]:
            return True, "ok"
        return False, "; ".join(str(r) for r in rows[:5])
