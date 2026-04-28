"""In-memory ``BookmarkJournal`` substitute for flow tests.

The contract test suite in ``tests/test_clients_bookmarks_contract.py`` runs
against both this and the real ``BookmarkJournal`` to prove they behave
identically before flow tests are allowed to inject this one.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ironrod.clients.bookmarks import (
    BookmarkExists,
    BookmarkNotFound,
    CannotDeleteLast,
)
from ironrod.models import Bookmark, Reference
from ironrod.utils.slug import slugify


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class InMemoryBookmarkJournal:
    def __init__(self) -> None:
        self._bookmarks: list[Bookmark] = []

    def load(self) -> list[Bookmark]:
        return list(self._bookmarks)

    def top(self) -> Bookmark | None:
        return self._bookmarks[0] if self._bookmarks else None

    def get(self, slug: str) -> Bookmark:
        for bm in self._bookmarks:
            if bm.slug == slug:
                return bm
        raise BookmarkNotFound(slug)

    def create(self, name: str, reference: Reference) -> Bookmark:
        slug = slugify(name)
        if any(bm.slug == slug for bm in self._bookmarks):
            raise BookmarkExists(slug)
        now = _now()
        bookmark = Bookmark(
            name=name,
            slug=slug,
            reference=reference,
            created_at=now,
            updated_at=now,
        )
        self._bookmarks.insert(0, bookmark)
        return bookmark

    def touch(self, slug: str, reference: Reference | None = None) -> Bookmark:
        for i, bm in enumerate(self._bookmarks):
            if bm.slug == slug:
                updated = Bookmark(
                    name=bm.name,
                    slug=bm.slug,
                    reference=reference if reference is not None else bm.reference,
                    created_at=bm.created_at,
                    updated_at=_now(),
                )
                self._bookmarks.pop(i)
                self._bookmarks.insert(0, updated)
                return updated
        raise BookmarkNotFound(slug)

    def delete(self, slug: str) -> None:
        if len(self._bookmarks) <= 1 and any(bm.slug == slug for bm in self._bookmarks):
            raise CannotDeleteLast(slug)
        for i, bm in enumerate(self._bookmarks):
            if bm.slug == slug:
                self._bookmarks.pop(i)
                return
        raise BookmarkNotFound(slug)
