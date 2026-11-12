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


def test_blank_query_or_nonpositive_limit_returns_nothing(memory_store: MemoryStore):
    for text in ("Likes tea", "Likes coffee"):
        stored = memory_store.submit_candidate(
            MemoryEntry(content=text, source="user", confidence=0.9)
        )
        memory_store.approve(stored.id, reviewer="tester")
    assert memory_store.query("") == []
    assert memory_store.query("   ") == []
    assert memory_store.query("Likes", limit=0) == []
    assert memory_store.query("Likes", limit=-1) == []
    assert len(memory_store.query("Likes", limit=1)) == 1


def test_retract_removes_approved_entry_from_query(memory_store: MemoryStore):
    stored = memory_store.submit_candidate(
        MemoryEntry(content="Prefers tea", source="user", confidence=0.9)
    )
    # Pending entries cannot be retracted (nothing to withdraw yet).
    with pytest.raises(ReviewInboxError):
        memory_store.retract(stored.id, reviewer="me")
    memory_store.approve(stored.id, reviewer="me")
    assert memory_store.query("tea")

    retracted = memory_store.retract(stored.id, reviewer="me")
    assert retracted.status == MemoryStatus.REJECTED
    assert memory_store.query("tea") == []
    # Row is kept for provenance, and cannot be retracted twice.
    assert memory_store.get(stored.id) is not None
    with pytest.raises(ReviewInboxError):
        memory_store.retract(stored.id, reviewer="me")


def test_duplicate_candidate_is_not_stored_twice(memory_store: MemoryStore):
    first = memory_store.submit_candidate(
        MemoryEntry(content="Prefers tea", source="user", confidence=0.9)
    )
    again = memory_store.submit_candidate(
        MemoryEntry(content="  prefers   TEA ", source="chat", confidence=0.5)
    )
    assert again.id == first.id
    assert len(memory_store.list_pending()) == 1

    # Also deduplicated against approved memory.
    memory_store.approve(first.id, reviewer="me")
    assert memory_store.submit_candidate(
        MemoryEntry(content="Prefers tea", source="chat", confidence=0.5)
    ).id == first.id
    assert memory_store.count_by_status() == {"approved": 1}

    # A rejected entry may be proposed again.
    memory_store.retract(first.id, reviewer="me")
    redo = memory_store.submit_candidate(
        MemoryEntry(content="Prefers tea", source="user", confidence=0.9)
    )
    assert redo.id != first.id


def test_review_does_not_overwrite_concurrent_decision(memory_store: MemoryStore, monkeypatch):
    stored = memory_store.submit_candidate(
        MemoryEntry(content="Race fact", source="user", confidence=0.5)
    )
    stale = memory_store.get(stored.id)  # still PENDING
    memory_store.approve(stored.id, "alice")  # another reviewer wins the race
    monkeypatch.setattr(memory_store, "get", lambda _id: stale)
    with pytest.raises(ReviewInboxError):
        memory_store.reject(stored.id, "bob")
    monkeypatch.undo()
    final = memory_store.get(stored.id)
    assert final.status == MemoryStatus.APPROVED
    assert final.reviewer == "alice"


def test_query_is_case_insensitive_for_non_ascii(memory_store: MemoryStore):
    stored = memory_store.submit_candidate(
        MemoryEntry(content="Der Ärger über Straße", source="user", confidence=0.9)
    )
    memory_store.approve(stored.id, reviewer="me")
    assert [m.id for m in memory_store.query("ärger")] == [stored.id]
    assert [m.id for m in memory_store.query("STRASSE")] == [stored.id]


def test_query_ignores_punctuation_around_words(tmp_path):
    store = MemoryStore(tmp_path / "m.db")
    e = store.submit_candidate(MemoryEntry(content="Sam likes pizza", source="user", confidence=0.9))
    store.approve(e.id, reviewer="t")
    assert [m.id for m in store.query("pizza?")] == [e.id]


