"""Disk-only behaviour: persistence across reloads, atomic write integrity."""

from __future__ import annotations

from pathlib import Path

import pytest

from ironrod.clients.bookmarks import BookmarkJournal
from ironrod.models import Reference

GEN_1_1 = Reference(book_id=1, chapter_number=1, verse_number=1)
GEN_1_2 = Reference(book_id=1, chapter_number=1, verse_number=2)


def test_persists_across_reload(tmp_path: Path) -> None:
    j1 = BookmarkJournal(path=tmp_path / "bookmarks.jsonl")
    j1.create("Daily", GEN_1_1)
    j1.create("Evening", GEN_1_2)
    j2 = BookmarkJournal(path=tmp_path / "bookmarks.jsonl")
    assert [b.slug for b in j2.load()] == ["evening", "daily"]


def test_write_to_nonexistent_directory_is_created(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "deeper" / "bookmarks.jsonl"
    journal = BookmarkJournal(path=nested)
    journal.create("X", GEN_1_1)
    assert nested.exists()
    assert journal.load()[0].slug == "x"


def test_atomic_write_failure_preserves_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    journal = BookmarkJournal(path=tmp_path / "bookmarks.jsonl")
    journal.create("Alpha", GEN_1_1)
    contents_before = (tmp_path / "bookmarks.jsonl").read_bytes()

    import os as _os
    real_replace = _os.replace

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated failure")

    monkeypatch.setattr("ironrod.clients.bookmarks.os.replace", boom)
    with pytest.raises(OSError, match="simulated failure"):
        journal.create("Beta", GEN_1_2)

    # The original file is untouched.
    assert (tmp_path / "bookmarks.jsonl").read_bytes() == contents_before
    # The tmp file may exist; clean it up so the next assertion is clean.
    tmp_file = tmp_path / "bookmarks.jsonl.tmp"
    if tmp_file.exists():
        tmp_file.unlink()
    monkeypatch.setattr("ironrod.clients.bookmarks.os.replace", real_replace)
    # And a normal create still works after recovery.
    journal.create("Beta", GEN_1_2)
    assert {b.slug for b in journal.load()} == {"alpha", "beta"}


def test_jsonl_format_one_bookmark_per_line(tmp_path: Path) -> None:
    journal = BookmarkJournal(path=tmp_path / "bookmarks.jsonl")
    journal.create("A", GEN_1_1)
    journal.create("B", GEN_1_1)
    raw = (tmp_path / "bookmarks.jsonl").read_text(encoding="utf-8")
    lines = [line for line in raw.splitlines() if line]
    assert len(lines) == 2
    for line in lines:
        # Each line is a complete JSON object.
        import json
        json.loads(line)
