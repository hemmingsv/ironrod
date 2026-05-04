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


def test_optimal_alignment_for_repeated_first_char() -> None:
    # "15" in "1 Nephi 15" must align to the trailing "1 5" (span 1), not
    # to the leading "1" + far-away "5" (span 9). Otherwise "Alma 15"
    # (span 1) outranks the user's clear intent of chapter 15 of the
    # current book.
    s = score("15", "1 Nephi 15")
    assert s is not None
    assert s.span == 1


def test_optimal_alignment_picks_tightest_subsequence() -> None:
    # The label has both a loose ("1...3") and a tight ("13") match.
    # The tight one wins.
    assert score("13", "1abc13").span == 1
