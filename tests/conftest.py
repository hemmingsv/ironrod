"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ironrod.clients.scriptures import ScriptureDB


@pytest.fixture(scope="session")
def scripture_db() -> Iterator[ScriptureDB]:
    """A live ScriptureDB on the bundled DB, reused across the session."""
    with ScriptureDB() as db:
        yield db


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` to ``tmp_path`` for the duration of a test."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path