def test_corrupt_row_raises_typed_memory_error(tmp_path):
    import sqlite3

    from odysseus.exceptions import MemoryError_

    store = MemoryStore(tmp_path / "m.db")
    e = store.submit_candidate(MemoryEntry(content="likes tea", source="user", confidence=0.9))
    store.approve(e.id, reviewer="me")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE memory_entries SET tags = 'not json' WHERE id = ?", (e.id,))
    with pytest.raises(MemoryError_):
        store.query("tea")


def test_review_requires_non_blank_reviewer(memory_store: MemoryStore):
    stored = memory_store.submit_candidate(
        MemoryEntry(content="Needs a named reviewer", source="user", confidence=0.5)
    )
    for blank in ("", "   "):
        with pytest.raises(ReviewInboxError):
            memory_store.approve(stored.id, reviewer=blank)
        with pytest.raises(ReviewInboxError):
            memory_store.reject(stored.id, reviewer=blank)
    assert memory_store.get(stored.id).status == MemoryStatus.PENDING


def test_review_records_trimmed_reviewer(memory_store: MemoryStore):
    stored = memory_store.submit_candidate(
        MemoryEntry(content="Reviewer name is trimmed", source="user", confidence=0.5)
    )
    approved = memory_store.approve(stored.id, reviewer="  sam \n")
    assert approved.reviewer == "sam"


def test_memory_entry_rejects_non_numeric_confidence():
    for bad in ("0.5", None, True):
        with pytest.raises(ValueError, match="confidence"):
            MemoryEntry(content="x", source="s", confidence=bad)


def test_memory_entry_rejects_non_string_content_and_source():
    for bad in (None, 5, b"x"):
        with pytest.raises(ValueError, match="must be strings"):
            MemoryEntry(content=bad, source="s", confidence=0.5)
        with pytest.raises(ValueError, match="must be strings"):
            MemoryEntry(content="x", source=bad, confidence=0.5)


def test_memory_entry_rejects_bad_tags():
    with pytest.raises(ValueError):
        MemoryEntry(content="x", source="s", confidence=0.5, tags="food")
    with pytest.raises(ValueError):
        MemoryEntry(content="x", source="s", confidence=0.5, tags=("ok", " "))
    with pytest.raises(ValueError):
        MemoryEntry(content="x", source="s", confidence=0.5, tags=("ok", 3))
    entry = MemoryEntry(content="x", source="s", confidence=0.5, tags=["a", "b"])
    assert entry.tags == ("a", "b")


def test_query_with_very_long_text_does_not_crash(memory_store: MemoryStore):
    stored = memory_store.submit_candidate(
        MemoryEntry(content="likes pizza", source="user", confidence=0.9)
    )
    memory_store.approve(stored.id, reviewer="alice")
    long_text = "pizza " + " ".join(f"word{i}" for i in range(5000))
    assert [e.content for e in memory_store.query(long_text)] == ["likes pizza"]


def test_store_rejects_out_of_range_auto_approve_threshold(tmp_path):
    for bad in (-0.1, 1.5, True, "0.5"):
        with pytest.raises(ValueError):
            MemoryStore(tmp_path / "mem.sqlite3", auto_approve_threshold=bad)


def test_query_rejects_wrong_argument_types(memory_store: MemoryStore):
    with pytest.raises(TypeError, match="query text must be a string"):
        memory_store.query(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="query limit must be an int"):
        memory_store.query("pizza", limit="5")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="query limit must be an int"):
        memory_store.query("pizza", limit=True)


def test_review_rejects_non_string_reviewer(memory_store: MemoryStore):
    stored = memory_store.submit_candidate(MemoryEntry(content="reviewer type", source="t", confidence=0.5))
    for bad in (123, b"bob", ["bob"]):
        with pytest.raises(ReviewInboxError):
            memory_store.approve(stored.id, reviewer=bad)
    assert memory_store.get(stored.id).status == MemoryStatus.PENDING


