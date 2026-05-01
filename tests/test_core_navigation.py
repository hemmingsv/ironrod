"""Tests for core.navigation against a synthetic mini-canon.

The mini-canon has 3 books to exercise the chapter, book, and canon-end
boundaries without depending on the real SQLite DB.

  Book 1: 2 chapters; ch1 has 3 verses, ch2 has 2 verses.
  Book 2: 1 chapter;  ch1 has 1 verse.
  Book 3: 2 chapters; ch1 has 2 verses, ch2 has 1 verse.
"""

import pytest

from ironrod.core.navigation import (
    next_reference,
    prev_reference,
    verse_distance,
    verse_position,
    next_chapter_start,
    next_reference,
    prev_chapter_start,
    prev_reference,
)
from ironrod.models import Reference

BOOK_ORDER = [1, 2, 3]
CHAPTER_COUNT_BY_BOOK = {1: 2, 2: 1, 3: 2}
VERSE_COUNT_BY_CHAPTER = {
    (1, 1): 3, (1, 2): 2,
    (2, 1): 1,
    (3, 1): 2, (3, 2): 1,
}

KW = {
    "book_order": BOOK_ORDER,
    "chapter_count_by_book": CHAPTER_COUNT_BY_BOOK,
    "verse_count_by_chapter": VERSE_COUNT_BY_CHAPTER,
}


def ref(book: int, ch: int, v: int) -> Reference:
    return Reference(book_id=book, chapter_number=ch, verse_number=v)


# next_reference

def test_next_within_chapter() -> None:
    assert next_reference(ref(1, 1, 1), **KW) == ref(1, 1, 2)
    assert next_reference(ref(1, 1, 2), **KW) == ref(1, 1, 3)


def test_next_crosses_chapter_within_book() -> None:
    assert next_reference(ref(1, 1, 3), **KW) == ref(1, 2, 1)


def test_next_crosses_book() -> None:
    # last verse of book 1
    assert next_reference(ref(1, 2, 2), **KW) == ref(2, 1, 1)
    # last verse of book 2 (single-chapter, single-verse)
    assert next_reference(ref(2, 1, 1), **KW) == ref(3, 1, 1)


def test_next_at_canon_end_returns_none() -> None:
    assert next_reference(ref(3, 2, 1), **KW) is None


# prev_reference

def test_prev_within_chapter() -> None:
    assert prev_reference(ref(1, 1, 3), **KW) == ref(1, 1, 2)


def test_prev_crosses_chapter_within_book() -> None:
    assert prev_reference(ref(1, 2, 1), **KW) == ref(1, 1, 3)


def test_prev_crosses_book() -> None:
    assert prev_reference(ref(2, 1, 1), **KW) == ref(1, 2, 2)
    assert prev_reference(ref(3, 1, 1), **KW) == ref(2, 1, 1)


def test_prev_at_canon_start_returns_none() -> None:
    assert prev_reference(ref(1, 1, 1), **KW) is None


# round-trip identity

@pytest.mark.parametrize(
    "r",
    [
        ref(1, 1, 1), ref(1, 1, 2), ref(1, 2, 1),
        ref(2, 1, 1),
        ref(3, 1, 1), ref(3, 1, 2), ref(3, 2, 1),
    ],
)
def test_next_then_prev_returns_to_start(r: Reference) -> None:
    nxt = next_reference(r, **KW)
    if nxt is None:
        assert r == ref(3, 2, 1)
        return
    assert prev_reference(nxt, **KW) == r


@pytest.mark.parametrize(
    "r",
    [
        ref(1, 1, 1), ref(1, 1, 2), ref(1, 2, 1),
        ref(2, 1, 1),
        ref(3, 1, 1), ref(3, 1, 2), ref(3, 2, 1),
    ],
)
def test_prev_then_next_returns_to_start(r: Reference) -> None:
    prv = prev_reference(r, **KW)
    if prv is None:
        assert r == ref(1, 1, 1)
        return
    assert next_reference(prv, **KW) == r


