"""Verse-level navigation across the canon.

These functions take dependency-injected indexes so they're callable from the
DB client and unit-testable without sqlite. The canon is modelled as:

* ``book_order``: list of book ids, in canonical reading order.
* ``chapter_count_by_book``: mapping of book id → number of chapters.
* ``verse_count_by_chapter``: mapping of (book id, chapter number) → number of
  verses.
"""

from collections.abc import Mapping, Sequence

from ironrod.models import Reference

ChapterCount = Mapping[int, int]                    # book_id -> chapter count
VerseCount = Mapping[tuple[int, int], int]          # (book_id, chapter) -> verse count


def next_reference(
    ref: Reference,
    *,
    book_order: Sequence[int],
    chapter_count_by_book: ChapterCount,
    verse_count_by_chapter: VerseCount,
) -> Reference | None:
    """Return the verse immediately after ``ref`` in canon order.

    Returns ``None`` at the very last verse of the canon.
    """
    last_in_chapter = verse_count_by_chapter[(ref.book_id, ref.chapter_number)]
    if ref.verse_number < last_in_chapter:
        return Reference(
            book_id=ref.book_id,
            chapter_number=ref.chapter_number,
            verse_number=ref.verse_number + 1,
        )

    last_chapter = chapter_count_by_book[ref.book_id]
    if ref.chapter_number < last_chapter:
        return Reference(
            book_id=ref.book_id,
            chapter_number=ref.chapter_number + 1,
            verse_number=1,
        )

    book_index = book_order.index(ref.book_id)
    if book_index + 1 < len(book_order):
        next_book = book_order[book_index + 1]
        return Reference(book_id=next_book, chapter_number=1, verse_number=1)

    return None


def verse_position(
    ref: Reference,
    *,
    book_order: Sequence[int],
    chapter_count_by_book: ChapterCount,
    verse_count_by_chapter: VerseCount,
) -> int:
    """Return ``ref``'s zero-based absolute index in canon order."""
    pos = 0
    for book_id in book_order:
        if book_id == ref.book_id:
            break
        for ch in range(1, chapter_count_by_book[book_id] + 1):
            pos += verse_count_by_chapter[(book_id, ch)]
    for ch in range(1, ref.chapter_number):
        pos += verse_count_by_chapter[(ref.book_id, ch)]
    return pos + ref.verse_number - 1


def verse_distance(
    a: Reference,
    b: Reference,
    *,
    book_order: Sequence[int],
    chapter_count_by_book: ChapterCount,
    verse_count_by_chapter: VerseCount,
) -> int:
    """Signed canon distance from ``a`` to ``b``: positive if ``b`` is after."""
    kw = {
        "book_order": book_order,
        "chapter_count_by_book": chapter_count_by_book,
        "verse_count_by_chapter": verse_count_by_chapter,
    }
    return verse_position(b, **kw) - verse_position(a, **kw)


def prev_reference(
    ref: Reference,
    *,
    book_order: Sequence[int],
    chapter_count_by_book: ChapterCount,
    verse_count_by_chapter: VerseCount,
) -> Reference | None:
    """Return the verse immediately before ``ref``.

    Returns ``None`` at Genesis 1:1 (or whatever the first canon verse is).
    """
    if ref.verse_number > 1:
        return Reference(
            book_id=ref.book_id,
            chapter_number=ref.chapter_number,
            verse_number=ref.verse_number - 1,
        )

    if ref.chapter_number > 1:
        prev_chapter = ref.chapter_number - 1
        last_verse = verse_count_by_chapter[(ref.book_id, prev_chapter)]
        return Reference(
            book_id=ref.book_id,
            chapter_number=prev_chapter,
            verse_number=last_verse,
        )

    book_index = book_order.index(ref.book_id)
    if book_index > 0:
        prev_book = book_order[book_index - 1]
        last_chapter = chapter_count_by_book[prev_book]
        last_verse = verse_count_by_chapter[(prev_book, last_chapter)]
        return Reference(
            book_id=prev_book,
            chapter_number=last_chapter,
            verse_number=last_verse,
        )

    return None