def test_submit_candidate_rejects_non_memory_entry(memory_store: MemoryStore):
    with pytest.raises(TypeError, match="expects a MemoryEntry"):
        memory_store.submit_candidate(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="expects a MemoryEntry"):
        memory_store.submit_candidate("likes pizza")  # type: ignore[arg-type]


def test_read_paths_raise_typed_error_on_corrupt_database(memory_store: MemoryStore):
    from odysseus.exceptions import MemoryError_

    memory_store.db_path.write_bytes(b"this is not a sqlite database" * 100)
    with pytest.raises(MemoryError_):
        memory_store.query("anything")
    with pytest.raises(MemoryError_):
        memory_store.get(1)
    with pytest.raises(MemoryError_):
        memory_store.list_pending()
    with pytest.raises(MemoryError_):
        memory_store.count_by_status()


def test_query_ranks_entries_matching_more_terms_first(memory_store: MemoryStore):
    # A high-confidence entry sharing only a common word must not crowd the
    # relevant, lower-confidence entry out of a small limit.
    def approved(content: str, confidence: float) -> MemoryEntry:
        entry = memory_store.submit_candidate(
            MemoryEntry(content=content, source="user", confidence=confidence)
        )
        return memory_store.approve(entry.id, reviewer="tester")

    for i in range(3):
        approved(f"Remember the capital letters rule {i}", 0.95)
    relevant = approved("The capital of France is Paris", 0.4)

    results = memory_store.query("What is the capital of France?", limit=3)

    assert results[0].id == relevant.id
    # Ties on relevance still fall back to confidence ordering.
    assert [e.confidence for e in results[1:]] == [0.95, 0.95]


def test_store_raises_typed_error_when_db_directory_cannot_be_created(tmp_path):
    """A file where the DB's directory should be is a MemoryError_, not a raw OSError."""
    from odysseus.exceptions import MemoryError_

    blocker = tmp_path / "data"
    blocker.write_text("not a directory")
    with pytest.raises(MemoryError_, match="Could not create memory database directory"):
        MemoryStore(blocker / "sub" / "memory.sqlite3")


def test_list_rejected_shows_rejected_and_retracted_with_reviewer(memory_store: MemoryStore):
    assert memory_store.list_rejected() == []
    refused = memory_store.submit_candidate(MemoryEntry("wrong fact", "guess", 0.2))
    withdrawn = memory_store.submit_candidate(MemoryEntry("stale fact", "note", 0.9))
    kept = memory_store.submit_candidate(MemoryEntry("good fact", "note", 0.9))
    memory_store.reject(refused.id, reviewer="alice")
    memory_store.approve(withdrawn.id, reviewer="alice")
    memory_store.retract(withdrawn.id, reviewer="bob")
    memory_store.approve(kept.id, reviewer="alice")

    rejected = memory_store.list_rejected()
    assert [(e.id, e.reviewer) for e in rejected] == [
        (refused.id, "alice"),
        (withdrawn.id, "bob"),
    ]
    assert all(e.status == MemoryStatus.REJECTED and e.reviewed_at for e in rejected)


def test_query_ignores_stop_words_as_search_terms(memory_store: MemoryStore):
    # "what"/"the" in a question must not pull in unrelated memories that
    # merely contain those words (they would be injected into the prompt).
    def approved(content: str) -> MemoryEntry:
        entry = memory_store.submit_candidate(
            MemoryEntry(content=content, source="user", confidence=0.9)
        )
        return memory_store.approve(entry.id, reviewer="tester")

    unrelated = approved("Remember the umbrella, whatever the weather")
    relevant = approved("The capital of France is Paris")

    results = memory_store.query("What is THE capital of France?")
    assert [e.id for e in results] == [relevant.id]
    # A question made only of stop words/short words matches nothing by term.
    assert memory_store.query("What is this about?") == []
    # The whole text is still matched, so an explicit stop-word search or a
    # phrase containing one keeps working.
    assert unrelated.id in [e.id for e in memory_store.query("the")]
    assert [e.id for e in memory_store.query("the umbrella")] == [unrelated.id]


