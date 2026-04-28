"""Wrap verse text into terminal-width lines with a verse-number prefix."""

import textwrap

PREFIX_WIDTH = 4  # "  7 " — two-space pad, up to 2-digit number, one space
CONTINUATION_INDENT = " " * PREFIX_WIDTH


def wrap_verse(verse_number: int, text: str, width: int) -> list[str]:
    """Wrap ``text`` to ``width`` columns, prefixed by the verse number.

    The first line gets a right-aligned verse number; continuation lines are
    indented by the same number of columns so the body aligns visually.

    ``width`` must be greater than the prefix indent. If ``width`` is too narrow
    to fit any word, the text falls back to break-on-hyphens / break-long-words
    behaviour from ``textwrap``.

    >>> wrap_verse(1, "In the beginning God created the heaven and the earth.", 30)
    ['  1 In the beginning God', '    created the heaven and the', '    earth.']
    >>> wrap_verse(7, "And it came to pass.", 80)
    ['  7 And it came to pass.']
    """
    if width <= PREFIX_WIDTH:
        raise ValueError(f"width must be > {PREFIX_WIDTH}, got {width}")
    prefix = f"{verse_number:>3} "  # "  1 ", " 12 ", "100 "
    body_width = width - PREFIX_WIDTH
    chunks = textwrap.wrap(
        text,
        width=body_width,
        break_long_words=True,
        break_on_hyphens=True,
    ) or [""]
    out = [prefix + chunks[0]]
    out.extend(CONTINUATION_INDENT + chunk for chunk in chunks[1:])
    return out
