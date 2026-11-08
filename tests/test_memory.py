from __future__ import annotations

import pytest

from odysseus.exceptions import ReviewInboxError
from odysseus.memory.models import MemoryEntry, MemoryStatus
from odysseus.memory.store import MemoryStore


def test_memory_entry_validates_fields():
    with pytest.raises(ValueError):
        MemoryEntry(content="", source="user", confidence=0.5)
    with pytest.raises(ValueError):
        MemoryEntry(content="x", source="", confidence=0.5)
    with pytest.raises(ValueError):
        MemoryEntry(content="x", source="user", confidence=1.5)


def test_candidate_starts_pending(memory_store: MemoryStore):
    entry = MemoryEntry(content="The sky is blue", source="user", confidence=0.9)
    stored = memory_store.submit_candidate(entry)
    assert stored.status == MemoryStatus.PENDING
    assert stored.id is not None
    # Pending entries must not be queryable as approved memory.
    assert memory_store.query("sky") == []
    assert memory_store.list_pending() == [stored]


def test_approve_promotes_to_queryable(memory_store: MemoryStore):
    entry = MemoryEntry(content="The sky is blue", source="user", confidence=0.9)
    stored = memory_store.submit_candidate(entry)
    approved = memory_store.approve(stored.id, reviewer="alice")
    assert approved.status == MemoryStatus.APPROVED
    assert approved.reviewer == "alice"
    results = memory_store.query("sky")
    assert len(results) == 1
    assert results[0].content == "The sky is blue"


def test_reject_keeps_entry_out_of_queries(memory_store: MemoryStore):
    entry = MemoryEntry(content="The moon is cheese", source="user", confidence=0.1)
    stored = memory_store.submit_candidate(entry)
    rejected = memory_store.reject(stored.id, reviewer="bob")
    assert rejected.status == MemoryStatus.REJECTED
    assert memory_store.query("moon") == []
    assert memory_store.list_pending() == []


def test_cannot_review_twice(memory_store: MemoryStore):
    entry = MemoryEntry(content="fact", source="user", confidence=0.5)
    stored = memory_store.submit_candidate(entry)
    memory_store.approve(stored.id, reviewer="alice")
    with pytest.raises(ReviewInboxError):
        memory_store.approve(stored.id, reviewer="bob")


def test_review_unknown_id_raises(memory_store: MemoryStore):
    with pytest.raises(ReviewInboxError):
        memory_store.approve(9999, reviewer="alice")


def test_auto_approve_threshold(tmp_path):
    store = MemoryStore(tmp_path / "mem.sqlite3", auto_approve_threshold=0.8)
    high = store.submit_candidate(
        MemoryEntry(content="high confidence fact", source="sensor", confidence=0.95)
    )
    low = store.submit_candidate(
        MemoryEntry(content="low confidence fact", source="sensor", confidence=0.3)
    )
    assert high.status == MemoryStatus.APPROVED
    assert high.reviewer == "auto-approval-rule"
    assert low.status == MemoryStatus.PENDING


def test_tags_round_trip(memory_store: MemoryStore):
    entry = MemoryEntry(content="x", source="user", confidence=0.5, tags=("a", "b"))
    stored = memory_store.submit_candidate(entry)
    fetched = memory_store.get(stored.id)
    assert fetched.tags == ("a", "b")


def test_count_by_status(memory_store: MemoryStore):
    memory_store.submit_candidate(MemoryEntry(content="x", source="s", confidence=0.5))
    memory_store.submit_candidate(MemoryEntry(content="y", source="s", confidence=0.5))
    counts = memory_store.count_by_status()
    assert counts == {"pending": 2}


def test_store_persists_across_instances(tmp_path):
    db_path = tmp_path / "mem.sqlite3"
    store1 = MemoryStore(db_path)
    stored = store1.submit_candidate(MemoryEntry(content="x", source="s", confidence=0.5))
    store2 = MemoryStore(db_path)
    assert store2.get(stored.id) is not None


def test_query_treats_like_wildcards_literally(memory_store: MemoryStore):
    for text in ("Battery is at 100% charge", "snake_case naming", "snakeXcase naming", "100 percent sure"):
        stored = memory_store.submit_candidate(
            MemoryEntry(content=text, source="user", confidence=0.9)
        )
        memory_store.approve(stored.id, reviewer="tester")
    assert [e.content for e in memory_store.query("100%")] == ["Battery is at 100% charge"]
    assert [e.content for e in memory_store.query("snake_case")] == ["snake_case naming"]
    # '_' must not act as a single-char wildcard (would also match snakeXcase).
    # '%' must not act as a wildcard (would also match "100 percent sure").