def test_query_matches_tags_as_well_as_content(memory_store: MemoryStore):
    """A tag is a search term: an entry filed under "allergy" is retrieved by
    that word even though its content never says it (F009 retrieval)."""

    def approved(content, tags=(), confidence=0.5):
        e = memory_store.submit_candidate(
            MemoryEntry(content=content, source="user", confidence=confidence, tags=tags)
        )
        return memory_store.approve(e.id, reviewer="sam")

    tagged = approved("Peanuts must be avoided", tags=("Allergy", "caf\u00e9"))
    both = approved("Shellfish allergy noted in 2020", tags=("allergy",), confidence=0.1)
    approved("Unrelated note about trains", tags=("travel",))
    pending = memory_store.submit_candidate(
        MemoryEntry(content="Pending fact", source="user", confidence=0.9, tags=("allergy",))
    )

    # Tag-only match, case-insensitive; pending entries stay invisible.
    found = memory_store.query("any allergy?")
    assert {e.id for e in found} == {tagged.id, both.id}
    assert pending.id not in {e.id for e in found}
    # Non-ASCII tags match as typed (not as their JSON escape), folded.
    assert [e.id for e in memory_store.query("CAF\u00c9")] == [tagged.id]
    # A term found in both content and tag still counts once: ranking by
    # distinct matched terms is unchanged, so "peanuts allergy" puts the
    # entry matching both terms ahead of the one matching only "allergy".
    assert [e.id for e in memory_store.query("peanuts allergy")] == [tagged.id, both.id]
    # The JSON punctuation of the stored tags is not searchable.
    assert memory_store.query('", "') == []
    assert memory_store.query("zzz") == []


def test_query_survives_unreadable_tags_on_a_non_matching_row(memory_store: MemoryStore):
    """A row whose stored tags are not valid JSON must not break searches that
    do not return it; matching it by content still reports the corrupt row."""
    import sqlite3

    from odysseus.exceptions import MemoryError_

    good = memory_store.submit_candidate(
        MemoryEntry(content="Likes pizza", source="user", confidence=0.5, tags=("food",))
    )
    bad = memory_store.submit_candidate(
        MemoryEntry(content="Owns a bicycle", source="user", confidence=0.5)
    )
    memory_store.approve(good.id, reviewer="sam")
    memory_store.approve(bad.id, reviewer="sam")
    with sqlite3.connect(memory_store.db_path) as conn:
        conn.execute("UPDATE memory_entries SET tags = 'not json' WHERE id = ?", (bad.id,))
    assert [e.id for e in memory_store.query("food")] == [good.id]
    with pytest.raises(MemoryError_):
        memory_store.query("bicycle")


@pytest.mark.parametrize(
    "stored_tags",
    ['"work"', '{"work": 1}', "7", "null", "true"],
    ids=["string", "object", "number", "null", "bool"],
)
def test_tags_column_that_is_not_a_json_list_is_a_corrupt_row(memory_store: MemoryStore, stored_tags):
    """Valid JSON that is not a list must not be coerced into tags: a JSON
    string used to come back as one tag per character, an object as its keys."""
    import sqlite3
    from contextlib import closing

    from odysseus.exceptions import MemoryError_

    good = memory_store.submit_candidate(
        MemoryEntry(content="Prefers tea", source="user", confidence=0.9, tags=("drink",))
    )
    bad = memory_store.submit_candidate(
        MemoryEntry(content="Standup at nine", source="user", confidence=0.9)
    )
    with closing(sqlite3.connect(memory_store.db_path)) as conn:
        conn.execute("UPDATE memory_entries SET tags = ? WHERE id = ?", (stored_tags, bad.id))
        conn.commit()

    with pytest.raises(MemoryError_, match=f"Corrupt memory row id={bad.id}"):
        memory_store.get(bad.id)
    assert memory_store.unreadable_entry_ids() == [bad.id]
    # A stored JSON list still decodes as before.
    assert memory_store.get(good.id).tags == ("drink",)


