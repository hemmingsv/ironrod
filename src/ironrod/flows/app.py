"""prompt_toolkit wrapper around ``flows.state.App``.

Translates terminal events into ``state.App.on_key()`` calls and renders the
state's text buffer to the terminal. All app behaviour lives in ``state.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings, KeyPress
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from ironrod.clients.bookmarks import BookmarkJournal
from ironrod.clients.history import HistoryJournal
from ironrod.clients.scriptures import ScriptureDB
from ironrod.flows.state import App as StateApp

if TYPE_CHECKING:
    from prompt_toolkit.input import Input
    from prompt_toolkit.output import Output


SPECIAL_KEYS = {
    Keys.Up: "up",
    Keys.Down: "down",
    Keys.Left: "left",
    Keys.Right: "right",
    Keys.PageUp: "pageup",
    Keys.PageDown: "pagedown",
    Keys.Enter: "enter",
    Keys.ControlJ: "enter",
    Keys.ControlM: "enter",
    Keys.ControlN: "ctrl-n",
    Keys.ControlP: "ctrl-p",
    Keys.Backspace: "backspace",
    Keys.Escape: "escape",
}


def _translate_key(press: KeyPress) -> str | None:
    """Map a prompt_toolkit KeyPress to the high-level key name our state
    machine speaks. Returns None for keys we don't handle.
    """
    if press.key in SPECIAL_KEYS:
        return SPECIAL_KEYS[press.key]
    if isinstance(press.key, str) and len(press.key) == 1 and press.key.isprintable():
        return press.key
    if isinstance(press.data, str) and len(press.data) == 1 and press.data.isprintable():
        return press.data
    return None


def build_application(
    state_app: StateApp,
    *,
    input: "Input | None" = None,
    output: "Output | None" = None,
) -> Application:
    text_control = FormattedTextControl(text=lambda: "\n".join(state_app.render()))
    body = Window(content=text_control, wrap_lines=False, always_hide_cursor=True)
    layout = Layout(HSplit([body]))
    bindings = KeyBindings()

    @bindings.add(Keys.Any, eager=True)
    def _any(event) -> None:  # type: ignore[no-untyped-def]
        for press in event.key_sequence:
            translated = _translate_key(press)
            if translated is not None:
                state_app.on_key(translated)
        if state_app.quitting:
            event.app.exit()
        # Sync our app dimensions to the rendered output so the layout knows
        # how much space it has.
        info = event.app.renderer.output.get_size()
        state_app.height = info.rows
        state_app.width = info.columns
        event.app.invalidate()

    application = Application(
        layout=layout,
        key_bindings=bindings,
        full_screen=True,
        mouse_support=False,
        input=input,
        output=output,
    )

    @application.before_render.add_handler
    def _sync_size(_app: Application) -> None:  # type: ignore[no-untyped-def]
        info = application.renderer.output.get_size()
        state_app.height = info.rows
        state_app.width = info.columns

    return application


def run() -> None:
    """Entry point used by the CLI: open the bundled DB and the user's journal,
    construct the state machine, and run the prompt_toolkit application until
    the user quits.
    """
    with ScriptureDB() as db:
        journal = BookmarkJournal()
        history = HistoryJournal()
        state_app = StateApp(db=db, journal=journal, history=history)
        app = build_application(state_app)
        app.run()
