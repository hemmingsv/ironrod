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
* ``n`` from the switcher creates a new bookmark at Gen 1:1
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
    app.on_key("n")
    assert app.screen == "newbookmark"
    for ch in "evening":
        app.on_key(ch)
    app.on_key("enter")
    assert app.screen == "study"
    assert app.bookmark.slug == "evening"
    assert app.bookmark.reference == INITIAL_REF


def test_switcher_new_empty_name_shows_error(app: App) -> None:
    app.on_key("b")
    app.on_key("n")
    app.on_key("enter")
    assert app.screen == "newbookmark"
    assert app.newbookmark.error == "name cannot be empty"


def test_switcher_new_duplicate_name_shows_error(app: App) -> None:
    app.on_key("b")
    app.on_key("n")
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


def test_escape_in_history_mode_exits_without_committing(app: App) -> None:
    initial = app.study.top_ref
    for _ in range(60):
        app.on_key("j")
        if app.study.top_ref != initial:
            break
    a = app.study.top_ref
    app.on_key("enter")
    app.on_key("left")
    assert app.study.mode == "history"
    before = list(_refs(app))
    app.on_key("escape")
    assert app.study.mode == "normal"
    assert _refs(app) == before  # no commit


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
    app.on_key("n")
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
    app.on_key("n")
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
