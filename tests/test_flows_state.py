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
from ironrod.clients.history import HistoryJournal
from ironrod.clients.scriptures import ScriptureDB
from ironrod.clients.testing.bookmarks_inmemory import InMemoryBookmarkJournal
from ironrod.clients.testing.history_inmemory import InMemoryHistoryJournal
from ironrod.flows.state import App, INITIAL_REF
from ironrod.models import Reference


@pytest.fixture(scope="module")
def db() -> Iterator[ScriptureDB]:
    with ScriptureDB() as d:
        yield d


@pytest.fixture
def app(db: ScriptureDB) -> App:
    return App(
        db=db,
        journal=InMemoryBookmarkJournal(),
        history=InMemoryHistoryJournal(),
        width=80,
        height=20,
    )


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


def test_pagedown_aligns_to_last_visible_verse_start(db: ScriptureDB, app: App) -> None:
    # PgDn aligns the new top to the last verse whose start was on screen
    # before the page. That verse must be one which appeared in the original
    # rendered viewport (so no skipping past unseen content), and the new
    # offset must be 0 (top-aligned).
    nephi = _book_id(db, "1 Nephi")
    start = Reference(book_id=nephi, chapter_number=3, verse_number=1)
    app.study.top_ref = start
    app.study.top_line_offset = 0
    before_render = "\n".join(app.render())
    app.on_key("pagedown")
    assert app.study.top_line_offset == 0
    new_top = app.study.top_ref
    assert new_top != start  # we advanced
    assert new_top.book_id == start.book_id
    assert new_top.chapter_number == start.chapter_number
    assert new_top.verse_number > start.verse_number
    # The verse picked must have been visible (its number prefix renders as
    # ``" {n} "`` at column 0 — see utils.wrap.wrap_verse).
    assert f"{new_top.verse_number:>3} " in before_render


def test_pageup_after_pagedown_makes_top_verse_end_visible(db: ScriptureDB, app: App) -> None:
    # PgDn then PgUp: the verse we just paged onto must reappear in its
    # entirety at (or near) the bottom of the new viewport.
    nephi = _book_id(db, "1 Nephi")
    start = Reference(book_id=nephi, chapter_number=3, verse_number=1)
    app.study.top_ref = start
    app.study.top_line_offset = 0
    app.on_key("pagedown")
    paged_top = app.study.top_ref
    app.on_key("pageup")
    rendered = "\n".join(app.render())
    # The verse we paged onto is now fully visible — its number appears
    # somewhere in the body.
    assert f"{paged_top.verse_number:>3} " in rendered
    # And its full text is reachable from the new top by scanning forward.
    assert app.study.top_ref.verse_number <= paged_top.verse_number


def test_pageup_at_canon_start_is_noop(app: App) -> None:
    app.on_key("pageup")
    assert app.study.top_ref == INITIAL_REF
    assert app.study.top_line_offset == 0


def test_shift_j_jumps_to_next_chapter_start(db: ScriptureDB, app: App) -> None:
    # From Gen 1:1, Shift-J → Gen 2:1, regardless of being on v1.
    app.on_key("J")
    assert app.study.top_ref == Reference(book_id=1, chapter_number=2, verse_number=1)
    assert app.study.top_line_offset == 0
    assert app.journal.top().reference == app.study.top_ref


def test_shift_j_from_mid_chapter_jumps_to_next_chapter(db: ScriptureDB, app: App) -> None:
    # Verse-jump to Gen 1:5, then Shift-J → Gen 2:1.
    app.on_key(":")
    app.on_key("5")
    app.on_key("enter")
    assert app.study.top_ref.verse_number == 5
    app.on_key("J")
    assert app.study.top_ref == Reference(book_id=1, chapter_number=2, verse_number=1)


def test_shift_k_at_verse_one_jumps_to_previous_chapter(db: ScriptureDB, app: App) -> None:
    # From Gen 2:1, Shift-K → Gen 1:1.
    app.study.top_ref = Reference(book_id=1, chapter_number=2, verse_number=1)
    app.study.top_line_offset = 0
    app.on_key("K")
    assert app.study.top_ref == Reference(book_id=1, chapter_number=1, verse_number=1)


def test_shift_k_past_verse_one_snaps_to_verse_one(db: ScriptureDB, app: App) -> None:
    # From Gen 1:5 (not v1), Shift-K → Gen 1:1.
    app.on_key(":")
    app.on_key("5")
    app.on_key("enter")
    assert app.study.top_ref.verse_number == 5
    app.on_key("K")
    assert app.study.top_ref == Reference(book_id=1, chapter_number=1, verse_number=1)
    # Pressing K again now (at v1) crosses the chapter boundary — but we're at
    # the very first chapter, so it's a no-op.
    app.on_key("K")
    assert app.study.top_ref == Reference(book_id=1, chapter_number=1, verse_number=1)


