"""Tests for utils.wrap."""

import pytest

from ironrod.utils.wrap import CONTINUATION_INDENT, PREFIX_WIDTH, wrap_verse


def test_short_verse_fits_on_one_line() -> None:
    out = wrap_verse(7, "And it came to pass.", 80)
    assert out == ["  7 And it came to pass."]


def test_wraps_long_verse() -> None:
    text = "In the beginning God created the heaven and the earth."
    out = wrap_verse(1, text, 30)
    assert out[0].startswith("  1 ")
    for line in out[1:]:
        assert line.startswith(CONTINUATION_INDENT)
    # Reassembling the body (without prefix) should equal the original words.
    body = " ".join(line[PREFIX_WIDTH:] for line in out)
    assert " ".join(body.split()) == text


def test_three_digit_verse_prefix() -> None:
    out = wrap_verse(176, "Test.", 80)
    assert out[0].startswith("176 ")


def test_width_too_narrow_raises() -> None:
    with pytest.raises(ValueError):
        wrap_verse(1, "anything", PREFIX_WIDTH)


def test_no_wrapping_when_width_is_huge() -> None:
    text = "a b c d e f"
    assert wrap_verse(1, text, 1000) == ["  1 a b c d e f"]


def test_empty_text_returns_prefix_only() -> None:
    out = wrap_verse(1, "", 40)
    assert out == ["  1 "]
