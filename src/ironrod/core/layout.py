"""Line-level viewport over the canon.

The study screen scrolls one terminal line at a time. The bookmark stores the
verse owning the **top line on screen**. This module turns a (top reference,
line offset within that verse) cursor into renderable lines, and provides:

* ``scroll_down`` / ``scroll_up`` — advance the cursor by exactly one line.
* ``page_down`` / ``page_up`` — move the cursor by a screenful at a time,
  snapping to verse boundaries so chapter headers and partial verses don't
  drift across the seam between consecutive pages.

The functions are pure: callers inject

* ``next_ref`` / ``prev_ref`` — closures that wrap the navigation index.
* ``verse_text`` — closure returning the raw text of a Reference.
* ``book_title`` — closure returning the long title of a book id (for chapter
  headers).

This means tests can drive the layout with synthetic data without touching
sqlite.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from ironrod.models import Reference
from ironrod.utils.wrap import wrap_verse

LineKind = Literal["verse", "header"]
HEADER_PREFIX = "── "
HEADER_SUFFIX = " ──"


@dataclass(frozen=True)
class LayoutLine:
    """One rendered line of the viewport.

    ``reference`` is the verse that "owns" this line — for both verse lines
    (the verse being rendered) and the header that introduces a chapter
    (its first verse). The bookmark uses the reference of the topmost line.
    """

    kind: LineKind
    reference: Reference
    content: str


NextRef = Callable[[Reference], Reference | None]
PrevRef = Callable[[Reference], Reference | None]
VerseText = Callable[[Reference], str]
BookTitle = Callable[[int], str]


def render_verse_lines(
    ref: Reference,
    *,
    width: int,
    verse_text: VerseText,
) -> list[LayoutLine]:
    """All terminal lines making up a single verse, in order."""
    text = verse_text(ref)
    return [
        LayoutLine(kind="verse", reference=ref, content=line)
        for line in wrap_verse(ref.verse_number, text, width)
    ]


def chapter_header_line(ref: Reference, *, book_title: BookTitle) -> LayoutLine:
    """The ``── 1 Nephi 4 ──`` separator inserted between chapters."""
    title = book_title(ref.book_id)
    content = f"{HEADER_PREFIX}{title} {ref.chapter_number}{HEADER_SUFFIX}"
    return LayoutLine(kind="header", reference=ref, content=content)


def lay_out(
    top_ref: Reference,
    top_line_offset: int,
    *,
    lines_needed: int,
    width: int,
    next_ref: NextRef,
    verse_text: VerseText,
    book_title: BookTitle,
) -> list[LayoutLine]:
    """Render ``lines_needed`` lines starting at the given cursor.

    ``top_line_offset`` selects which line within ``top_ref`` is at the top;
    ``0`` means the verse-number line, ``1+`` means a continuation line.
    Stops early if the canon ends.
    """
    if top_line_offset < 0:
        raise ValueError("top_line_offset must be >= 0")
    if lines_needed <= 0:
        return []

    out: list[LayoutLine] = []
    cur = top_ref
    while cur is not None and len(out) < lines_needed:
        verse_lines = render_verse_lines(cur, width=width, verse_text=verse_text)
        if cur == top_ref:
            if top_line_offset >= len(verse_lines):
                raise ValueError(
                    f"top_line_offset {top_line_offset} out of range for "
                    f"verse with {len(verse_lines)} lines"
                )
            verse_lines = verse_lines[top_line_offset:]
        out.extend(verse_lines[: lines_needed - len(out)])
        if len(out) >= lines_needed:
            break
        nxt = next_ref(cur)
        if nxt is None:
            break
        # Insert a chapter header when crossing into a new chapter.
        if nxt.chapter_number != cur.chapter_number or nxt.book_id != cur.book_id:
            header = chapter_header_line(nxt, book_title=book_title)
            out.append(header)
            if len(out) >= lines_needed:
                break
        cur = nxt
    return out


def _verse_line_count(ref: Reference, *, width: int, verse_text: VerseText) -> int:
    return len(render_verse_lines(ref, width=width, verse_text=verse_text))


def scroll_down(
    top_ref: Reference,
    top_line_offset: int,
    *,
    width: int,
    next_ref: NextRef,
    verse_text: VerseText,
) -> tuple[Reference, int] | None:
    """Advance the cursor by one line. Returns ``None`` at canon end.

    Skips chapter-header lines: the header sits between the last line of one
    verse and the first line of the next, but the cursor itself never lands on
    a header (the header is always rendered above its chapter's first verse).
    """
    line_count = _verse_line_count(top_ref, width=width, verse_text=verse_text)
    if top_line_offset + 1 < line_count:
        return (top_ref, top_line_offset + 1)
    nxt = next_ref(top_ref)
    if nxt is None:
        return None
    return (nxt, 0)


def scroll_up(
    top_ref: Reference,
    top_line_offset: int,
    *,
    width: int,
    prev_ref: PrevRef,
    verse_text: VerseText,
) -> tuple[Reference, int] | None:
    """Move the cursor up one line. Returns ``None`` at the canon start."""
    if top_line_offset > 0:
        return (top_ref, top_line_offset - 1)
    prv = prev_ref(top_ref)
    if prv is None:
        return None
    last_line = _verse_line_count(prv, width=width, verse_text=verse_text) - 1
    return (prv, last_line)


def _walk_back_render_lines(
    top_ref: Reference,
    top_line_offset: int,
    n: int,
    *,
    width: int,
    prev_ref: PrevRef,
    verse_text: VerseText,
) -> tuple[Reference, int] | None:
    """Walk back ``n`` rendered lines from a verse cursor.

    Counts chapter-header lines (which ``lay_out`` inserts between chapters)
    as render lines, so the result lines up with what ``lay_out`` will emit
    when it runs forward from the returned cursor.

    Returns ``None`` if no movement is possible.

    If the walk would land on a header line — which has no verse cursor —
    snaps to the verse just below the header (the chapter's first verse).
    The header then sits one row above the viewport rather than inside it,
    nudging downstream content up by one row, but it never makes the target
    verse fall off the bottom.
    """
    cursor = (top_ref, top_line_offset)
    on_header = False
    moved = 0
    while moved < n:
        if on_header:
            # The line above a header is the previous chapter's last verse.
            prv = prev_ref(cursor[0])
            if prv is None:
                break
            last_line = _verse_line_count(prv, width=width, verse_text=verse_text) - 1
            cursor = (prv, last_line)
            on_header = False
            moved += 1
            continue
        if cursor[1] > 0:
            cursor = (cursor[0], cursor[1] - 1)
            moved += 1
            continue
        prv = prev_ref(cursor[0])
        if prv is None:
            break
        if (prv.chapter_number != cursor[0].chapter_number
                or prv.book_id != cursor[0].book_id):
            # The line above this verse's first line is the chapter header.
            on_header = True
            moved += 1
            continue
        last_line = _verse_line_count(prv, width=width, verse_text=verse_text) - 1
        cursor = (prv, last_line)
        moved += 1
    if moved == 0:
        return None
    return cursor


def page_down(
    top_ref: Reference,
    top_line_offset: int,
    *,
    body_height: int,
    width: int,
    next_ref: NextRef,
    verse_text: VerseText,
    book_title: BookTitle,
) -> tuple[Reference, int] | None:
    """Page-scroll down: align to the last verse whose start is on screen.

    The new top is the bottom-most verse whose first line was visible in the
    current viewport, with offset 0. If only the current top verse's start is
    visible (e.g. one giant verse fills the screen), advances to the next
    verse so PgDn always makes forward progress. Returns ``None`` at canon
    end.
    """
    body = lay_out(
        top_ref, top_line_offset,
        lines_needed=body_height, width=width,
        next_ref=next_ref, verse_text=verse_text, book_title=book_title,
    )
    starts: list[Reference] = []
    seen: set[Reference] = set()
    for line in body:
        if line.kind != "verse":
            continue
        if line.reference in seen:
            continue
        seen.add(line.reference)
        # When ``top_line_offset > 0`` the first viewport line of ``top_ref``
        # is a continuation; the verse's start sits above the viewport.
        if line.reference == top_ref and top_line_offset > 0:
            continue
        starts.append(line.reference)
    candidate = starts[-1] if starts else None
    if candidate is None or (candidate == top_ref and top_line_offset == 0):
        nxt = next_ref(top_ref)
        if nxt is None:
            return None
        return (nxt, 0)
    return (candidate, 0)


def page_up(
    top_ref: Reference,
    top_line_offset: int,
    *,
    body_height: int,
    width: int,
    next_ref: NextRef,
    prev_ref: PrevRef,
    verse_text: VerseText,
    book_title: BookTitle,
) -> tuple[Reference, int] | None:
    """Page-scroll up: place the first verse whose end is on screen fully at
    the bottom of the new viewport.

    Returns ``None`` at canon start, or when the natural alignment would not
    move the cursor and there's nothing earlier to fall back to.
    """
    body = lay_out(
        top_ref, top_line_offset,
        lines_needed=body_height, width=width,
        next_ref=next_ref, verse_text=verse_text, book_title=book_title,
    )
    refs_in_order: list[Reference] = []
    line_counts: dict[Reference, int] = {}
    for line in body:
        if line.kind != "verse":
            continue
        if line.reference not in line_counts:
            refs_in_order.append(line.reference)
            line_counts[line.reference] = 0
        line_counts[line.reference] += 1

    target: Reference | None = None
    for ref in refs_in_order:
        full = _verse_line_count(ref, width=width, verse_text=verse_text)
        expected = full - top_line_offset if ref == top_ref else full
        if line_counts[ref] >= expected:
            target = ref
            break

    if target is not None:
        target_lines = _verse_line_count(target, width=width, verse_text=verse_text)
        # Walk back ``body_height - 1`` *render* lines so the target's last
        # line lands at the bottom row of the new viewport. ``lay_out`` will
        # insert a header row at every chapter boundary it crosses; if we
        # only counted verse lines here, those extra header rows would shove
        # the target past the bottom and out of sight.
        new_top = _walk_back_render_lines(
            target, target_lines - 1, body_height - 1,
            width=width, prev_ref=prev_ref, verse_text=verse_text,
        )
        if new_top is not None and new_top != (top_ref, top_line_offset):
            return new_top

    # Either no verse end was visible (the whole viewport was mid-verse) or
    # the chosen target is too tall to fit, so positioning it at the bottom
    # would not move us. Walk back one viewport's worth of lines instead.
    return _walk_back_render_lines(
        top_ref, top_line_offset, max(1, body_height - 1),
        width=width, prev_ref=prev_ref, verse_text=verse_text,
    )