def test_shift_k_at_canon_start_is_noop(app: App) -> None:
    app.on_key("K")
    assert app.study.top_ref == INITIAL_REF
    assert app.study.top_line_offset == 0


def test_shift_j_crosses_book_boundary(db: ScriptureDB, app: App) -> None:
    # Genesis has 50 chapters; from Gen 50:1, Shift-J → Exodus 1:1.
    exodus = _book_id(db, "Exodus")
    app.study.top_ref = Reference(book_id=1, chapter_number=50, verse_number=1)
    app.study.top_line_offset = 0
    app.on_key("J")
    assert app.study.top_ref == Reference(book_id=exodus, chapter_number=1, verse_number=1)


def test_shift_k_crosses_book_boundary(db: ScriptureDB, app: App) -> None:
    # From Exodus 1:1, Shift-K → Gen 50:1 (last chapter of previous book, v1).
    exodus = _book_id(db, "Exodus")
    app.study.top_ref = Reference(book_id=exodus, chapter_number=1, verse_number=1)
    app.study.top_line_offset = 0
    app.on_key("K")
    assert app.study.top_ref == Reference(book_id=1, chapter_number=50, verse_number=1)

    
def test_pageup_keeps_top_verse_visible_across_chapter_boundary(
    db: ScriptureDB, app: App,
) -> None:
    # When the top verse is the first verse of a chapter, paging up walks
    # back through the chapter header above it. The header takes up a row
    # in the new viewport; if the walk-back ignored it, ``lay_out`` would
    # shove the original top verse past the bottom of the screen.
    nephi = _book_id(db, "1 Nephi")
    start = Reference(book_id=nephi, chapter_number=3, verse_number=1)
    app.study.top_ref = start
    app.study.top_line_offset = 0
    app.on_key("pageup")
    rendered_body = "\n".join(app.render()[1 : 1 + app.body_height])
    # 1 Nephi 3:1 must still be on screen after PgUp.
    assert "  1 " in rendered_body  # verse-1 prefix from utils.wrap.wrap_verse
    # The new top must be canonically before the original top.
    new_top = app.study.top_ref
    assert (new_top.book_id, new_top.chapter_number, new_top.verse_number) < (
        start.book_id, start.chapter_number, start.verse_number,
    )
    # And the chapter-3 header must be on screen too — that's what the user
    # expects: the verse fully visible at the bottom, with the header row
    # immediately above it.
    assert "1 Nephi 3" in rendered_body


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
    # Move to start of 1 Nephi 1 first via goto. Use the full book name so
    # the query is unambiguous from Genesis (otherwise tiered ordering picks
    # a same-volume match like 1 Chronicles 1 ahead of cross-volume 1 Nephi).
    app.on_key("g")
    for ch in "1 nephi 1":
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


def test_verse_jump_negative_last(app: App) -> None:
    # Genesis 1 has 31 verses; :-1 jumps to the last.
    app.on_key(":")
    app.on_key("-")
    app.on_key("1")
    app.on_key("enter")
    assert app.study.top_ref.verse_number == 31
    assert app.study.top_ref.chapter_number == 1


def test_verse_jump_negative_second_to_last(app: App) -> None:
    app.on_key(":")
    for k in "-2":
        app.on_key(k)
    app.on_key("enter")
    assert app.study.top_ref.verse_number == 30
    assert app.study.top_ref.chapter_number == 1


def test_verse_jump_negative_out_of_range_is_flash_only(app: App) -> None:
    app.on_key(":")
    for k in "-999":
        app.on_key(k)
    app.on_key("enter")
    assert app.study.top_ref == INITIAL_REF
    assert app.flash and "verse -999" in app.flash


def test_verse_jump_positive_out_of_range_hints_negative(app: App) -> None:
    app.on_key(":")
    for k in "999":
        app.on_key(k)
    app.on_key("enter")
    assert app.study.top_ref == INITIAL_REF
    assert app.flash and "try -1" in app.flash


def test_verse_jump_bare_minus_is_noop(app: App) -> None:
    app.on_key(":")
    app.on_key("-")
    assert app.study.verse_jump_buf == "-"
    app.on_key("enter")
    assert app.study.mode == "normal"
    assert app.study.top_ref == INITIAL_REF
    assert app.flash is None


def test_verse_jump_minus_only_allowed_at_start(app: App) -> None:
    # Once digits are entered, a stray '-' is ignored, not appended.
    app.on_key(":")
    app.on_key("1")
    app.on_key("-")
    assert app.study.verse_jump_buf == "1"


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


