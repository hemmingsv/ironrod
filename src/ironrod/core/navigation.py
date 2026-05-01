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


def next_chapter_start(
    ref: Reference,
    *,
    book_order: Sequence[int],
    chapter_count_by_book: ChapterCount,
) -> Reference | None:
    """Return verse 1 of the chapter immediately after ``ref``'s chapter.

    Returns ``None`` if ``ref`` is in the final chapter of the canon.
    """
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


def prev_chapter_start(
    ref: Reference,
    *,
    book_order: Sequence[int],
    chapter_count_by_book: ChapterCount,
) -> Reference | None:
    """Return verse 1 of the chapter immediately before ``ref``'s chapter.

    Returns ``None`` if ``ref`` is in the first chapter of the canon.
    """
    if ref.chapter_number > 1:
        return Reference(
            book_id=ref.book_id,
            chapter_number=ref.chapter_number - 1,
            verse_number=1,
        )

    book_index = book_order.index(ref.book_id)
    if book_index > 0:
        prev_book = book_order[book_index - 1]
        last_chapter = chapter_count_by_book[prev_book]
        return Reference(
            book_id=prev_book,
            chapter_number=last_chapter,
            verse_number=1,
        )

    return None
