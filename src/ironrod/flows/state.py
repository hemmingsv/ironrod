"""Pure state machine for the ironrod TUI.

Owns the application state and the transitions between screens. Renders the
visible buffer as a list of strings; takes input as a high-level key name.
The prompt_toolkit wrapper in ``flows/app.py`` is a thin translation layer.

Keeping this module free of prompt_toolkit makes it cheap to test: drive the
state machine by calling ``on_key()`` and assert on the journal, the cursor,
and ``render()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from ironrod.clients.bookmarks import (
    BookmarkExists,
    BookmarkNotFound,
    CannotDeleteLast,
)
from ironrod.clients.scriptures import ScriptureDB
from ironrod.core.fuzzy import score
from ironrod.core.layout import lay_out, scroll_down, scroll_up
from ironrod.models import Bookmark, ChapterEntry, HistoryRecord, Reference

DEFAULT_NAME = "my-study"
INITIAL_REF = Reference(book_id=1, chapter_number=1, verse_number=1)
HEADER_LINES = 1
FOOTER_LINES = 2
CHROME_LINES = HEADER_LINES + FOOTER_LINES


Mode = Literal["normal", "verse-jump", "history"]
Screen = Literal["study", "goto", "switcher", "newbookmark"]


class JournalProto(Protocol):
    def load(self) -> list[Bookmark]: ...
    def top(self) -> Bookmark | None: ...
    def get(self, slug: str) -> Bookmark: ...
    def create(self, name: str, reference: Reference) -> Bookmark: ...
    def touch(self, slug: str, reference: Reference | None = None) -> Bookmark: ...
    def delete(self, slug: str) -> None: ...


class HistoryProto(Protocol):
    def load(self) -> list[HistoryRecord]: ...
    def load_for(self, slug: str) -> list[HistoryRecord]: ...
    def append(self, slug: str, reference: Reference) -> bool: ...


@dataclass
class StudyState:
    top_ref: Reference
    top_line_offset: int = 0
    mode: Mode = "normal"
    verse_jump_buf: str = ""
    # Snapshot of the bookmark's history captured on entering history mode.
    # ``None`` iff ``mode != "history"``. Snapshotting (rather than re-reading
    # on each step) keeps the index stable if anything else appends mid-walk.
    history_view: list[HistoryRecord] | None = None
    history_index: int = 0


@dataclass
class GotoState:
    query: str = ""
    selected: int = 0


@dataclass
class SwitcherState:
    selected: int = 0
    confirming_delete: bool = False


@dataclass
class NewBookmarkState:
    name_buf: str = ""
    error: str | None = None


@dataclass
class App:
    db: ScriptureDB
    journal: JournalProto
    history: HistoryProto

    width: int = 80
    height: int = 24

    bookmark: Bookmark = field(init=False)
    screen: Screen = field(init=False, default="study")
    study: StudyState = field(init=False)
    goto: GotoState = field(init=False, default_factory=GotoState)
    switcher: SwitcherState = field(init=False, default_factory=SwitcherState)
    newbookmark: NewBookmarkState = field(init=False, default_factory=NewBookmarkState)
    flash: str | None = None
    quitting: bool = False

    def __post_init__(self) -> None:
        existing = self.journal.top()
        if existing is None:
            self.bookmark = self.journal.create(DEFAULT_NAME, INITIAL_REF)
            self.history.append(self.bookmark.slug, self.bookmark.reference)
        else:
            self.bookmark = existing
        self.study = StudyState(top_ref=self.bookmark.reference, top_line_offset=0)

    # rendering helpers

    @property
    def body_height(self) -> int:
        return max(1, self.height - CHROME_LINES)

    def _verse_text(self, ref: Reference) -> str:
        return self.db.verse(ref).text

    def _book_title(self, book_id: int) -> str:
        return self.db.book_by_id(book_id).title

    def _book_short_title(self, book_id: int) -> str:
        return self.db.book_by_id(book_id).short_title

    def _ref_label(self, ref: Reference) -> str:
        book = self.db.book_by_id(ref.book_id)
        return f"{book.short_title} {ref.chapter_number}:{ref.verse_number}"

    def _ref_long_label(self, ref: Reference) -> str:
        book = self.db.book_by_id(ref.book_id)
        return f"{book.title} {ref.chapter_number}:{ref.verse_number}"

    # screen rendering — returns a list of exactly ``self.height`` lines.

    def render(self) -> list[str]:
        if self.screen == "study":
            return self._render_study()
        if self.screen == "goto":
            return self._render_goto()
        if self.screen == "switcher":
            return self._render_switcher()
        if self.screen == "newbookmark":
            return self._render_newbookmark()
        raise AssertionError(f"unknown screen {self.screen!r}")

    def _pad_to_height(self, lines: list[str]) -> list[str]:
        if len(lines) > self.height:
            return lines[: self.height]
        return lines + [""] * (self.height - len(lines))

    def _render_study(self) -> list[str]:
        suffix = " [history]" if self.study.mode == "history" else ""
        header = (
            f"{self.bookmark.name}{suffix} — "
            f"{self._ref_long_label(self.study.top_ref)}"
        )
        body = lay_out(
            self.study.top_ref,
            self.study.top_line_offset,
            lines_needed=self.body_height,
            width=self.width,
            next_ref=self.db.next_reference,
            verse_text=self._verse_text,
            book_title=self._book_title,
        )
        body_lines = [line.content for line in body]
        if len(body_lines) < self.body_height:
            body_lines += [""] * (self.body_height - len(body_lines))
        sep = "─" * self.width
        if self.study.mode == "verse-jump":
            footer = f":{self.study.verse_jump_buf}_   (Enter to jump, Esc to cancel)"
        elif self.study.mode == "history" and self.study.history_view is not None:
            total = len(self.study.history_view)
            pos = self.study.history_index + 1
            footer = f"← {pos}/{total} →   Enter settle  Esc cancel"
        else:
            footer = (
                "j/↓ down  k/↑ prev  ←/→ history  : verse  "
                "g goto  b bookmarks  q quit"
            )
        if self.flash:
            footer = f"{self.flash}"
        return self._pad_to_height([header, *body_lines, sep, footer])

    def _filtered_chapters(self) -> list[tuple[ChapterEntry, object]]:
        index = self.db.chapter_index()
        scored: list[tuple[ChapterEntry, object]] = []
        for entry in index:
            s = score(self.goto.query, entry.label)
            if s is not None:
                scored.append((entry, s))
        scored.sort(key=lambda t: (t[1], t[0].book_id, t[0].chapter_number))  # type: ignore[arg-type]
        return scored

    def _render_goto(self) -> list[str]:
        header = f"Goto chapter — type to filter, Enter to jump, Esc to cancel"
        prompt = f"  > {self.goto.query}_"
        scored = self._filtered_chapters()
        list_lines: list[str] = []
        list_height = self.body_height - 1  # one line for prompt
        for i, (entry, _) in enumerate(scored[: list_height]):
            cursor = ">" if i == self.goto.selected else " "
            list_lines.append(f"  {cursor} {entry.label}")
        if not scored:
            list_lines = ["  (no matches)"]
        body = [prompt, *list_lines]
        if len(body) < self.body_height:
            body += [""] * (self.body_height - len(body))
        sep = "─" * self.width
        footer = "↑/↓ select  Enter jump  Esc cancel"
        return self._pad_to_height([header, *body, sep, footer])

    def _render_switcher(self) -> list[str]:
        header = "Bookmarks (most recent first)"
        bookmarks = self.journal.load()
        list_lines: list[str] = []
        for i, bm in enumerate(bookmarks[: self.body_height]):
            cursor = ">" if i == self.switcher.selected else " "
            location = self._ref_label(bm.reference)
            # Pad name into a fixed column for alignment.
            namecol = bm.name[:24].ljust(24)
            list_lines.append(f"  {cursor} {namecol}  {location}")
        if not bookmarks:
            list_lines = ["  (no bookmarks — press n to create)"]
        if len(list_lines) < self.body_height:
            list_lines += [""] * (self.body_height - len(list_lines))
        sep = "─" * self.width
        if self.switcher.confirming_delete:
            footer = "Delete this bookmark? (y/n)"
        else:
            footer = "Enter switch  n new  d delete  Esc back"
        return self._pad_to_height([header, *list_lines, sep, footer])

    def _render_newbookmark(self) -> list[str]:
        header = "New bookmark — type a name, Enter to create, Esc to cancel"
        prompt = f"  Name: {self.newbookmark.name_buf}_"
        body = [prompt]
        if self.newbookmark.error:
            body.append(f"  ! {self.newbookmark.error}")
        if len(body) < self.body_height:
            body += [""] * (self.body_height - len(body))
        sep = "─" * self.width
        footer = "Enter create  Esc cancel"
        return self._pad_to_height([header, *body, sep, footer])

    # input dispatch

    def on_key(self, key: str) -> None:
        """Handle a high-level key name. ``key`` is ``"j"``, ``"down"``,
        ``"enter"``, ``"escape"``, ``"backspace"``, or any literal printable
        character (e.g. ``" "``, ``"a"``, ``"3"``).
        """
        self.flash = None
        if self.screen == "study":
            self._on_key_study(key)
        elif self.screen == "goto":
            self._on_key_goto(key)
        elif self.screen == "switcher":
            self._on_key_switcher(key)
        elif self.screen == "newbookmark":
            self._on_key_newbookmark(key)

    # study handlers

    def _on_key_study(self, key: str) -> None:
        if self.study.mode == "verse-jump":
            self._on_key_study_verse_jump(key)
            return
        if self.study.mode == "history":
            self._on_key_study_history(key)
            return
        # normal mode
        if key in ("j", "down"):
            self._scroll_down_one()
        elif key in ("k", "up"):
            self._scroll_up_one()
        elif key in ("left", "h"):
            self._enter_history_mode()
        elif key in ("right", "l"):
            # No-op: there is nothing forward of the newest record.
            return
        elif key == "enter":
            # Append current HEAD to history (deduped). Implemented as enter +
            # immediate exit of history mode so commit-on-transition remains
            # the single primitive — no other side-effects.
            self._commit_history()
        elif key == "g":
            self.screen = "goto"
            self.goto = GotoState()
        elif key == "b":
            self.screen = "switcher"
            self.switcher = SwitcherState()
        elif key == "q":
            self.quitting = True
        elif key == ":":
            self.study.mode = "verse-jump"
            self.study.verse_jump_buf = ""

    # History mode

    def _commit_history(self, ref: Reference | None = None) -> bool:
        """Append the given (or current HEAD) reference to the bookmark's
        history. Returns True if a new record was actually written, False if
        deduplicated against the most recent existing record.
        """
        target = ref if ref is not None else self.study.top_ref
        return self.history.append(self.bookmark.slug, target)

    def _enter_history_mode(self) -> None:
        """Commit current HEAD, snapshot history, step back by one."""
        self._commit_history()
        snapshot = self.history.load_for(self.bookmark.slug)
        if len(snapshot) < 2:
            self.flash = "no earlier history"
            return
        self.study.history_view = snapshot
        self.study.history_index = len(snapshot) - 2
        self._set_top(snapshot[self.study.history_index].reference)
        self.study.mode = "history"

    def _exit_history_mode(self, *, commit: bool) -> None:
        if commit:
            self._commit_history()
        self.study.mode = "normal"
        self.study.history_view = None
        self.study.history_index = 0

    def _on_key_study_history(self, key: str) -> None:
        view = self.study.history_view
        if view is None:  # pragma: no cover — invariant
            self.study.mode = "normal"
            return
        if key in ("left", "h"):
            self.study.history_index = max(0, self.study.history_index - 1)
            self._set_top(view[self.study.history_index].reference)
            return
        if key in ("right", "l"):
            self.study.history_index = min(len(view) - 1, self.study.history_index + 1)
            self._set_top(view[self.study.history_index].reference)
            return
        if key == "enter":
            self._exit_history_mode(commit=True)
            return
        if key == "escape":
            self._exit_history_mode(commit=False)
            return
        # Any other key: leave history mode (committing the walked-to position),
        # then fall through to normal study handling so the keystroke still does
        # what the user expects (scroll, open goto, etc.).
        self._exit_history_mode(commit=True)
        self._on_key_study(key)

    def _on_key_study_verse_jump(self, key: str) -> None:
        if key == "escape":
            self.study.mode = "normal"
            self.study.verse_jump_buf = ""
            return
        if key == "backspace":
            self.study.verse_jump_buf = self.study.verse_jump_buf[:-1]
            return
        if key == "enter":
            buf = self.study.verse_jump_buf
            self.study.mode = "normal"
            self.study.verse_jump_buf = ""
            if not buf.isdigit():
                return
            verse_num = int(buf)
            ch = self.study.top_ref.chapter_number
            book_id = self.study.top_ref.book_id
            if 1 <= verse_num <= self.db.verse_count(book_id, ch):
                new_ref = Reference(
                    book_id=book_id,
                    chapter_number=ch,
                    verse_number=verse_num,
                )
                # Commit source HEAD (where the user is now), then jump and
                # commit the destination too.
                self._commit_history()
                self._set_top(new_ref)
                self._commit_history(new_ref)
            else:
                self.flash = f"verse {verse_num} not in {self._ref_long_label(self.study.top_ref).rsplit(':', 1)[0]}"
            return
        if len(key) == 1 and key.isdigit():
            self.study.verse_jump_buf += key

    def _scroll_down_one(self) -> None:
        result = scroll_down(
            self.study.top_ref,
            self.study.top_line_offset,
            width=self.width,
            next_ref=self.db.next_reference,
            verse_text=self._verse_text,
        )
        if result is None:
            return
        new_top, new_offset = result
        if new_top != self.study.top_ref:
            self._set_top_with_offset(new_top, new_offset)
        else:
            self.study.top_line_offset = new_offset

    def _scroll_up_one(self) -> None:
        result = scroll_up(
            self.study.top_ref,
            self.study.top_line_offset,
            width=self.width,
            prev_ref=self.db.prev_reference,
            verse_text=self._verse_text,
        )
        if result is None:
            return
        new_top, new_offset = result
        if new_top != self.study.top_ref:
            self._set_top_with_offset(new_top, new_offset)
        else:
            self.study.top_line_offset = new_offset

    def _set_top(self, ref: Reference) -> None:
        """Set top_ref to a new verse with offset 0. Persists to journal."""
        self._set_top_with_offset(ref, 0)

    def _set_top_with_offset(self, ref: Reference, offset: int) -> None:
        self.study.top_ref = ref
        self.study.top_line_offset = offset
        # Persist only the verse, not the offset.
        self.bookmark = self.journal.touch(self.bookmark.slug, ref)

    # goto handlers

    def _on_key_goto(self, key: str) -> None:
        if key == "escape":
            self.screen = "study"
            return
        if key == "enter":
            scored = self._filtered_chapters()
            if not scored:
                return
            entry = scored[self.goto.selected][0]
            target = Reference(
                book_id=entry.book_id,
                chapter_number=entry.chapter_number,
                verse_number=1,
            )
            self.screen = "study"
            # Commit source HEAD before jumping, then the destination.
            self._commit_history()
            self._set_top(target)
            self._commit_history(target)
            return
        if key in ("up",):
            self.goto.selected = max(0, self.goto.selected - 1)
            return
        if key in ("down",):
            scored = self._filtered_chapters()
            limit = max(0, len(scored) - 1)
            self.goto.selected = min(limit, self.goto.selected + 1)
            return
        if key == "backspace":
            self.goto.query = self.goto.query[:-1]
            self.goto.selected = 0
            return
        if len(key) == 1 and key.isprintable():
            self.goto.query += key
            self.goto.selected = 0

    # switcher handlers

    def _on_key_switcher(self, key: str) -> None:
        bookmarks = self.journal.load()
        if self.switcher.confirming_delete:
            if key == "y":
                if not bookmarks:
                    self.switcher.confirming_delete = False
                    return
                target = bookmarks[self.switcher.selected]
                try:
                    self.journal.delete(target.slug)
                except CannotDeleteLast:
                    self.flash = "cannot delete the last bookmark"
                self.switcher.confirming_delete = False
                self.switcher.selected = 0
            elif key in ("n", "escape"):
                self.switcher.confirming_delete = False
            return
        if key == "escape":
            self.screen = "study"
            return
        if key == "n":
            self.screen = "newbookmark"
            self.newbookmark = NewBookmarkState()
            return
        if key == "d":
            if bookmarks:
                self.switcher.confirming_delete = True
            return
        if key == "up":
            self.switcher.selected = max(0, self.switcher.selected - 1)
            return
        if key == "down":
            self.switcher.selected = min(max(0, len(bookmarks) - 1), self.switcher.selected + 1)
            return
        if key == "enter":
            if not bookmarks:
                return
            target = bookmarks[self.switcher.selected]
            self.bookmark = self.journal.touch(target.slug)
            self.study = StudyState(top_ref=self.bookmark.reference)
            self.screen = "study"

    # newbookmark handlers

    def _on_key_newbookmark(self, key: str) -> None:
        if key == "escape":
            self.screen = "switcher"
            return
        if key == "backspace":
            self.newbookmark.name_buf = self.newbookmark.name_buf[:-1]
            self.newbookmark.error = None
            return
        if key == "enter":
            name = self.newbookmark.name_buf.strip()
            if not name:
                self.newbookmark.error = "name cannot be empty"
                return
            try:
                bm = self.journal.create(name, INITIAL_REF)
            except BookmarkExists:
                self.newbookmark.error = "a bookmark with that name already exists"
                return
            except ValueError as e:
                self.newbookmark.error = str(e)
                return
            self.bookmark = bm
            self.study = StudyState(top_ref=bm.reference)
            self.screen = "study"
            # Seed the new bookmark's history with its initial position so that
            # ←/→ have something to walk to from day one.
            self.history.append(bm.slug, bm.reference)
            return
        if len(key) == 1 and key.isprintable():
            self.newbookmark.name_buf += key
            self.newbookmark.error = None