def test_goto_ctrl_n_and_ctrl_p_navigate_selection(app: App) -> None:
    app.on_key("g")
    assert app.goto.selected == 0
    app.on_key("ctrl-n")
    assert app.goto.selected == 1
    app.on_key("ctrl-n")
    assert app.goto.selected == 2
    app.on_key("ctrl-p")
    assert app.goto.selected == 1
    app.on_key("ctrl-p")
    app.on_key("ctrl-p")
    assert app.goto.selected == 0

    
def test_goto_prefers_current_book_on_score_tie(app: App, db: ScriptureDB) -> None:
    # Typing "j" matches Job, Jude, Joel, James, Jacob, John, etc. With the
    # cursor in 2 Nephi (Book of Mormon), Jacob (also BoM) should rank above
    # Job/James/etc — same-volume tier wins on score ties.
    nephi2 = _book_id(db, "2 Nephi")
    app.study.top_ref = Reference(book_id=nephi2, chapter_number=15, verse_number=1)
    app.on_key("g")
    app.on_key("j")
    titles = [entry.label for entry, _ in app._filtered_chapters()]
    jacob_pos = next(i for i, t in enumerate(titles) if t.startswith("Jacob "))
    job_pos = next(i for i, t in enumerate(titles) if t.startswith("Job "))
    assert jacob_pos < job_pos


def test_goto_numeric_selects_current_book_chapter(app: App, db: ScriptureDB) -> None:
    # A bare number works as a chapter selector for the current book — it's
    # the natural consequence of preferring same-book chapters on score ties.
    nephi2 = _book_id(db, "2 Nephi")
    app.study.top_ref = Reference(book_id=nephi2, chapter_number=15, verse_number=1)
    app.on_key("g")
    app.on_key("5")
    app.on_key("enter")
    assert app.study.top_ref.book_id == nephi2
    assert app.study.top_ref.chapter_number == 5


def test_goto_same_volume_ranks_above_other_volumes(app: App, db: ScriptureDB) -> None:
    # In 2 Nephi (BoM), typing "1" should put BoM chapters ahead of OT/NT
    # chapters with the same fuzzy score.
    nephi2 = _book_id(db, "2 Nephi")
    app.study.top_ref = Reference(book_id=nephi2, chapter_number=15, verse_number=1)
    app.on_key("g")
    app.on_key("1")
    chapters = app._filtered_chapters()
    bom_id = db.book_by_id(nephi2).volume_id
    # Walk the list until we find an entry outside the current book; that
    # entry should still belong to the same volume (Book of Mormon).
    first_other_book = next(
        entry for entry, _ in chapters if entry.book_id != nephi2
    )
    assert db.book_by_id(first_other_book.book_id).volume_id == bom_id


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


def test_switcher_default_selects_previous_bookmark(app: App, db: ScriptureDB) -> None:
    # b+Enter behaves like Alt+Tab: when the active bookmark sits at the top
    # of the list, the default selection lands on the next-most-recent one,
    # so Enter immediately switches back to the previous bookmark.
    nephi = _book_id(db, "1 Nephi")
    app.journal.create("Evening", Reference(book_id=nephi, chapter_number=3, verse_number=7))
    # Switch to Evening so it's the active bookmark and sits at the top.
    app.on_key("b")
    app.on_key("enter")
    assert app.bookmark.slug == "evening"
    assert app.journal.load()[0].slug == "evening"
    # Now b should default to my-study (index 1, the previous bookmark).
    app.on_key("b")
    assert app.switcher.selected == 1
    app.on_key("enter")
    assert app.bookmark.slug == "my-study"


def test_switcher_default_with_only_one_bookmark_is_zero(app: App) -> None:
    # Single bookmark — default selection has nowhere else to go.
    app.on_key("b")
    assert app.switcher.selected == 0


def test_switcher_default_skips_active_when_active_not_at_top(
    app: App, db: ScriptureDB,
) -> None:
    # Edge case: active bookmark isn't at index 0 (e.g. another bookmark was
    # just created). Default should still skip the active one.
    nephi = _book_id(db, "1 Nephi")
    app.journal.create("Evening", Reference(book_id=nephi, chapter_number=3, verse_number=7))
    # bookmarks = [evening, my-study], active = my-study (still at index 1).
    app.on_key("b")
    assert app.switcher.selected == 0  # evening, the first non-active entry


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


def test_switcher_ctrl_n_ctrl_p_navigate_selection(app: App) -> None:
    app.journal.create("Evening", Reference(book_id=1, chapter_number=2, verse_number=1))
    app.on_key("b")
    assert app.switcher.selected == 0
    app.on_key("ctrl-n")
    assert app.switcher.selected == 1
    app.on_key("ctrl-p")
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


# history mode

def _refs(app: App) -> list[Reference]:
    return [r.reference for r in app.history.load_for(app.bookmark.slug)]


