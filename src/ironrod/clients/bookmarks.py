"""JSONLines bookmark journal at ``~/.ironrod/bookmarks.jsonl``.

* Each line is one ``Bookmark`` serialised as JSON.
* Most-recently-used is on line 1.
* Every mutation rewrites the whole file atomically (tmp + ``os.replace``).

The file is small enough that rewriting on every keystroke is negligible.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ironrod.models import Bookmark, Reference
from ironrod.utils.slug import slugify


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class BookmarkExists(ValueError):
    """Raised when creating a bookmark whose slug already exists."""


class BookmarkNotFound(KeyError):
    """Raised when a slug isn't in the journal."""


class CannotDeleteLast(ValueError):
    """Raised when delete() would leave the journal empty."""


def _default_path() -> Path:
    return Path.home() / ".ironrod" / "bookmarks.jsonl"


# Public interface (also implemented by InMemoryBookmarkJournal).

class BookmarkJournalProtocol(Protocol):
    def load(self) -> list[Bookmark]: ...
    def top(self) -> Bookmark | None: ...
    def get(self, slug: str) -> Bookmark: ...
    def create(self, name: str, reference: Reference) -> Bookmark: ...
    def touch(self, slug: str, reference: Reference | None = None) -> Bookmark: ...
    def delete(self, slug: str) -> None: ...


class BookmarkJournal:
    """Disk-backed JSONL implementation."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_path()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[Bookmark]:
        if not self._path.exists():
            return []
        out: list[Bookmark] = []
        with self._path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                out.append(Bookmark.model_validate_json(line))
        return out

    def top(self) -> Bookmark | None:
        bookmarks = self.load()
        return bookmarks[0] if bookmarks else None

    def get(self, slug: str) -> Bookmark:
        for bm in self.load():
            if bm.slug == slug:
                return bm
        raise BookmarkNotFound(slug)

    def create(self, name: str, reference: Reference) -> Bookmark:
        slug = slugify(name)
        existing = self.load()
        if any(bm.slug == slug for bm in existing):
            raise BookmarkExists(slug)
        now = _now()
        bookmark = Bookmark(
            name=name,
            slug=slug,
            reference=reference,
            created_at=now,
            updated_at=now,
        )
        self._write([bookmark, *existing])
        return bookmark

    def touch(self, slug: str, reference: Reference | None = None) -> Bookmark:
        bookmarks = self.load()
        for i, bm in enumerate(bookmarks):
            if bm.slug == slug:
                updated = Bookmark(
                    name=bm.name,
                    slug=bm.slug,
                    reference=reference if reference is not None else bm.reference,
                    created_at=bm.created_at,
                    updated_at=_now(),
                )
                rest = bookmarks[:i] + bookmarks[i + 1 :]
                self._write([updated, *rest])
                return updated
        raise BookmarkNotFound(slug)

    def delete(self, slug: str) -> None:
        bookmarks = self.load()
        if len(bookmarks) <= 1 and any(bm.slug == slug for bm in bookmarks):
            raise CannotDeleteLast(slug)
        remaining = [bm for bm in bookmarks if bm.slug != slug]
        if len(remaining) == len(bookmarks):
            raise BookmarkNotFound(slug)
        self._write(remaining)

    # internals

    def _write(self, bookmarks: list[Bookmark]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for bm in bookmarks:
                f.write(bm.model_dump_json())
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
