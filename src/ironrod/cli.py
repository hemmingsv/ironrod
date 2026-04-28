"""ironrod CLI — entry point for ``ironrod`` and ``python -m ironrod``."""

from __future__ import annotations

import fire

from ironrod.clients.bookmarks import BookmarkJournal
from ironrod.clients.scriptures import ScriptureDB
from ironrod.flows.app import run as run_tui


class Cli:
    """Terminal scripture reader.

    Calling ``ironrod`` with no arguments opens the TUI on the last-used
    bookmark (creating ``my-study`` at Genesis 1:1 if no bookmark exists).
    """

    def bookmarks(self) -> None:
        """List bookmarks (most recent first) with their current reference."""
        journal = BookmarkJournal()
        with ScriptureDB() as db:
            for bm in journal.load():
                book = db.book_by_id(bm.reference.book_id)
                ref = f"{book.short_title} {bm.reference.chapter_number}:{bm.reference.verse_number}"
                print(f"{bm.name:<24}  {ref}")

    def where(self) -> None:
        """Print the reference of the most-recently-used bookmark."""
        journal = BookmarkJournal()
        bm = journal.top()
        if bm is None:
            print("(no bookmarks yet)")
            return
        with ScriptureDB() as db:
            book = db.book_by_id(bm.reference.book_id)
            print(
                f"{bm.name}  {book.short_title} "
                f"{bm.reference.chapter_number}:{bm.reference.verse_number}",
            )


def main() -> None:
    """ironrod entry point. Bare invocation runs the TUI; subcommands go
    through python-fire (``ironrod bookmarks``, ``ironrod where``)."""
    import sys
    if len(sys.argv) == 1:
        run_tui()
        return
    fire.Fire(Cli)
