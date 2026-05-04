"""Smoke test for the prompt_toolkit wrapper around the state machine.

Drives a real prompt_toolkit Application with simulated keystrokes via
``create_pipe_input`` and ``DummyOutput``. The state machine itself is covered
by ``test_flows_state.py``; this test only proves the wrapper:

1. Boots without raising.
2. Forwards keystrokes to the state machine.
3. Exits cleanly when the state sets ``quitting``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from ironrod.clients.scriptures import ScriptureDB
from ironrod.clients.testing.bookmarks_inmemory import InMemoryBookmarkJournal
from ironrod.clients.testing.history_inmemory import InMemoryHistoryJournal
from ironrod.flows.app import build_application
from ironrod.flows.state import App as StateApp


@pytest.fixture(scope="module")
def db() -> Iterator[ScriptureDB]:
    with ScriptureDB() as d:
        yield d


def test_wrapper_boots_and_quits(db: ScriptureDB) -> None:
    state = StateApp(
        db=db,
        journal=InMemoryBookmarkJournal(),
        history=InMemoryHistoryJournal(),
    )
    with create_pipe_input() as pipe:
        # Send three "j" then "q" to advance and quit.
        pipe.send_text("jjjq")
        app = build_application(state, input=pipe, output=DummyOutput())
        app.run(in_thread=False)
    assert state.quitting is True
    # The journal was rewritten — top reference may have advanced.
    top = state.journal.top()
    assert top is not None
    assert top.slug == "my-study"


def test_wrapper_handles_goto_keys(db: ScriptureDB) -> None:
    state = StateApp(
        db=db,
        journal=InMemoryBookmarkJournal(),
        history=InMemoryHistoryJournal(),
    )
    with create_pipe_input() as pipe:
        # g, "1 nephi 3", Enter, q. Spell out the book name so the query
        # disambiguates from same-volume matches like 1 Chronicles.
        pipe.send_text("g1 nephi 3\rq")
        app = build_application(state, input=pipe, output=DummyOutput())
        app.run(in_thread=False)
    nephi = next(b for b in db.books() if b.title == "1 Nephi")
    assert state.study.top_ref.book_id == nephi.id
    assert state.study.top_ref.chapter_number == 3
    assert state.study.top_ref.verse_number == 1