def test_first_run_seeds_initial_history(app: App) -> None:
    assert _refs(app) == [INITIAL_REF]


def test_scroll_does_not_commit_to_history(app: App) -> None:
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    assert app.study.top_ref != initial
    assert _refs(app) == [INITIAL_REF]  # scroll alone never commits


def test_enter_in_normal_mode_commits_head(app: App) -> None:
    # Scroll to a new position, then press Enter to commit it.
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    new_top = app.study.top_ref
    app.on_key("enter")
    assert _refs(app) == [INITIAL_REF, new_top]
    assert app.study.mode == "normal"
    # Pressing Enter again at the same place is a no-op (dedup).
    app.on_key("enter")
    assert _refs(app) == [INITIAL_REF, new_top]


def test_goto_commits_source_and_destination(app: App, db: ScriptureDB) -> None:
    # Scroll past the initial position so "source" differs from "destination".
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    source = app.study.top_ref
    app.on_key("g")
    for ch in "1 nephi 3":
        app.on_key(ch)
    app.on_key("enter")
    nephi = next(b for b in db.books() if b.title == "1 Nephi")
    dest = Reference(book_id=nephi.id, chapter_number=3, verse_number=1)
    assert _refs(app)[-3:] == [INITIAL_REF, source, dest]


def test_verse_jump_commits_source_and_destination(app: App, db: ScriptureDB) -> None:
    # Goto Genesis 2 first so we can verse-jump within it.
    app.on_key("g")
    for ch in "genesis 2":
        app.on_key(ch)
    app.on_key("enter")
    gen2_1 = app.study.top_ref
    # Scroll to verse 5 (or wherever 4 lines down lands).
    for _ in range(60):
        before = app.study.top_ref
        app.on_key("j")
        if app.study.top_ref != before and app.study.top_ref.verse_number == 5:
            break
    source = app.study.top_ref
    assert source.verse_number == 5
    app.on_key(":")
    app.on_key("1")
    app.on_key("5")
    app.on_key("enter")
    dest = app.study.top_ref
    assert dest.verse_number == 15
    refs = _refs(app)
    # Initial Gen 1:1 + goto source/dest (Gen 1:1 dedup'd, then Gen 2:1) +
    # verse-jump source/dest (Gen 2:5, Gen 2:15).
    assert refs[-3:] == [gen2_1, source, dest]


def test_left_in_normal_mode_enters_history_and_walks_back(app: App) -> None:
    # Build up some history: scroll → Enter, then scroll → Enter.
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    first = app.study.top_ref
    app.on_key("enter")
    for _ in range(60):
        before = app.study.top_ref
        app.on_key("j")
        if app.study.top_ref != before:
            break
    second = app.study.top_ref
    app.on_key("enter")
    # History: [INITIAL_REF, first, second].
    assert _refs(app) == [INITIAL_REF, first, second]
    app.on_key("left")
    assert app.study.mode == "history"
    assert app.study.top_ref == first
    # Footer reflects the indicator.
    rendered = "\n".join(app.render())
    assert "← 2/3 →" in rendered
    app.on_key("left")
    assert app.study.top_ref == INITIAL_REF
    # Walk past the start is a no-op.
    app.on_key("left")
    assert app.study.top_ref == INITIAL_REF
    app.on_key("right")
    assert app.study.top_ref == first
    app.on_key("right")
    assert app.study.top_ref == second
    app.on_key("right")
    assert app.study.top_ref == second  # at end


def test_right_in_normal_mode_is_noop(app: App) -> None:
    before_ref = app.study.top_ref
    before_history = _refs(app)
    app.on_key("right")
    assert app.study.mode == "normal"
    assert app.study.top_ref == before_ref
    assert _refs(app) == before_history


def test_left_with_only_initial_record_flashes(app: App) -> None:
    # Fresh app: only INITIAL_REF is in history.
    assert _refs(app) == [INITIAL_REF]
    app.on_key("left")
    assert app.study.mode == "normal"
    assert app.flash and "no earlier history" in app.flash


def test_enter_in_history_mode_settles_and_exits(app: App) -> None:
    # Build up [INITIAL_REF, A].
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    a = app.study.top_ref
    app.on_key("enter")
    app.on_key("left")
    assert app.study.mode == "history"
    assert app.study.top_ref == initial
    app.on_key("enter")
    assert app.study.mode == "normal"
    # The walked-to position was committed (deduped if equal to last).
    refs = _refs(app)
    assert refs == [INITIAL_REF, a, initial]


