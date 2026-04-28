"""Tests for core.layout.

We build a synthetic 3-verse canon and drive scroll_down / scroll_up, checking
that the cursor advances line-by-line, that chapter headers appear at chapter
boundaries, and that the canon-end / canon-start return None.
"""

import pytest

from ironrod.core.layout import LayoutLine, lay_out, scroll_down, scroll_up
from ironrod.models import Reference

# Tiny canon:
#   book 1 chapter 1: 2 verses
#   book 1 chapter 2: 1 verse
# Total 3 verses.

BOOK_ORDER = [1]

VERSES = {
    Reference(book_id=1, chapter_number=1, verse_number=1): "Alpha verse text.",
    Reference(book_id=1, chapter_number=1, verse_number=2):
        "Beta verse with a longer body that should wrap into multiple display lines.",
    Reference(book_id=1, chapter_number=2, verse_number=1): "Gamma verse.",
}

ORDERED = list(VERSES.keys())


def next_ref(r: Reference) -> Reference | None:
    i = ORDERED.index(r)
    return ORDERED[i + 1] if i + 1 < len(ORDERED) else None


def prev_ref(r: Reference) -> Reference | None:
    i = ORDERED.index(r)
    return ORDERED[i - 1] if i > 0 else None


def verse_text(r: Reference) -> str:
    return VERSES[r]


def book_title(book_id: int) -> str:
    return {1: "Foo"}[book_id]


WIDTH = 30  # narrow enough that the long verse wraps


def lines_for(r: Reference) -> int:
    from ironrod.core.layout import render_verse_lines
    return len(render_verse_lines(r, width=WIDTH, verse_text=verse_text))


# lay_out

def test_lay_out_yields_first_verse_only_when_short() -> None:
    out = lay_out(
        ORDERED[0], 0,
        lines_needed=1, width=WIDTH,
        next_ref=next_ref, verse_text=verse_text, book_title=book_title,
    )
    assert len(out) == 1
    assert out[0].kind == "verse"
    assert out[0].reference == ORDERED[0]


def test_lay_out_inserts_chapter_header_at_boundary() -> None:
    # Lay out enough lines to cross from chapter 1 (verses 1+2) into chapter 2.
    total_lines = lines_for(ORDERED[0]) + lines_for(ORDERED[1]) + 1 + 1
    # That + 1 (header) + 1 (first line of ch2 v1)
    out = lay_out(
        ORDERED[0], 0,
        lines_needed=total_lines, width=WIDTH,
        next_ref=next_ref, verse_text=verse_text, book_title=book_title,
    )
    headers = [line for line in out if line.kind == "header"]
    assert len(headers) == 1
    assert "Foo 2" in headers[0].content
    assert headers[0].reference == ORDERED[2]


def test_lay_out_with_top_line_offset_skips_first_lines() -> None:
    out = lay_out(
        ORDERED[1], 1,
        lines_needed=2, width=WIDTH,
        next_ref=next_ref, verse_text=verse_text, book_title=book_title,
    )
    full = lay_out(
        ORDERED[1], 0,
        lines_needed=lines_for(ORDERED[1]) + 5, width=WIDTH,
        next_ref=next_ref, verse_text=verse_text, book_title=book_title,
    )
    assert out[0] == full[1]


def test_lay_out_offset_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        lay_out(
            ORDERED[0], 99,
            lines_needed=1, width=WIDTH,
            next_ref=next_ref, verse_text=verse_text, book_title=book_title,
        )


# scroll_down / scroll_up

def test_scroll_down_within_verse() -> None:
    # Beta verse wraps into > 1 line; offset should advance.
    assert lines_for(ORDERED[1]) >= 2
    assert scroll_down(ORDERED[1], 0, width=WIDTH, next_ref=next_ref, verse_text=verse_text) == (ORDERED[1], 1)


def test_scroll_down_crosses_verse_boundary() -> None:
    # From last line of verse 1 → first line of verse 2.
    last_offset = lines_for(ORDERED[0]) - 1
    assert scroll_down(ORDERED[0], last_offset, width=WIDTH, next_ref=next_ref, verse_text=verse_text) == (ORDERED[1], 0)


def test_scroll_down_at_canon_end_returns_none() -> None:
    last_ref = ORDERED[-1]
    last_offset = lines_for(last_ref) - 1
    assert scroll_down(last_ref, last_offset, width=WIDTH, next_ref=next_ref, verse_text=verse_text) is None


def test_scroll_up_within_verse() -> None:
    assert scroll_up(ORDERED[1], 1, width=WIDTH, prev_ref=prev_ref, verse_text=verse_text) == (ORDERED[1], 0)


def test_scroll_up_crosses_verse_boundary() -> None:
    last_offset_prev = lines_for(ORDERED[0]) - 1
    assert scroll_up(ORDERED[1], 0, width=WIDTH, prev_ref=prev_ref, verse_text=verse_text) == (ORDERED[0], last_offset_prev)


def test_scroll_up_at_canon_start_returns_none() -> None:
    assert scroll_up(ORDERED[0], 0, width=WIDTH, prev_ref=prev_ref, verse_text=verse_text) is None


def test_scroll_down_then_up_round_trip() -> None:
    cur: tuple[Reference, int] = (ORDERED[0], 0)
    visited: list[tuple[Reference, int]] = [cur]
    for _ in range(20):
        nxt = scroll_down(cur[0], cur[1], width=WIDTH, next_ref=next_ref, verse_text=verse_text)
        if nxt is None:
            break
        visited.append(nxt)
        cur = nxt
    # Now walk backward and check we revisit the same cursors.
    for expected in reversed(visited[:-1]):
        prv = scroll_up(cur[0], cur[1], width=WIDTH, prev_ref=prev_ref, verse_text=verse_text)
        assert prv == expected
        cur = prv
    assert scroll_up(cur[0], cur[1], width=WIDTH, prev_ref=prev_ref, verse_text=verse_text) is None
