"""JSONLines history journal at ``~/.ironrod/history.jsonl``.

Append-only audit log of past reading positions per bookmark. Each line is one
``HistoryRecord`` serialised as JSON. Records for a given bookmark are kept in
file order (oldest first, newest last). All bookmarks share one file, keyed by
``slug`` on each record.

Writes append a single line with ``fsync`` and dedup against the most recent
record for the same bookmark, so navigating to the same place twice in a row
does not grow the file.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ironrod.models import HistoryRecord, Reference


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _default_path() -> Path:
    return Path.home() / ".ironrod" / "history.jsonl"


class HistoryJournalProtocol(Protocol):
    def load(self) -> list[HistoryRecord]: ...
    def load_for(self, slug: str) -> list[HistoryRecord]: ...
    def append(self, slug: str, reference: Reference) -> bool: ...


class HistoryJournal:
    """Disk-backed JSONL implementation."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_path()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[HistoryRecord]:
        if not self._path.exists():
            return []
        out: list[HistoryRecord] = []
        with self._path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                out.append(HistoryRecord.model_validate_json(line))
        return out

    def load_for(self, slug: str) -> list[HistoryRecord]:
        return [r for r in self.load() if r.slug == slug]

    def append(self, slug: str, reference: Reference) -> bool:
        existing = self.load_for(slug)
        if existing and existing[-1].reference == reference:
            return False
        record = HistoryRecord(slug=slug, reference=reference, created_at=_now())
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(record.model_dump_json())
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        return True
