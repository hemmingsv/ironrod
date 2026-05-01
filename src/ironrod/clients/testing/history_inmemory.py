"""In-memory ``HistoryJournal`` substitute for flow tests.

The contract suite in ``tests/test_clients_history_contract.py`` runs against
both this and the real ``HistoryJournal`` to prove they behave identically
before flow tests are allowed to inject this one.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ironrod.models import HistoryRecord, Reference


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class InMemoryHistoryJournal:
    def __init__(self) -> None:
        self._records: list[HistoryRecord] = []

    def load(self) -> list[HistoryRecord]:
        return list(self._records)

    def load_for(self, slug: str) -> list[HistoryRecord]:
        return [r for r in self._records if r.slug == slug]

    def append(self, slug: str, reference: Reference) -> bool:
        existing = self.load_for(slug)
        if existing and existing[-1].reference == reference:
            return False
        self._records.append(
            HistoryRecord(slug=slug, reference=reference, created_at=_now()),
        )
        return True
