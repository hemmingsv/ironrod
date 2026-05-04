"""Tiny fuzzy matcher for the chapter Goto screen.

Matches the query as a case-insensitive in-order subsequence of the label.
Lower score = better match. Score = (match-span, label-length).

``prefix_match_count`` is a separate, complementary signal — it counts how
many whitespace-split query tokens line up as prefixes of label tokens,
greedy left-to-right. The Goto sort uses it ahead of tier so that a
multi-token query like ``1 ne 1`` clearly disambiguates 1 Nephi 1 (count 3)
from 1 Chronicles 1 (count 2), even across volumes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Score:
    span: int           # first → last matched index distance
    label_length: int


def score(query: str, label: str) -> Score | None:
    """Return a comparable score for ``label`` against ``query``, or None.

    Reports the *tightest* subsequence match — the smallest distance from
    the first to the last matched character across every valid alignment.
    A naïve left-greedy scan would lock onto the first occurrence of the
    first query char, which makes "15" against "1 Nephi 15" look terrible
    (span 9, jumping past everything to reach the trailing 5) compared to
    "Alma 15" (span 1). The optimal alignment puts both at span 1.

    >>> score("1 ne 3", "1 Nephi 3").span < 100
    True
    >>> score("xyz", "Genesis") is None
    True
    >>> score("", "anything").span
    0
    >>> score("15", "1 Nephi 15").span
    1
    """
    if not query:
        return Score(span=0, label_length=len(label))
    q = query.lower()
    l = label.lower()
    best_span: int | None = None
    # Try each occurrence of the first query char as the alignment anchor;
    # greedy-match the remaining query chars from there. The minimum span
    # over all anchors is the optimal alignment.
    for start in range(len(l)):
        if l[start] != q[0]:
            continue
        j = 1
        last = start
        for i in range(start + 1, len(l)):
            if j == len(q):
                break
            if l[i] == q[j]:
                last = i
                j += 1
        if j != len(q):
            continue
        span = last - start
        if best_span is None or span < best_span:
            best_span = span
            if best_span == len(q) - 1:
                break  # contiguous match — can't do better
    if best_span is None:
        return None
    return Score(span=best_span, label_length=len(label))


def prefix_match_count(query: str, label: str) -> int:
    """Count whitespace-split query tokens that are prefixes of label tokens.

    Greedy left-to-right alignment: each query token consumes the next label
    token that prefix-matches it; on a miss, the label pointer stays put so a
    middle-query miss doesn't burn through later label tokens.

    >>> prefix_match_count("1 ne 1", "1 Nephi 1")
    3
    >>> prefix_match_count("1 ne 1", "1 Nephi 10")
    3
    >>> prefix_match_count("1 ne 1", "1 Chronicles 1")
    2
    >>> prefix_match_count("1 ne 1", "1 Chronicles 4")
    1
    >>> prefix_match_count("", "Genesis 1")
    0
    """
    q_tokens = query.lower().split()
    l_tokens = label.lower().split()
    count = 0
    li = 0
    for qt in q_tokens:
        for j in range(li, len(l_tokens)):
            if l_tokens[j].startswith(qt):
                count += 1
                li = j + 1
                break
    return count
