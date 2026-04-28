"""Tiny fuzzy matcher for the chapter Goto screen.

Matches the query as a case-insensitive in-order subsequence of the label.
Lower score = better match. Score = (match-span, label-length).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Score:
    span: int           # first → last matched index distance
    label_length: int


def score(query: str, label: str) -> Score | None:
    """Return a comparable score for ``label`` against ``query``, or None.

    >>> score("1 ne 3", "1 Nephi 3").span < 100
    True
    >>> score("xyz", "Genesis") is None
    True
    >>> score("", "anything").span
    0
    """
    if not query:
        return Score(span=0, label_length=len(label))
    q = query.lower()
    l = label.lower()
    j = 0
    first: int | None = None
    last = -1
    for i, ch in enumerate(l):
        if j < len(q) and ch == q[j]:
            if first is None:
                first = i
            last = i
            j += 1
            if j == len(q):
                break
    if j != len(q) or first is None:
        return None
    return Score(span=last - first, label_length=len(label))