def test_escape_in_history_mode_returns_to_floating_head(app: App) -> None:
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    a = app.study.top_ref
    app.on_key("enter")
    app.on_key("left")
    assert app.study.mode == "history"
    assert app.study.top_ref == initial  # walked back visually
    # The walk does not persist — bookmark on disk still points at the entry.
    assert app.journal.get(app.bookmark.slug).reference == a
    before = list(_refs(app))
    app.on_key("escape")
    assert app.study.mode == "normal"
    assert app.study.top_ref == a  # HEAD restored to entry position
    assert _refs(app) == before  # history untouched
    assert app.journal.get(app.bookmark.slug).reference == a  # journal unchanged


def test_escape_from_floating_head_restores_without_editing_history(
    app: App,
) -> None:
    """HEAD scrolled past the last commit (floating). ← enters history mode
    without recording the floating position; Esc returns to it; history is
    unchanged throughout.
    """
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    a = app.study.top_ref
    app.on_key("enter")  # commits a → [INITIAL_REF, a]
    # Scroll past `a` without committing — HEAD is now floating.
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != a:
            break
    floating = app.study.top_ref
    assert floating != a
    history_before = list(_refs(app))
    assert history_before == [INITIAL_REF, a]
    journal_before = app.journal.get(app.bookmark.slug).reference
    assert journal_before == floating
    app.on_key("left")
    assert app.study.mode == "history"
    # First step from a floating HEAD lands on the most recent record.
    assert app.study.top_ref == a
    # Entry alone does not write to history or to the bookmark journal.
    assert _refs(app) == history_before
    assert app.journal.get(app.bookmark.slug).reference == floating
    app.on_key("left")
    assert app.study.top_ref == INITIAL_REF
    # Walking does not persist either.
    assert app.journal.get(app.bookmark.slug).reference == floating
    app.on_key("escape")
    assert app.study.mode == "normal"
    assert app.study.top_ref == floating  # restored
    assert _refs(app) == history_before  # history still untouched
    assert app.journal.get(app.bookmark.slug).reference == floating


def test_scroll_in_history_mode_exits_with_commit_then_scrolls(app: App) -> None:
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    a = app.study.top_ref
    app.on_key("enter")
    app.on_key("left")
    assert app.study.mode == "history"
    assert app.study.top_ref == initial
    # j should: commit current (initial), exit history, then scroll.
    app.on_key("j")
    assert app.study.mode == "normal"
    refs = _refs(app)
    # [initial, a, initial] — last commit dedup-checked against `a` (different),
    # so initial is appended again.
    assert refs == [INITIAL_REF, a, initial]


def test_dedup_after_enter_then_left(app: App) -> None:
    """User's example: at HEAD = X, press Enter (no-op), then ← goes to prior."""
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    a = app.study.top_ref
    app.on_key("enter")  # commit A → [INITIAL, A]
    app.on_key("enter")  # dedup, no-op
    refs_before = _refs(app)
    assert refs_before == [INITIAL_REF, a]
    app.on_key("left")  # enters history, commits A (dedup), walks to prior.
    assert app.study.top_ref == INITIAL_REF
    # Indicator should show 1/2, not 1/3 — dedup means no growth.
    assert _refs(app) == [INITIAL_REF, a]
    rendered = "\n".join(app.render())
    assert "← 1/2 →" in rendered


def test_switcher_does_not_commit_to_history(app: App, db: ScriptureDB) -> None:
    # Create a second bookmark and switch to it via the switcher.
    nephi = _book_id(db, "1 Nephi")
    other_ref = Reference(book_id=nephi, chapter_number=3, verse_number=7)
    app.journal.create("Evening", other_ref)
    history_before = list(_refs(app))
    app.on_key("b")
    app.on_key("enter")  # selects Evening (top of switcher)
    assert app.bookmark.slug == "evening"
    # The OLD bookmark's history is untouched.
    refs_old = [r.reference for r in app.history.load_for("my-study")]
    assert refs_old == history_before
    # The NEW bookmark's history was not auto-committed by the switch either.
    assert app.history.load_for("evening") == []


def test_new_bookmark_seeds_history(app: App) -> None:
    app.on_key("b")
    app.on_key("c")
    for ch in "evening":
        app.on_key(ch)
    app.on_key("enter")
    assert app.bookmark.slug == "evening"
    refs = [r.reference for r in app.history.load_for("evening")]
    assert refs == [INITIAL_REF]


def test_history_is_per_bookmark(app: App, db: ScriptureDB) -> None:
    # Move my-study somewhere and commit it.
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    moved = app.study.top_ref
    app.on_key("enter")
    # Create a second bookmark via the new-bookmark flow.
    app.on_key("b")
    app.on_key("c")
    for ch in "evening":
        app.on_key(ch)
    app.on_key("enter")
    # Walk back in evening's history — only INITIAL_REF is there, so flash.
    app.on_key("left")
    assert app.flash and "no earlier history" in app.flash
    # my-study's history is unaffected.
    assert [r.reference for r in app.history.load_for("my-study")] == [
        INITIAL_REF,
        moved,
    ]