# verse_position / verse_distance

def test_verse_position_starts_at_zero() -> None:
    assert verse_position(ref(1, 1, 1), **KW) == 0


def test_verse_position_within_chapter() -> None:
    assert verse_position(ref(1, 1, 3), **KW) == 2


def test_verse_position_crosses_chapters_and_books() -> None:
    # Book 1 has 3 + 2 = 5 verses, so book 2 v1 is at index 5.
    assert verse_position(ref(2, 1, 1), **KW) == 5
    # Book 1 (5) + book 2 (1) = 6, so book 3 ch2 v1 is at 6 + 2 = 8.
    assert verse_position(ref(3, 2, 1), **KW) == 8


def test_verse_position_matches_forward_walk() -> None:
    cur = ref(1, 1, 1)
    expected = 0
    while True:
        assert verse_position(cur, **KW) == expected
        nxt = next_reference(cur, **KW)
        if nxt is None:
            break
        cur, expected = nxt, expected + 1


def test_verse_distance_signed() -> None:
    a, b = ref(1, 1, 1), ref(1, 1, 3)
    assert verse_distance(a, b, **KW) == 2
    assert verse_distance(b, a, **KW) == -2
    assert verse_distance(a, a, **KW) == 0


def test_verse_distance_across_books() -> None:
    # Gen-style canon: from book 1 ch 1 v 1 to book 3 ch 2 v 1 is 8 steps.
    assert verse_distance(ref(1, 1, 1), ref(3, 2, 1), **KW) == 8

    
CHAPTER_KW = {
    "book_order": BOOK_ORDER,
    "chapter_count_by_book": CHAPTER_COUNT_BY_BOOK,
}


# next_chapter_start

def test_next_chapter_start_within_book() -> None:
    assert next_chapter_start(ref(1, 1, 1), **CHAPTER_KW) == ref(1, 2, 1)
    # Verse position within the chapter doesn't matter.
    assert next_chapter_start(ref(1, 1, 3), **CHAPTER_KW) == ref(1, 2, 1)


def test_next_chapter_start_crosses_book() -> None:
    # Last chapter of book 1 → ch1 of book 2.
    assert next_chapter_start(ref(1, 2, 1), **CHAPTER_KW) == ref(2, 1, 1)
    assert next_chapter_start(ref(1, 2, 2), **CHAPTER_KW) == ref(2, 1, 1)


def test_next_chapter_start_at_canon_end_returns_none() -> None:
    assert next_chapter_start(ref(3, 2, 1), **CHAPTER_KW) is None


# prev_chapter_start

def test_prev_chapter_start_within_book() -> None:
    assert prev_chapter_start(ref(1, 2, 1), **CHAPTER_KW) == ref(1, 1, 1)
    assert prev_chapter_start(ref(1, 2, 2), **CHAPTER_KW) == ref(1, 1, 1)


def test_prev_chapter_start_crosses_book() -> None:
    # First chapter of book 2 → last chapter of book 1, but at verse 1.
    assert prev_chapter_start(ref(2, 1, 1), **CHAPTER_KW) == ref(1, 2, 1)
    assert prev_chapter_start(ref(3, 1, 1), **CHAPTER_KW) == ref(2, 1, 1)


def test_prev_chapter_start_at_canon_start_returns_none() -> None:
    assert prev_chapter_start(ref(1, 1, 1), **CHAPTER_KW) is None
    assert prev_chapter_start(ref(1, 1, 3), **CHAPTER_KW) is None


def test_full_forward_walk_visits_every_verse() -> None:
    visited = [ref(1, 1, 1)]
    cur = visited[0]
    while True:
        nxt = next_reference(cur, **KW)
        if nxt is None:
            break
        visited.append(nxt)
        cur = nxt
    expected_count = sum(VERSE_COUNT_BY_CHAPTER.values())
    assert len(visited) == expected_count
