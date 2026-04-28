"""Contract tests for the bookmark journal.

The same suite runs against the real (disk-backed) ``BookmarkJournal`` and the
``InMemoryBookmarkJournal`` test double. If both implementations pass every
test, flow tests are safe to inject the in-memory one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ironrod.clients.bookmarks import (
    BookmarkExists,
    BookmarkJournal,
    BookmarkNotFound,
    CannotDeleteLast,
)
from ironrod.clients.testing.bookmarks_inmemory import InMemoryBookmarkJournal
from ironrod.models import Reference

GEN_1_1 = Reference(book_id=1, chapter_number=1, verse_number=1)
GEN_1_2 = Reference(book_id=1, chapter_number=1, verse_number=2)


JournalFactory = Callable[[Path], Any]


def _real(tmp_path: Path) -> BookmarkJournal:
    return BookmarkJournal(path=tmp_path / "bookmarks.jsonl")


def _inmemory(tmp_path: Path) -> InMemoryBookmarkJournal:  # noqa: ARG001
    return InMemoryBookmarkJournal()


@pytest.fixture(params=[_real, _inmemory], ids=["real", "inmemory"])
def journal(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    factory: JournalFactory = request.param
    return factory(tmp_path)


def test_load_starts_empty(journal: Any) -> None:
    assert journal.load() == []
    assert journal.top() is None


def test_create_adds_to_top(journal: Any) -> None:
    bm = journal.create("My Study", GEN_1_1)
    assert bm.slug == "my-study"
    assert bm.reference == GEN_1_1
    assert journal.top() == bm


def test_create_two_keeps_newest_first(journal: Any) -> None:
    journal.create("First", GEN_1_1)
    second = journal.create("Second", GEN_1_1)
    bookmarks = journal.load()
    assert [b.slug for b in bookmarks] == ["second", "first"]
    assert journal.top() == second


def test_get_returns_correct_bookmark(journal: Any) -> None:
    journal.create("Alpha", GEN_1_1)
    journal.create("Beta", GEN_1_2)
    alpha = journal.get("alpha")
    assert alpha.slug == "alpha"
    assert alpha.reference == GEN_1_1


def test_get_unknown_raises(journal: Any) -> None:
    with pytest.raises(BookmarkNotFound):
        journal.get("nope")


def test_create_duplicate_raises(journal: Any) -> None:
    journal.create("My Study", GEN_1_1)
    with pytest.raises(BookmarkExists):
        journal.create("My Study", GEN_1_2)
    with pytest.raises(BookmarkExists):
        # Same slug, different display name.
        journal.create("my study", GEN_1_2)


def test_touch_moves_to_top_and_updates_reference(journal: Any) -> None:
    journal.create("Alpha", GEN_1_1)
    journal.create("Beta", GEN_1_1)
    journal.create("Gamma", GEN_1_1)
    # Right now order is gamma, beta, alpha.
    updated = journal.touch("alpha", GEN_1_2)
    assert updated.reference == GEN_1_2
    assert updated.updated_at >= updated.created_at
    assert [b.slug for b in journal.load()] == ["alpha", "gamma", "beta"]


def test_touch_without_reference_keeps_old_reference(journal: Any) -> None:
    journal.create("Alpha", GEN_1_2)
    journal.create("Beta", GEN_1_1)
    updated = journal.touch("alpha")
    assert updated.reference == GEN_1_2
    assert journal.load()[0].slug == "alpha"


def test_touch_unknown_raises(journal: Any) -> None:
    journal.create("Alpha", GEN_1_1)
    with pytest.raises(BookmarkNotFound):
        journal.touch("nope", GEN_1_2)


def test_delete_removes_bookmark(journal: Any) -> None:
    journal.create("Alpha", GEN_1_1)
    journal.create("Beta", GEN_1_1)
    journal.delete("alpha")
    assert [b.slug for b in journal.load()] == ["beta"]


def test_delete_last_raises(journal: Any) -> None:
    journal.create("Only", GEN_1_1)
    with pytest.raises(CannotDeleteLast):
        journal.delete("only")


def test_delete_unknown_with_others_present_raises(journal: Any) -> None:
    journal.create("Alpha", GEN_1_1)
    journal.create("Beta", GEN_1_1)
    with pytest.raises(BookmarkNotFound):
        journal.delete("nope")