def test_find_duplicate_reports_what_submit_candidate_would_keep(memory_store: MemoryStore):
    assert memory_store.find_duplicate("Sam likes pizza") is None
    first = memory_store.submit_candidate(
        MemoryEntry(content="Sam likes pizza", source="note", confidence=0.5)
    )
    found = memory_store.find_duplicate("  sam LIKES   pizza ")
    assert found is not None and found.id == first.id
    assert memory_store.find_duplicate("Sam likes pasta") is None
    assert memory_store.find_duplicate("   ") is None
    # Read-only: looking does not store anything.
    assert memory_store.count_by_status() == {"pending": 1}
    # A rejected entry does not count, so the fact can be proposed again.
    memory_store.reject(first.id, reviewer="t")
    assert memory_store.find_duplicate("Sam likes pizza") is None
    with pytest.raises(TypeError):
        memory_store.find_duplicate(None)


def test_ids_and_limits_beyond_sqlite_integer_range_do_not_raise_overflow(memory_store):
    """F009: SQLite integers are 64-bit; a larger id or limit must not escape
    the store as a raw OverflowError (it is not a sqlite3.Error)."""
    entry = memory_store.submit_candidate(
        MemoryEntry(content="Sam likes pizza", source="user", confidence=0.8)
    )
    memory_store.approve(entry.id, "sam")

    for too_big in (2**63, 10**30, -(2**63) - 1):
        assert memory_store.get(too_big) is None
        with pytest.raises(ReviewInboxError, match="No memory entry"):
            memory_store.approve(too_big, "sam")
        with pytest.raises(ReviewInboxError, match="No memory entry"):
            memory_store.retract(too_big, "sam")

    assert [e.id for e in memory_store.query("pizza", limit=10**30)] == [entry.id]
    # The largest id SQLite can hold is still looked up normally.
    assert memory_store.get(2**63 - 1) is None


def test_same_fact_submitted_concurrently_is_stored_once(tmp_path):
    """Two submitters that both pass the duplicate check before either has
    inserted must still end up with one entry (F009): the check and the
    insert are one write transaction."""
    import threading

    db = tmp_path / "memory.db"
    first = MemoryStore(db)
    second = MemoryStore(db)
    results: dict[str, MemoryEntry] = {}
    errors: list[BaseException] = []

    def submit_second():
        try:
            results["second"] = second.submit_candidate(
                MemoryEntry(content="sam  LIKES pizza", source="other", confidence=0.4)
            )
        except BaseException as exc:  # reported by the assertion below
            errors.append(exc)

    other = threading.Thread(target=submit_second)
    original = first._find_live_duplicate

    def check_then_let_the_other_submitter_run(*args, **kwargs):
        found = original(*args, **kwargs)
        # The first submitter has looked and found nothing. Give the second
        # one time to do its whole submission before the first inserts.
        other.start()
        other.join(timeout=1.0)
        return found

    first._find_live_duplicate = check_then_let_the_other_submitter_run
    results["first"] = first.submit_candidate(
        MemoryEntry(content="Sam likes pizza", source="user", confidence=0.8)
    )
    other.join(timeout=10.0)

    assert not other.is_alive()
    assert errors == []
    assert first.count_by_status() == {"pending": 1}
    assert results["first"].id == results["second"].id
    # Whoever got the write lock first is the one whose provenance is kept.
    assert results["second"].source == "user"


def test_raw_row_returns_stored_values_of_a_row_get_refuses(memory_store: MemoryStore):
    """F009: the stored text of a corrupt row stays readable (read-only, undecoded)."""
    import sqlite3

    entry = memory_store.submit_candidate(
        MemoryEntry(content="the gate code is 4471", source="user", confidence=0.9, tags=("home",))
    )
    conn = sqlite3.connect(memory_store.db_path)
    conn.execute("UPDATE memory_entries SET status = 'archived' WHERE id = ?", (entry.id,))
    conn.commit()
    conn.close()
    with pytest.raises(Exception, match="Corrupt memory row"):
        memory_store.get(entry.id)

    raw = memory_store.raw_row(entry.id)

    assert raw["id"] == entry.id
    assert raw["content"] == "the gate code is 4471"
    assert raw["status"] == "archived"
    assert raw["tags"] == '["home"]'
    assert raw["reviewed_at"] is None
    assert memory_store.unreadable_entry_ids() == [entry.id]  # nothing was repaired


