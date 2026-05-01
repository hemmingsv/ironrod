"""Disk-only behaviour for the history journal: persistence, file shape."""

from __future__ import annotations

import json
from pathlib import Path

from ironrod.clients.history import HistoryJournal
from ironrod.models import Reference

GEN_1_1 = Reference(book_id=1, chapter_number=1, verse_number=1)
GEN_1_2 = Reference(book_id=1, chapter_number=1, verse_number=2)


def test_persists_across_reload(tmp_path: Path) -> None:
    j1 = HistoryJournal(path=tmp_path / "history.jsonl")
    j1.append("daily", GEN_1_1)
    j1.append("daily", GEN_1_2)
    j2 = HistoryJournal(path=tmp_path / "history.jsonl")
    refs = [r.reference for r in j2.load_for("daily")]
    assert refs == [GEN_1_1, GEN_1_2]


def test_write_to_nonexistent_directory_is_created(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "deeper" / "history.jsonl"
    journal = HistoryJournal(path=nested)
    journal.append("x", GEN_1_1)
    assert nested.exists()
    assert journal.load_for("x")[0].reference == GEN_1_1


def test_jsonl_format_one_record_per_line(tmp_path: Path) -> None:
    journal = HistoryJournal(path=tmp_path / "history.jsonl")
    journal.append("a", GEN_1_1)
    journal.append("b", GEN_1_1)
    journal.append("a", GEN_1_2)
    raw = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    lines = [line for line in raw.splitlines() if line]
    assert len(lines) == 3
    for line in lines:
        json.loads(line)


def test_dedup_does_not_write_to_disk(tmp_path: Path) -> None:
    journal = HistoryJournal(path=tmp_path / "history.jsonl")
    journal.append("daily", GEN_1_1)
    size_before = (tmp_path / "history.jsonl").stat().st_size
    assert journal.append("daily", GEN_1_1) is False
    size_after = (tmp_path / "history.jsonl").stat().st_size
    assert size_after == size_before
