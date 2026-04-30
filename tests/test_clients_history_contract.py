"""Contract tests for the history journal.

The same suite runs against the real (disk-backed) ``HistoryJournal`` and the
``InMemoryHistoryJournal`` test double. If both implementations pass every
test, flow tests are safe to inject the in-memory one.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ironrod.clients.history import HistoryJournal
from ironrod.clients.testing.history_inmemory import InMemoryHistoryJournal
from ironrod.models import Reference

GEN_1_1 = Reference(book_id=1, chapter_number=1, verse_number=1)
GEN_1_2 = Reference(book_id=1, chapter_number=1, verse_number=2)
GEN_2_1 = Reference(book_id=1, chapter_number=2, verse_number=1)


JournalFactory = Callable[[Path], Any]


def _real(tmp_path: Path) -> HistoryJournal:
    return HistoryJournal(path=tmp_path / "history.jsonl")


def _inmemory(tmp_path: Path) -> InMemoryHistoryJournal:  # noqa: ARG001
    return InMemoryHistoryJournal()


@pytest.fixture(params=[_real, _inmemory], ids=["real", "inmemory"])
def journal(request: pytest.FixtureRequest, tmp_path: Path) -> Any:
    factory: JournalFactory = request.param
    return factory(tmp_path)


def test_load_starts_empty(journal: Any) -> None:
    assert journal.load() == []
    assert journal.load_for("anything") == []


def test_append_returns_true_on_new_record(journal: Any) -> None:
    assert journal.append("my-study", GEN_1_1) is True
    records = journal.load_for("my-study")
    assert len(records) == 1
    assert records[0].slug == "my-study"
    assert records[0].reference == GEN_1_1


def test_append_dedups_against_last_record(journal: Any) -> None:
    assert journal.append("my-study", GEN_1_1) is True
    assert journal.append("my-study", GEN_1_1) is False
    assert len(journal.load_for("my-study")) == 1


def test_append_does_not_dedup_after_intervening_record(journal: Any) -> None:
    journal.append("my-study", GEN_1_1)
    journal.append("my-study", GEN_1_2)
    assert journal.append("my-study", GEN_1_1) is True
    refs = [r.reference for r in journal.load_for("my-study")]
    assert refs == [GEN_1_1, GEN_1_2, GEN_1_1]


def test_dedup_is_per_slug_only(journal: Any) -> None:
    journal.append("daily", GEN_1_1)
    # Same reference, different slug, must NOT dedup.
    assert journal.append("evening", GEN_1_1) is True
    assert len(journal.load_for("daily")) == 1
    assert len(journal.load_for("evening")) == 1


def test_load_returns_records_in_file_order(journal: Any) -> None:
    journal.append("daily", GEN_1_1)
    journal.append("evening", GEN_2_1)
    journal.append("daily", GEN_1_2)
    refs = [r.reference for r in journal.load_for("daily")]
    assert refs == [GEN_1_1, GEN_1_2]


def test_load_for_unknown_slug_is_empty(journal: Any) -> None:
    journal.append("daily", GEN_1_1)
    assert journal.load_for("nope") == []
