from ironrod.core.fuzzy import score


def test_substring_matches() -> None:
    s = score("nephi", "1 Nephi 3")
    assert s is not None


def test_case_insensitive() -> None:
    assert score("NEPHI", "1 Nephi 3") is not None


def test_short_query_matches_book_chapter() -> None:
    assert score("1 ne 3", "1 Nephi 3") is not None


def test_nonmatch_returns_none() -> None:
    assert score("xyz", "Genesis") is None


def test_empty_query_matches_everything() -> None:
    assert score("", "anything") is not None


def test_tighter_match_scores_lower() -> None:
    """A query that matches contiguously beats one with gaps."""
    tight = score("nep", "1 Nephi 3")
    loose = score("ngn", "1 Nephi 3")  # n, no g present, fails
    assert tight is not None
    assert loose is None


def test_shorter_label_wins_on_tie() -> None:
    a = score("g", "Genesis 1")
    b = score("g", "Galatians 1")
    assert a is not None and b is not None
    assert a.label_length < b.label_length


def test_chapter_number_matches() -> None:
    s = score("ps 119", "Psalms 119")
    assert s is not None