def test_genesis_2_walk_end_to_end(app: App, db: ScriptureDB) -> None:
    """Mirrors the canonical user-described flow:
    goto Gen 2 → scroll to v5 → :15 → ← ← → → walks back and forward.
    """
    # 1. Goto Genesis 2.
    app.on_key("g")
    for ch in "genesis 2":
        app.on_key(ch)
    app.on_key("enter")
    gen2_1 = app.study.top_ref
    assert gen2_1.chapter_number == 2 and gen2_1.verse_number == 1
    # 2. Scroll until verse 5 reaches the top.
    for _ in range(80):
        app.on_key("j")
        if app.study.top_ref.verse_number == 5:
            break
    gen2_5 = app.study.top_ref
    assert gen2_5.verse_number == 5
    # 3. Verse-jump to 15.
    app.on_key(":")
    app.on_key("1")
    app.on_key("5")
    app.on_key("enter")
    gen2_15 = app.study.top_ref
    assert gen2_15.verse_number == 15
    # History from this bookmark — note Gen 1:1 (initial) precedes the goto.
    assert _refs(app) == [INITIAL_REF, gen2_1, gen2_5, gen2_15]
    # 4-7. Walk back twice, then forward twice.
    app.on_key("left")
    assert app.study.top_ref == gen2_5
    app.on_key("left")
    assert app.study.top_ref == gen2_1
    app.on_key("right")
    assert app.study.top_ref == gen2_5
    app.on_key("right")
    assert app.study.top_ref == gen2_15


def test_history_mode_header_shows_indicator(app: App) -> None:
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    app.on_key("enter")
    app.on_key("left")
    rendered = "\n".join(app.render())
    assert "[history]" in rendered


# session "verses read" cursor

def _scroll_until_top_changes(app: App, max_steps: int = 60) -> Reference:
    initial = app.study.top_ref
    for _ in range(max_steps):
        app.on_key("j")
        if app.study.top_ref != initial:
            return app.study.top_ref
    raise AssertionError("scroll never crossed a verse boundary")


def test_read_cursor_initialized_at_head_on_first_run(app: App) -> None:
    assert app.read_cursors[app.bookmark.slug] == app.bookmark.reference


def test_read_indicator_hidden_at_zero_verses_read(app: App) -> None:
    rendered = "\n".join(app.render())
    assert "verses read" not in rendered


def test_read_indicator_shows_after_scrolling_down(app: App) -> None:
    _scroll_until_top_changes(app)
    rendered = "\n".join(app.render())
    assert "verses read" in rendered


def test_read_indicator_right_aligned_in_header(app: App) -> None:
    _scroll_until_top_changes(app)
    header = app.render()[0]
    assert header.rstrip().endswith("verses read")
    assert app.bookmark.name in header


def test_enter_resets_read_cursor(app: App) -> None:
    moved = _scroll_until_top_changes(app)
    assert "verses read" in "\n".join(app.render())
    app.on_key("enter")
    assert app.read_cursors[app.bookmark.slug] == moved
    assert "verses read" not in "\n".join(app.render())


def test_scroll_up_below_cursor_hides_indicator(db: ScriptureDB, app: App) -> None:
    # Park HEAD a little forward so we can scroll up past the initial cursor.
    nephi = _book_id(db, "1 Nephi")
    start = Reference(book_id=nephi, chapter_number=3, verse_number=5)
    app.read_cursors[app.bookmark.slug] = start
    app.study.top_ref = start
    # Scroll up so HEAD is before the cursor.
    for _ in range(60):
        before = app.study.top_ref
        app.on_key("k")
        if app.study.top_ref != before:
            break
    assert app.db.verse_distance(start, app.study.top_ref) < 0
    assert "verses read" not in "\n".join(app.render())


def test_verse_jump_resets_read_cursor(app: App) -> None:
    _scroll_until_top_changes(app)
    app.on_key(":")
    app.on_key("7")
    app.on_key("enter")
    assert app.read_cursors[app.bookmark.slug] == app.study.top_ref
    assert "verses read" not in "\n".join(app.render())


def test_goto_resets_read_cursor(app: App) -> None:
    _scroll_until_top_changes(app)
    app.on_key("g")
    for ch in "1 nephi 3":
        app.on_key(ch)
    app.on_key("enter")
    assert app.read_cursors[app.bookmark.slug] == app.study.top_ref
    assert "verses read" not in "\n".join(app.render())


