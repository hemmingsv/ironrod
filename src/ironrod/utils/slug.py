"""Slugify human-typed bookmark names into filesystem-safe identifiers."""

import re
import unicodedata

MAX_LEN = 64


def slugify(name: str) -> str:
    """Return a lowercase ASCII slug for ``name``.

    >>> slugify("My Study")
    'my-study'
    >>> slugify("  Daily Study!!  ")
    'daily-study'
    >>> slugify("café")
    'cafe'
    >>> slugify("1 Nephi & Ether")
    '1-nephi-ether'
    >>> slugify("___---___")
    Traceback (most recent call last):
        ...
    ValueError: name produced an empty slug
    >>> slugify("")
    Traceback (most recent call last):
        ...
    ValueError: name must be non-empty
    >>> slugify("x" * 80)[:5], len(slugify("x" * 80))
    ('xxxxx', 64)
    """
    if not name:
        raise ValueError("name must be non-empty")
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    lowered = folded.lower()
    dashed = re.sub(r"[^a-z0-9]+", "-", lowered)
    stripped = dashed.strip("-")
    if not stripped:
        raise ValueError("name produced an empty slug")
    return stripped[:MAX_LEN].rstrip("-")
