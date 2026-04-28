"""Pytest edge cases for slugify (in addition to the doctests in slug.py)."""

import pytest

from ironrod.utils.slug import MAX_LEN, slugify


def test_basic() -> None:
    assert slugify("Daily Study") == "daily-study"


def test_already_slug_is_idempotent() -> None:
    assert slugify("daily-study") == "daily-study"
    assert slugify(slugify("Daily Study")) == "daily-study"


def test_strips_punctuation_runs() -> None:
    assert slugify("Hello---World") == "hello-world"
    assert slugify("a!!b??c") == "a-b-c"


def test_unicode_folding() -> None:
    assert slugify("Mörgenstudie") == "morgenstudie"
    assert slugify("naïve") == "naive"


def test_numbers_preserved() -> None:
    assert slugify("1 Nephi 3:7") == "1-nephi-3-7"


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError):
        slugify("")


def test_all_punctuation_raises() -> None:
    with pytest.raises(ValueError):
        slugify("!!!")
    with pytest.raises(ValueError):
        slugify("---")


def test_length_cap_and_trailing_dash_strip() -> None:
    long = "a" * (MAX_LEN + 20)
    assert len(slugify(long)) == MAX_LEN
    # If the cap lands on a dash, it should still be trimmed.
    s = slugify("a" + "!" * MAX_LEN + "b")
    assert not s.endswith("-")


def test_leading_trailing_whitespace() -> None:
    assert slugify("   morning  ") == "morning"