def test_history_mode_hides_indicator(app: App) -> None:
    moved = _scroll_until_top_changes(app)
    app.on_key("enter")  # commit so history has something to walk to.
    # Re-establish a non-zero count by scrolling forward again.
    _scroll_until_top_changes(app)
    assert "verses read" in "\n".join(app.render())
    app.on_key("left")
    assert app.study.mode == "history"
    rendered = "\n".join(app.render())
    assert "[history]" in rendered
    assert "verses read" not in rendered


def test_history_settle_resets_read_cursor(app: App) -> None:
    moved = _scroll_until_top_changes(app)
    app.on_key("enter")
    _scroll_until_top_changes(app)
    app.on_key("left")  # into history mode, walks back one step.
    settled = app.study.top_ref
    app.on_key("enter")  # settle.
    assert app.read_cursors[app.bookmark.slug] == settled


def test_history_escape_preserves_read_cursor(app: App) -> None:
    cursor_before = app.read_cursors[app.bookmark.slug]
    moved = _scroll_until_top_changes(app)
    app.on_key("enter")  # commit; this resets cursor to `moved`.
    cursor_after_enter = app.read_cursors[app.bookmark.slug]
    assert cursor_after_enter == moved
    _scroll_until_top_changes(app)
    app.on_key("left")  # enter history mode.
    app.on_key("escape")  # cancel.
    # Cursor unchanged by entering+escaping history.
    assert app.read_cursors[app.bookmark.slug] == cursor_after_enter


def test_read_cursor_is_per_bookmark(app: App, db: ScriptureDB) -> None:
    # Advance my-study HEAD first; cursor remains at INITIAL_REF.
    _scroll_until_top_changes(app)
    nephi = _book_id(db, "1 Nephi")
    other_ref = Reference(book_id=nephi, chapter_number=3, verse_number=7)
    # Create Evening AFTER the scroll so Evening sits at the top of the switcher.
    app.journal.create("Evening", other_ref)
    app.on_key("b")
    app.on_key("enter")  # switch to evening (top of switcher).
    assert app.bookmark.slug == "evening"
    # Evening's cursor is initialized to its own HEAD.
    assert app.read_cursors["evening"] == other_ref
    # No "verses read" message in evening yet.
    assert "verses read" not in "\n".join(app.render())
    # my-study's cursor is preserved while we're elsewhere.
    assert app.read_cursors["my-study"] == INITIAL_REF


def test_enter_at_head_still_resets_cursor(app: App) -> None:
    # User is at HEAD with no scrolling; cursor == HEAD. Enter is a dedup'd
    # no-op for history but should still feel like a "settle here" gesture.
    cursor_before = app.read_cursors[app.bookmark.slug]
    app.on_key("enter")
    assert app.read_cursors[app.bookmark.slug] == app.study.top_ref
    assert app.read_cursors[app.bookmark.slug] == cursor_before  # equal here


# help screen


def _help_app(db: ScriptureDB) -> App:
    # Tall enough to render the entire help cheat sheet without truncation.
    return App(
        db=db,
        journal=InMemoryBookmarkJournal(),
        history=InMemoryHistoryJournal(),
        width=80,
        height=60,
    )


def test_question_mark_opens_help_from_study(app: App) -> None:
    app.on_key("?")
    assert app.screen == "help"


def test_help_escape_returns_to_study(app: App) -> None:
    app.on_key("?")
    app.on_key("escape")
    assert app.screen == "study"


def test_question_mark_opens_help_from_switcher(app: App) -> None:
    app.on_key("b")
    assert app.screen == "switcher"
    app.on_key("?")
    assert app.screen == "help"
    app.on_key("escape")
    assert app.screen == "switcher"


def test_help_ignores_random_keys(app: App) -> None:
    app.on_key("?")
    for k in ("q", "g", "b", "x", "enter"):
        app.on_key(k)
        assert app.screen == "help"
    app.on_key("escape")
    assert app.screen == "study"


def test_help_scrolls_when_taller_than_terminal(app: App) -> None:
    # Default fixture is height=20: the help is taller than the body, so
    # j/k/PgDn/PgUp must scroll rather than exit.
    app.on_key("?")
    assert app.help.scroll == 0
    app.on_key("j")
    assert app.help.scroll == 1
    app.on_key("down")
    assert app.help.scroll == 2
    app.on_key("k")
    assert app.help.scroll == 1
    app.on_key("up")
    assert app.help.scroll == 0
    # Cannot scroll above the top.
    app.on_key("k")
    assert app.help.scroll == 0
    # Page jumps move further; clamped at the bottom.
    app.on_key("pagedown")
    assert app.help.scroll > 2
    for _ in range(20):
        app.on_key("pagedown")
    bottom = app.help.scroll
    assert bottom > 0
    app.on_key("pagedown")
    assert app.help.scroll == bottom  # clamped
    app.on_key("pageup")
    assert app.help.scroll < bottom


