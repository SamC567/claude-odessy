"""Data model for a persistent memory entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class MemoryStatus(str, Enum):
    """Lifecycle of a memory entry.

    PENDING entries sit in the review inbox and are NOT returned by
    normal memory queries -- they only become usable, permanent memory
    once a human (or an explicitly auto-approved rule) promotes them to
    APPROVED. This is the "Review Inbox before proposed information
    becomes permanent memory" requirement.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class MemoryEntry:
    """A single fact/note the system knows, with provenance.

    ``source`` and ``confidence`` are mandatory so every memory can be
    traced back to where it came from and how much to trust it -- the
    "source attribution and confidence for memory entries" requirement.
    """

    content: str
    source: str
    confidence: float
    status: MemoryStatus = MemoryStatus.PENDING
    tags: tuple[str, ...] = field(default_factory=tuple)
    id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: datetime | None = None
    reviewer: str | None = None

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("MemoryEntry.content must not be empty")
        if not self.source or not self.source.strip():
            raise ValueError("MemoryEntry.source must not be empty")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            # A string would raise a raw TypeError on comparison; a bool is almost certainly a mistake.
            raise ValueError("MemoryEntry.confidence must be a number")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("MemoryEntry.confidence must be between 0.0 and 1.0")
        if isinstance(self.tags, str):
            # A bare string would be silently split into single-character tags.
            raise ValueError("MemoryEntry.tags must be a collection of strings, not a string")
        if not all(isinstance(t, str) and t.strip() for t in self.tags):
            raise ValueError("MemoryEntry.tags must contain only non-empty strings")
        self.tags = tuple(self.tags)
