"""Read-only SQLite client for the bundled scripture database."""

from __future__ import annotations

import sqlite3
from importlib.resources import as_file, files
from pathlib import Path
from types import TracebackType

from ironrod.core.navigation import next_reference, prev_reference, verse_distance
from ironrod.core.navigation import (
    next_chapter_start,
    next_reference,
    prev_chapter_start,
    prev_reference,
)
from ironrod.models import Book, ChapterEntry, Reference, Verse, Volume


def _bundled_db_path() -> Path:
    """Resolve the path to the bundled SQLite DB.

    ``importlib.resources.as_file`` returns a context manager that materialises
    the resource on disk if it lives inside a zip; we exit it immediately and
    keep the path because the wheel layout always extracts to a real file.
    """
    resource = files("ironrod.data").joinpath("scriptures.db")
    with as_file(resource) as p:
        return Path(p)


class ScriptureDB:
    """Read-only client over the bundled scriptures DB.

    Builds in-memory indexes on enter so navigation is O(1).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _bundled_db_path()
        self._con: sqlite3.Connection | None = None
        self._book_order: list[int] = []
        self._chapter_count_by_book: dict[int, int] = {}
        self._verse_count_by_chapter: dict[tuple[int, int], int] = {}
        self._books_by_id: dict[int, Book] = {}
        self._volumes_by_id: dict[int, Volume] = {}

    # context manager

    def __enter__(self) -> "ScriptureDB":
        uri = f"file:{self._db_path}?mode=ro"
        self._con = sqlite3.connect(uri, uri=True)
        self._con.row_factory = sqlite3.Row
        self._build_indexes()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    # index construction

    def _build_indexes(self) -> None:
        assert self._con is not None
        for row in self._con.execute(
            "SELECT id, volume_title, volume_short_title FROM volumes ORDER BY id"
        ):
            self._volumes_by_id[row["id"]] = Volume(
                id=row["id"],
                title=row["volume_title"],
                short_title=row["volume_short_title"],
            )
        for row in self._con.execute(
            "SELECT id, volume_id, book_title, book_short_title FROM books ORDER BY id"
        ):
            book = Book(
                id=row["id"],
                volume_id=row["volume_id"],
                title=row["book_title"],
                short_title=row["book_short_title"],
            )
            self._books_by_id[book.id] = book
            self._book_order.append(book.id)
        for row in self._con.execute(
            "SELECT book_id, COUNT(*) AS n FROM chapters GROUP BY book_id"
        ):
            self._chapter_count_by_book[row["book_id"]] = row["n"]
        for row in self._con.execute(
            """
            SELECT c.book_id AS book_id,
                   c.chapter_number AS chapter_number,
                   COUNT(v.id) AS n
            FROM chapters c
            JOIN verses v ON v.chapter_id = c.id
            GROUP BY c.book_id, c.chapter_number
            """
        ):
            self._verse_count_by_chapter[(row["book_id"], row["chapter_number"])] = row["n"]

    # public API

    def volumes(self) -> list[Volume]:
        return list(self._volumes_by_id.values())

    def books(self, volume_id: int | None = None) -> list[Book]:
        if volume_id is None:
            return [self._books_by_id[i] for i in self._book_order]
        return [b for b in self._books_by_id.values() if b.volume_id == volume_id]

    def book_by_id(self, book_id: int) -> Book:
        return self._books_by_id[book_id]

    def chapter_count(self, book_id: int) -> int:
        return self._chapter_count_by_book[book_id]

    def verse_count(self, book_id: int, chapter_number: int) -> int:
        return self._verse_count_by_chapter[(book_id, chapter_number)]

    def verse(self, ref: Reference) -> Verse:
        assert self._con is not None
        row = self._con.execute(
            """
            SELECT scripture_text, book_title, book_short_title
            FROM scriptures
            WHERE book_id = ? AND chapter_number = ? AND verse_number = ?
            """,
            (ref.book_id, ref.chapter_number, ref.verse_number),
        ).fetchone()
        if row is None:
            raise KeyError(ref)
        return Verse(
            reference=ref,
            book_title=row["book_title"],
            book_short_title=row["book_short_title"],
            text=row["scripture_text"],
        )

    def chapter_verses(self, book_id: int, chapter_number: int) -> list[Verse]:
        assert self._con is not None
        rows = self._con.execute(
            """
            SELECT verse_number, scripture_text, book_title, book_short_title
            FROM scriptures
            WHERE book_id = ? AND chapter_number = ?
            ORDER BY verse_number
            """,
            (book_id, chapter_number),
        ).fetchall()
        return [
            Verse(
                reference=Reference(
                    book_id=book_id,
                    chapter_number=chapter_number,
                    verse_number=row["verse_number"],
                ),
                book_title=row["book_title"],
                book_short_title=row["book_short_title"],
                text=row["scripture_text"],
            )
            for row in rows
        ]

    def chapter_index(self) -> list[ChapterEntry]:
        out: list[ChapterEntry] = []
        for book_id in self._book_order:
            book = self._books_by_id[book_id]
            for ch in range(1, self._chapter_count_by_book[book_id] + 1):
                out.append(
                    ChapterEntry(
                        book_id=book_id,
                        book_title=book.title,
                        book_short_title=book.short_title,
                        chapter_number=ch,
                        label=f"{book.title} {ch}",
                    )
                )
        return out

    def next_reference(self, ref: Reference) -> Reference | None:
        return next_reference(
            ref,
            book_order=self._book_order,
            chapter_count_by_book=self._chapter_count_by_book,
            verse_count_by_chapter=self._verse_count_by_chapter,
        )

    def prev_reference(self, ref: Reference) -> Reference | None:
        return prev_reference(
            ref,
            book_order=self._book_order,
            chapter_count_by_book=self._chapter_count_by_book,
            verse_count_by_chapter=self._verse_count_by_chapter,
        )

    def verse_distance(self, a: Reference, b: Reference) -> int:
        return verse_distance(
            a,
            b,
            book_order=self._book_order,
            chapter_count_by_book=self._chapter_count_by_book,
            verse_count_by_chapter=self._verse_count_by_chapter,
        )
    
    def next_chapter_start(self, ref: Reference) -> Reference | None:
        return next_chapter_start(
            ref,
            book_order=self._book_order,
            chapter_count_by_book=self._chapter_count_by_book,
        )

    def prev_chapter_start(self, ref: Reference) -> Reference | None:
        return prev_chapter_start(
            ref,
            book_order=self._book_order,
            chapter_count_by_book=self._chapter_count_by_book,
        )

    # introspection helpers used by the layout code

    @property
    def book_order(self) -> list[int]:
        return list(self._book_order)

    def first_reference(self) -> Reference:
        first_book = self._book_order[0]
        return Reference(book_id=first_book, chapter_number=1, verse_number=1)

    def last_reference(self) -> Reference:
        last_book = self._book_order[-1]
        last_chapter = self._chapter_count_by_book[last_book]
        last_verse = self._verse_count_by_chapter[(last_book, last_chapter)]
        return Reference(
            book_id=last_book,
            chapter_number=last_chapter,
            verse_number=last_verse,
        )