def test_help_no_scroll_when_fits(db: ScriptureDB) -> None:
    # On a tall terminal the whole help fits — footer should not advertise
    # scroll keys, and j/k should be inert.
    app = _help_app(db)
    app.on_key("?")
    rendered = "\n".join(app.render())
    assert "j/k scroll" not in rendered
    app.on_key("j")
    assert app.help.scroll == 0


def test_help_scroll_resets_per_open(app: App) -> None:
    # Scroll, exit, reopen: should be back at the top so the user always lands
    # on the first section.
    app.on_key("?")
    app.on_key("pagedown")
    assert app.help.scroll > 0
    app.on_key("escape")
    app.on_key("?")
    assert app.help.scroll == 0


def test_help_footer_shows_position_when_scrollable(app: App) -> None:
    app.on_key("?")
    rendered = "\n".join(app.render())
    assert "j/k scroll" in rendered
    assert " of " in rendered  # position indicator like "1–17 of 39"


def test_help_lists_bindings_from_every_mode(db: ScriptureDB) -> None:
    # The help is a dumb, exhaustive cheat sheet — it should mention every
    # mode/dialog regardless of which one is currently active.
    app = _help_app(db)
    app.on_key("?")
    rendered = "\n".join(app.render())
    for section in (
        "Study",
        "Verse jump",
        "History walk",
        "Goto chapter",
        "Bookmarks",
        "New bookmark",
    ):
        assert section in rendered, f"help missing section: {section}"


def test_help_uses_h_and_l_letters(db: ScriptureDB) -> None:
    app = _help_app(db)
    app.on_key("?")
    rendered = "\n".join(app.render())
    # Vim-style letters should be visible as discrete tokens; arrows are only
    # mentioned as a secondary aid.
    assert " h " in rendered
    assert " l " in rendered
    assert " j " in rendered
    assert " k " in rendered


def test_help_documents_shift_jk_chapter_jumps(db: ScriptureDB) -> None:
    app = _help_app(db)
    app.on_key("?")
    rendered = "\n".join(app.render())
    assert "next chapter" in rendered
    assert "previous chapter" in rendered
    assert " J " in rendered
    assert " K " in rendered


def test_help_does_not_open_during_delete_confirm(app: App) -> None:
    # Two bookmarks so delete is allowed.
    app.journal.create("Evening", Reference(book_id=1, chapter_number=2, verse_number=1))
    app.on_key("b")
    app.on_key("d")
    assert app.switcher.confirming_delete is True
    app.on_key("?")
    # ? is not a y/n answer, and the delete prompt is the only thing the user
    # should be looking at — stay in switcher with the prompt up.
    assert app.screen == "switcher"
    assert app.switcher.confirming_delete is True


def test_help_does_not_open_in_verse_jump(app: App) -> None:
    app.on_key(":")
    assert app.study.mode == "verse-jump"
    app.on_key("?")
    # ? is not a digit and not a control key — verse jump just ignores it.
    assert app.screen == "study"
    assert app.study.mode == "verse-jump"


def test_help_does_not_open_from_goto_query(app: App) -> None:
    app.on_key("g")
    app.on_key("?")
    # ? is a literal printable char in the goto query, not a help shortcut.
    assert app.screen == "goto"
    assert app.goto.query == "?"


def test_help_does_not_open_from_newbookmark_input(app: App) -> None:
    app.on_key("b")
    app.on_key("c")
    assert app.screen == "newbookmark"
    app.on_key("?")
    assert app.screen == "newbookmark"
    assert app.newbookmark.name_buf == "?"


def test_study_footer_documents_help(app: App) -> None:
    rendered = "\n".join(app.render())
    assert "? help" in rendered


def test_switcher_footer_documents_help(app: App) -> None:
    app.on_key("b")
    rendered = "\n".join(app.render())
    assert "? help" in rendered


# disk integration: same flow with real BookmarkJournal

def test_disk_journal_persists_after_navigation(tmp_path, db: ScriptureDB) -> None:
    journal = BookmarkJournal(path=tmp_path / "bookmarks.jsonl")
    history = HistoryJournal(path=tmp_path / "history.jsonl")
    app = App(db=db, journal=journal, history=history, width=80, height=20)
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    new_top = app.study.top_ref
    # Reopen with a fresh App and verify it lands where we left off.
    journal2 = BookmarkJournal(path=tmp_path / "bookmarks.jsonl")
    history2 = HistoryJournal(path=tmp_path / "history.jsonl")
    app2 = App(db=db, journal=journal2, history=history2, width=80, height=20)
    assert app2.bookmark.slug == "my-study"
    assert app2.bookmark.reference == new_top
    assert app2.study.top_ref == new_top
