"""State-machine tests for flows.state.App.

Drives the app via on_key() calls, with a real ScriptureDB and the contract-
verified InMemoryBookmarkJournal. Assertions cover:

* first-run auto-creates ``my-study`` at Gen 1:1
* ``j`` advances the cursor; the journal is rewritten with the new top verse
* ``k`` walks back; canon-start stops cleanly
* eternal scroll moves from 1 Nephi 1:20 → 1 Nephi 2:1
* ``g`` opens goto, typing ``1 ne 3`` selects 1 Nephi 3, Enter jumps there
* ``:`` then a number jumps to that verse in the current chapter
* ``b`` opens the switcher, selecting another bookmark moves it to top
* ``c`` from the switcher creates a new bookmark at Gen 1:1
* ``j``/``k`` navigate the switcher; ``PgDn``/``PgUp`` page the study view
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ironrod.clients.bookmarks import BookmarkJournal
from ironrod.clients.scriptures import ScriptureDB
from ironrod.clients.testing.bookmarks_inmemory import InMemoryBookmarkJournal
from ironrod.flows.state import App, INITIAL_REF
from ironrod.models import Reference


@pytest.fixture(scope="module")
def db() -> Iterator[ScriptureDB]:
    with ScriptureDB() as d:
        yield d


@pytest.fixture
def app(db: ScriptureDB) -> App:
    return App(db=db, journal=InMemoryBookmarkJournal(), width=80, height=20)


def _book_id(db: ScriptureDB, title: str) -> int:
    return next(b.id for b in db.books() if b.title == title)


# first-run + autosave

def test_first_run_auto_creates_my_study(app: App) -> None:
    assert app.bookmark.slug == "my-study"
    assert app.bookmark.reference == INITIAL_REF
    assert app.screen == "study"
    assert app.journal.top() is not None
    assert app.journal.top().slug == "my-study"


def test_render_has_correct_height(app: App) -> None:
    out = app.render()
    assert len(out) == app.height


def test_first_render_shows_genesis(app: App) -> None:
    rendered = "\n".join(app.render())
    assert "Genesis 1:1" in rendered
    assert "In the beginning" in rendered


# study scroll

def test_j_advances_cursor_and_persists(app: App) -> None:
    initial = app.bookmark.reference
    app.on_key("j")
    # After one line, top_ref might still equal INITIAL_REF if Gen 1:1 wraps to multiple lines.
    # Walk forward enough to definitely cross a verse boundary.
    for _ in range(50):
        if app.study.top_ref != initial:
            break
        app.on_key("j")
    assert app.study.top_ref != initial
    assert app.journal.top().reference == app.study.top_ref


def test_k_at_canon_start_is_noop(app: App) -> None:
    # We're at Gen 1:1 with offset 0.
    app.on_key("k")
    assert app.study.top_ref == INITIAL_REF
    assert app.study.top_line_offset == 0


def test_pagedown_advances_body_minus_overlap(db: ScriptureDB, app: App) -> None:
    # body_height = 20 - 3 = 17, PAGE_OVERLAP = 3, so a page advances 14
    # verse-line steps. Compare against repeated `j` from the same starting
    # position; well clear of the canon edges.
    nephi = _book_id(db, "1 Nephi")
    start = Reference(book_id=nephi, chapter_number=3, verse_number=1)
    app.study.top_ref = start
    app.study.top_line_offset = 0
    app.on_key("pagedown")
    after_page = (app.study.top_ref, app.study.top_line_offset)
    app.study.top_ref = start
    app.study.top_line_offset = 0
    for _ in range(app.body_height - 3):
        app.on_key("j")
    assert after_page == (app.study.top_ref, app.study.top_line_offset)


def test_pageup_round_trips_with_pagedown(db: ScriptureDB, app: App) -> None:
    nephi = _book_id(db, "1 Nephi")
    start = Reference(book_id=nephi, chapter_number=3, verse_number=1)
    app.study.top_ref = start
    app.study.top_line_offset = 0
    app.on_key("pagedown")
    app.on_key("pageup")
    assert app.study.top_ref == start
    assert app.study.top_line_offset == 0


def test_pageup_at_canon_start_is_noop(app: App) -> None:
    app.on_key("pageup")
    assert app.study.top_ref == INITIAL_REF
    assert app.study.top_line_offset == 0


def test_eternal_scroll_into_next_chapter(db: ScriptureDB, app: App) -> None:
    nephi = _book_id(db, "1 Nephi")
    last_ref = Reference(book_id=nephi, chapter_number=1, verse_number=20)
    app.study.top_ref = last_ref
    app.study.top_line_offset = 0
    # Walk forward enough lines to definitely cross into ch2.
    for _ in range(80):
        before = app.study.top_ref
        app.on_key("j")
        if app.study.top_ref.chapter_number == 2:
            break
    assert app.study.top_ref.chapter_number == 2
    assert app.study.top_ref.verse_number == 1
    # Persistence reflects the new top reference.
    assert app.journal.top().reference == app.study.top_ref


# verse jump

def test_verse_jump_within_chapter(app: App) -> None:
    # Move to start of 1 Nephi 1 first via goto.
    app.on_key("g")
    for ch in "1 ne 1":
        app.on_key(ch)
    app.on_key("enter")
    assert app.screen == "study"
    nephi_book = next(b for b in app.db.books() if b.title == "1 Nephi")
    assert app.study.top_ref == Reference(book_id=nephi_book.id, chapter_number=1, verse_number=1)
    # Now :7 enter
    app.on_key(":")
    assert app.study.mode == "verse-jump"
    app.on_key("7")
    app.on_key("enter")
    assert app.study.top_ref.verse_number == 7
    assert app.study.top_ref.chapter_number == 1


def test_verse_jump_out_of_range_is_flash_only(app: App) -> None:
    # Currently at Gen 1:1 — Genesis 1 has 31 verses. Jump to 999 should fail.
    app.on_key(":")
    for d in "999":
        app.on_key(d)
    app.on_key("enter")
    assert app.study.top_ref == INITIAL_REF
    assert app.flash and "verse 999" in app.flash


def test_verse_jump_escape_cancels(app: App) -> None:
    app.on_key(":")
    app.on_key("4")
    app.on_key("escape")
    assert app.study.mode == "normal"
    assert app.study.top_ref == INITIAL_REF


# goto

def test_goto_filters_by_query(app: App) -> None:
    app.on_key("g")
    for ch in "1 ne 3":
        app.on_key(ch)
    rendered = "\n".join(app.render())
    assert "1 Nephi 3" in rendered


def test_goto_enter_jumps_and_persists(app: App) -> None:
    app.on_key("g")
    for ch in "1 nephi 3":
        app.on_key(ch)
    app.on_key("enter")
    assert app.screen == "study"
    nephi_book = next(b for b in app.db.books() if b.title == "1 Nephi")
    assert app.study.top_ref == Reference(book_id=nephi_book.id, chapter_number=3, verse_number=1)
    assert app.journal.top().reference == app.study.top_ref


def test_goto_escape_cancels(app: App) -> None:
    original = app.study.top_ref
    app.on_key("g")
    app.on_key("escape")
    assert app.screen == "study"
    assert app.study.top_ref == original


# switcher

def test_switcher_shows_bookmarks(app: App) -> None:
    app.journal.create("Evening", Reference(book_id=1, chapter_number=2, verse_number=1))
    app.on_key("b")
    assert app.screen == "switcher"
    rendered = "\n".join(app.render())
    assert "Evening" in rendered
    assert "my-study" in rendered


def test_switcher_select_other_moves_to_top(app: App, db: ScriptureDB) -> None:
    nephi = _book_id(db, "1 Nephi")
    evening_ref = Reference(book_id=nephi, chapter_number=3, verse_number=7)
    app.journal.create("Evening", evening_ref)
    # Now order: evening, my-study. We'll select my-study (index 1).
    app.on_key("b")
    app.on_key("down")
    app.on_key("enter")
    assert app.screen == "study"
    assert app.bookmark.slug == "my-study"
    assert app.journal.top().slug == "my-study"
    assert app.study.top_ref == app.bookmark.reference  # Gen 1:1


def test_switcher_creates_new_at_gen_1_1(app: App) -> None:
    app.on_key("b")
    app.on_key("c")
    assert app.screen == "newbookmark"
    for ch in "evening":
        app.on_key(ch)
    app.on_key("enter")
    assert app.screen == "study"
    assert app.bookmark.slug == "evening"
    assert app.bookmark.reference == INITIAL_REF


def test_switcher_n_does_not_create_new(app: App) -> None:
    # ``n`` used to mean "new"; it must no longer trigger create.
    app.on_key("b")
    app.on_key("n")
    assert app.screen == "switcher"


def test_switcher_n_still_cancels_delete(app: App) -> None:
    app.journal.create("Evening", Reference(book_id=1, chapter_number=2, verse_number=1))
    app.on_key("b")
    app.on_key("d")
    assert app.switcher.confirming_delete is True
    app.on_key("n")
    assert app.switcher.confirming_delete is False
    # Bookmarks unchanged.
    assert len(app.journal.load()) == 2


def test_switcher_j_k_navigate_selection(app: App) -> None:
    app.journal.create("Evening", Reference(book_id=1, chapter_number=2, verse_number=1))
    app.on_key("b")
    assert app.switcher.selected == 0
    app.on_key("j")
    assert app.switcher.selected == 1
    app.on_key("k")
    assert app.switcher.selected == 0


def test_switcher_new_empty_name_shows_error(app: App) -> None:
    app.on_key("b")
    app.on_key("c")
    app.on_key("enter")
    assert app.screen == "newbookmark"
    assert app.newbookmark.error == "name cannot be empty"


def test_switcher_new_duplicate_name_shows_error(app: App) -> None:
    app.on_key("b")
    app.on_key("c")
    for ch in "my-study":
        app.on_key(ch)
    app.on_key("enter")
    assert app.screen == "newbookmark"
    assert app.newbookmark.error is not None
    assert "already exists" in app.newbookmark.error


def test_switcher_delete_last_blocks(app: App) -> None:
    app.on_key("b")
    app.on_key("d")
    assert app.switcher.confirming_delete is True
    app.on_key("y")
    assert app.flash and "last bookmark" in app.flash
    assert app.journal.top() is not None


def test_switcher_delete_with_two_works(app: App) -> None:
    app.journal.create("Evening", Reference(book_id=1, chapter_number=2, verse_number=1))
    app.on_key("b")
    app.on_key("d")
    app.on_key("y")
    bookmarks = app.journal.load()
    assert len(bookmarks) == 1
    assert bookmarks[0].slug == "my-study"


def test_switcher_escape_returns_to_study(app: App) -> None:
    app.on_key("b")
    app.on_key("escape")
    assert app.screen == "study"


# disk integration: same flow with real BookmarkJournal

def test_disk_journal_persists_after_navigation(tmp_path, db: ScriptureDB) -> None:
    journal = BookmarkJournal(path=tmp_path / "bookmarks.jsonl")
    app = App(db=db, journal=journal, width=80, height=20)
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    new_top = app.study.top_ref
    # Reopen with a fresh App and verify it lands where we left off.
    journal2 = BookmarkJournal(path=tmp_path / "bookmarks.jsonl")
    app2 = App(db=db, journal=journal2, width=80, height=20)
    assert app2.bookmark.slug == "my-study"
    assert app2.bookmark.reference == new_top
    assert app2.study.top_ref == new_top