def test_raw_row_unknown_or_out_of_range_id_is_none(memory_store: MemoryStore):
    assert memory_store.raw_row(12345) is None
    assert memory_store.raw_row(2**70) is None


def _approved(store: MemoryStore, content: str, confidence: float = 0.5, tags=()) -> MemoryEntry:
    stored = store.submit_candidate(
        MemoryEntry(content=content, source="user", confidence=confidence, tags=tags)
    )
    return store.approve(stored.id, "sam")


def test_search_terms_are_the_whole_text_then_its_significant_words(memory_store: MemoryStore):
    """F009: the terms retrieval searches for can be read, not only inferred."""
    assert memory_store.search_terms("What pizza, with OLIVES and pizza?") == (
        "What pizza, with OLIVES and pizza?",
        "pizza",
        "OLIVES",
    )
    # A one-word query is one term, not the word twice.
    assert memory_store.search_terms("pizza") == ("pizza",)
    assert memory_store.search_terms("pizza?") == ("pizza?", "pizza")
    # A blank text retrieves nothing, so it has no terms.
    assert memory_store.search_terms("   ") == ()
    with pytest.raises(TypeError):
        memory_store.search_terms(None)


def test_matched_terms_account_for_the_order_query_returns(memory_store: MemoryStore):
    """F009: an entry's rank is explained by how many search terms it contains."""
    one = _approved(memory_store, "Sam likes pizza", confidence=0.9)
    two = _approved(memory_store, "Pizza with Ölives on Friday", confidence=0.2)
    tagged = _approved(memory_store, "Tom is a cat", confidence=0.5, tags=("ÖLIVES",))
    text = "pizza ölives?"

    results = memory_store.query(text)
    # Two terms beat one; confidence orders the two single-term entries.
    assert [e.id for e in results] == [two.id, one.id, tagged.id]
    counts = [len(memory_store.matched_terms(text, e)) for e in results]
    # Every returned entry matched something, and more matches never rank lower.
    assert all(counts) and counts == sorted(counts, reverse=True)

    # Case-insensitive (non-ASCII too), in query order, tags included.
    assert memory_store.matched_terms(text, two) == ("pizza", "ölives")
    assert memory_store.matched_terms(text, tagged) == ("ölives",)
    assert memory_store.matched_terms("Sam likes pizza", one) == (
        "Sam likes pizza",
        "Sam",
        "likes",
        "pizza",
    )
    # Nothing in common, a blank text, and a phrase that would only match
    # across the content/tag boundary all explain as "no terms".
    assert memory_store.matched_terms("umbrella", one) == ()
    assert memory_store.matched_terms("  ", one) == ()
    assert memory_store.matched_terms("cat ÖLIVES", tagged) == ("cat", "ÖLIVES")
    with pytest.raises(TypeError):
        memory_store.matched_terms("pizza", "Sam likes pizza")


def test_matched_terms_agree_with_query_on_what_matches(memory_store: MemoryStore):
    """F009: the explanation and retrieval share one rule -- an approved
    entry is returned by ``query`` exactly when it has a matched term."""
    entries = [
        _approved(memory_store, "100% cotton shirts"),
        _approved(memory_store, "snake_case is preferred"),
        _approved(memory_store, "The umbrella is in the hall"),
        _approved(memory_store, "category theory notes", tags=("maths",)),
    ]
    for text in ("100%", "snake_case", "the", "the umbrella", "cat maths", "what is it", "x_y"):
        returned = {e.id for e in memory_store.query(text)}
        explained = {e.id for e in entries if memory_store.matched_terms(text, e)}
        assert returned == explained, text
