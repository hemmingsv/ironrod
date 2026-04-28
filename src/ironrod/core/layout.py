"""Line-level viewport over the canon.

The study screen scrolls one terminal line at a time. The bookmark stores the
verse owning the **top line on screen**. This module turns a (top reference,
line offset within that verse) cursor into renderable lines, and provides
``scroll_down`` / ``scroll_up`` that advance the cursor by exactly one line.

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
