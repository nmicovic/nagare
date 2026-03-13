# Interactive Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace suspend/attach with inline terminal rendering — keystrokes forwarded to tmux, pane captured at high frequency, user never leaves nagare.

**Architecture:** A transport abstraction (`SessionTransport` ABC) decouples the app from the polling mechanism. `PollingTransport` implements it using `capture-pane` + `send-keys`. The app tracks which pane is active (left/right) and routes key events accordingly. Ctrl+] toggles between panes.

**Tech Stack:** Python 3.14+, Textual, tmux CLI

**Design doc:** `docs/plans/2026-03-13-interactive-mode-design.md`

**Key finding:** Textual represents Ctrl+] as `ctrl+right_square_bracket`. Ctrl+[ is indistinguishable from Escape at the terminal level, so we use a single toggle key.

---

### Task 1: Transport ABC + Key Mapper

**Files:**
- Create: `src/nagare/transport/__init__.py`
- Create: `src/nagare/transport/base.py`
- Create: `src/nagare/transport/keys.py`
- Create: `tests/test_keys.py`

**Step 1: Write the failing test for key mapper**

Create `tests/test_keys.py`:

```python
from nagare.transport.keys import textual_to_tmux


def test_regular_char():
    assert textual_to_tmux("a", "a") == ("send-keys", "-l", "a")


def test_enter():
    assert textual_to_tmux("enter", None) == ("send-keys", "Enter")


def test_tab():
    assert textual_to_tmux("tab", None) == ("send-keys", "Tab")


def test_backspace():
    assert textual_to_tmux("backspace", None) == ("send-keys", "BSpace")


def test_escape():
    assert textual_to_tmux("escape", None) == ("send-keys", "Escape")


def test_space():
    assert textual_to_tmux("space", " ") == ("send-keys", "Space")


def test_arrow_up():
    assert textual_to_tmux("up", None) == ("send-keys", "Up")


def test_arrow_down():
    assert textual_to_tmux("down", None) == ("send-keys", "Down")


def test_arrow_left():
    assert textual_to_tmux("left", None) == ("send-keys", "Left")


def test_arrow_right():
    assert textual_to_tmux("right", None) == ("send-keys", "Right")


def test_ctrl_c():
    assert textual_to_tmux("ctrl+c", None) == ("send-keys", "C-c")


def test_ctrl_d():
    assert textual_to_tmux("ctrl+d", None) == ("send-keys", "C-d")


def test_ctrl_l():
    assert textual_to_tmux("ctrl+l", None) == ("send-keys", "C-l")


def test_home():
    assert textual_to_tmux("home", None) == ("send-keys", "Home")


def test_end():
    assert textual_to_tmux("end", None) == ("send-keys", "End")


def test_pageup():
    assert textual_to_tmux("pageup", None) == ("send-keys", "PPage")


def test_pagedown():
    assert textual_to_tmux("pagedown", None) == ("send-keys", "NPage")


def test_delete():
    assert textual_to_tmux("delete", None) == ("send-keys", "DC")


def test_shift_tab():
    assert textual_to_tmux("shift+tab", None) == ("send-keys", "BTab")


def test_unknown_key_returns_none():
    assert textual_to_tmux("ctrl+right_square_bracket", None) is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_keys.py -v`
Expected: FAIL (ImportError)

**Step 3: Create transport package and key mapper**

Create `src/nagare/transport/__init__.py` (empty file).

Create `src/nagare/transport/keys.py`:

```python
import re

# Mapping of Textual key names to tmux send-keys arguments
_SPECIAL_KEYS: dict[str, str] = {
    "enter": "Enter",
    "tab": "Tab",
    "shift+tab": "BTab",
    "backspace": "BSpace",
    "escape": "Escape",
    "space": "Space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "PPage",
    "pagedown": "NPage",
    "delete": "DC",
}

_CTRL_RE = re.compile(r"^ctrl\+([a-z])$")

# Keys that nagare intercepts — never forwarded to tmux
INTERCEPTED_KEYS = frozenset({
    "ctrl+right_square_bracket",
})


def textual_to_tmux(key: str, character: str | None) -> tuple[str, ...] | None:
    """Convert a Textual key event to tmux send-keys arguments.

    Returns a tuple of arguments for run_tmux(), or None if the key
    should not be forwarded (intercepted by nagare).
    """
    if key in INTERCEPTED_KEYS:
        return None

    # Special keys
    if key in _SPECIAL_KEYS:
        return ("send-keys", _SPECIAL_KEYS[key])

    # Ctrl+letter combinations
    ctrl_match = _CTRL_RE.match(key)
    if ctrl_match:
        letter = ctrl_match.group(1)
        return ("send-keys", f"C-{letter}")

    # Regular printable character
    if character and len(character) == 1:
        return ("send-keys", "-l", character)

    return None
```

**Step 4: Create transport base ABC**

Create `src/nagare/transport/base.py`:

```python
from abc import ABC, abstractmethod
from collections.abc import Callable

from nagare.models import Session


class SessionTransport(ABC):

    @abstractmethod
    def get_content(self, session: Session) -> str:
        """Get current pane content (for preview mode)."""

    @abstractmethod
    def send_keys(self, session: Session, key: str, character: str | None) -> None:
        """Forward a key event to the session."""

    @abstractmethod
    def start_streaming(self, session: Session, callback: Callable[[str], None]) -> None:
        """Begin high-frequency content updates. Calls callback(content) on each update."""

    @abstractmethod
    def stop_streaming(self) -> None:
        """Stop high-frequency updates."""
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_keys.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/nagare/transport/ tests/test_keys.py
git commit -m "feat: transport ABC and Textual-to-tmux key mapper"
```

---

### Task 2: PollingTransport

**Files:**
- Create: `src/nagare/transport/polling.py`
- Create: `tests/test_polling_transport.py`

**Step 1: Write the failing test**

Create `tests/test_polling_transport.py`:

```python
from unittest.mock import patch, MagicMock, call
from nagare.transport.polling import PollingTransport
from nagare.models import Session, SessionStatus


MOCK_SESSION = Session(
    name="proj-a", session_id="$1", path="/home/user/a",
    pane_index=0, status=SessionStatus.IDLE,
)


@patch("nagare.transport.polling.run_tmux")
def test_get_content(mock_run):
    mock_run.return_value = "pane content here"
    transport = PollingTransport()
    result = transport.get_content(MOCK_SESSION)
    assert result == "pane content here"
    mock_run.assert_called_once_with("capture-pane", "-t", "proj-a:0", "-p", "-e")


@patch("nagare.transport.polling.run_tmux")
def test_send_keys_regular_char(mock_run):
    transport = PollingTransport()
    transport.send_keys(MOCK_SESSION, "a", "a")
    mock_run.assert_called_once_with("send-keys", "-t", "proj-a:0", "-l", "a")


@patch("nagare.transport.polling.run_tmux")
def test_send_keys_special(mock_run):
    transport = PollingTransport()
    transport.send_keys(MOCK_SESSION, "enter", None)
    mock_run.assert_called_once_with("send-keys", "-t", "proj-a:0", "Enter")


@patch("nagare.transport.polling.run_tmux")
def test_send_keys_ctrl(mock_run):
    transport = PollingTransport()
    transport.send_keys(MOCK_SESSION, "ctrl+c", None)
    mock_run.assert_called_once_with("send-keys", "-t", "proj-a:0", "C-c")


@patch("nagare.transport.polling.run_tmux")
def test_send_keys_intercepted_ignored(mock_run):
    transport = PollingTransport()
    transport.send_keys(MOCK_SESSION, "ctrl+right_square_bracket", None)
    mock_run.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_polling_transport.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/transport/polling.py`:

```python
import threading
from collections.abc import Callable

from nagare.models import Session
from nagare.tmux import run_tmux
from nagare.transport.base import SessionTransport
from nagare.transport.keys import textual_to_tmux


class PollingTransport(SessionTransport):

    def __init__(self) -> None:
        self._streaming: bool = False
        self._stream_timer: threading.Timer | None = None

    def get_content(self, session: Session) -> str:
        return run_tmux("capture-pane", "-t", f"{session.name}:{session.pane_index}", "-p", "-e")

    def send_keys(self, session: Session, key: str, character: str | None) -> None:
        args = textual_to_tmux(key, character)
        if args is None:
            return
        target = f"{session.name}:{session.pane_index}"
        # Insert -t target after "send-keys"
        cmd = (args[0], "-t", target) + args[1:]
        run_tmux(*cmd)

    def start_streaming(self, session: Session, callback: Callable[[str], None]) -> None:
        self.stop_streaming()
        self._streaming = True

        def poll() -> None:
            if not self._streaming:
                return
            content = self.get_content(session)
            callback(content)
            if self._streaming:
                self._stream_timer = threading.Timer(0.2, poll)
                self._stream_timer.daemon = True
                self._stream_timer.start()

        poll()

    def stop_streaming(self) -> None:
        self._streaming = False
        if self._stream_timer is not None:
            self._stream_timer.cancel()
            self._stream_timer = None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_polling_transport.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/nagare/transport/polling.py tests/test_polling_transport.py
git commit -m "feat: PollingTransport with capture-pane and send-keys"
```

---

### Task 3: Reactive Footer Bar

**Files:**
- Modify: `src/nagare/widgets/footer_bar.py`
- Modify: `tests/test_footer_bar.py`

**Step 1: Write the failing test**

Replace `tests/test_footer_bar.py`:

```python
from textual.app import App, ComposeResult
from nagare.widgets.footer_bar import FooterBar


class FooterApp(App):
    def compose(self) -> ComposeResult:
        yield FooterBar()


async def test_footer_browse_mode():
    app = FooterApp()
    async with app.run_test() as pilot:
        footer = app.query_one(FooterBar)
        footer.set_browse_mode()
        await pilot.pause()
        assert "Ctrl+]" in footer.renderable


async def test_footer_interactive_mode():
    app = FooterApp()
    async with app.run_test() as pilot:
        footer = app.query_one(FooterBar)
        footer.set_interactive_mode()
        await pilot.pause()
        assert "Ctrl+]" in footer.renderable
        assert "forwarded" in footer.renderable.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_footer_bar.py -v`
Expected: FAIL (no set_browse_mode method)

**Step 3: Write implementation**

Replace `src/nagare/widgets/footer_bar.py`:

```python
from textual.widgets import Static

BROWSE_FOOTER = (
    "[b]↑/k[/b] Up  [b]↓/j[/b] Down  [b]Ctrl+][/b] Interact  "
    "[b]r[/b] Refresh  [b]t[/b] Theme  [b]q[/b] Quit"
)

INTERACTIVE_FOOTER = (
    "[b]Ctrl+][/b] Back to sessions    "
    "All input forwarded to session"
)


class FooterBar(Static):

    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(BROWSE_FOOTER)

    def set_browse_mode(self) -> None:
        self.update(BROWSE_FOOTER)

    def set_interactive_mode(self) -> None:
        self.update(INTERACTIVE_FOOTER)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_footer_bar.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add src/nagare/widgets/footer_bar.py tests/test_footer_bar.py
git commit -m "feat: reactive footer bar with browse/interactive modes"
```

---

### Task 4: TerminalView Widget (replaces PreviewPane)

**Files:**
- Create: `src/nagare/widgets/terminal_view.py`
- Create: `tests/test_terminal_view.py`

The PreviewPane (RichLog) is read-only and appends content. For interactive mode we need a widget that replaces its entire content each update (like a screen buffer) and can signal key events to the app.

**Step 1: Write the failing test**

Create `tests/test_terminal_view.py`:

```python
from textual.app import App, ComposeResult
from nagare.widgets.terminal_view import TerminalView


class TVApp(App):
    def compose(self) -> ComposeResult:
        yield TerminalView()


async def test_terminal_view_update():
    app = TVApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.update_content("hello\nworld")
        await pilot.pause()
        assert tv is not None


async def test_terminal_view_empty():
    app = TVApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.update_content("")
        await pilot.pause()
        assert tv is not None


async def test_terminal_view_active_border():
    app = TVApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.set_active(True)
        await pilot.pause()
        assert tv.has_class("active-pane")
        tv.set_active(False)
        await pilot.pause()
        assert not tv.has_class("active-pane")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_terminal_view.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/widgets/terminal_view.py`:

```python
from rich.text import Text
from textual.widgets import RichLog


class TerminalView(RichLog):

    DEFAULT_CSS = """
    TerminalView {
        border: solid $surface;
    }

    TerminalView.active-pane {
        border: solid $primary;
    }
    """

    def __init__(self) -> None:
        super().__init__(wrap=False, highlight=False, markup=False)

    def update_content(self, raw_output: str) -> None:
        self.clear()
        if raw_output:
            rendered = Text.from_ansi(raw_output)
            self.write(rendered)

    def set_active(self, active: bool) -> None:
        if active:
            self.add_class("active-pane")
        else:
            self.remove_class("active-pane")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_terminal_view.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/nagare/widgets/terminal_view.py tests/test_terminal_view.py
git commit -m "feat: TerminalView widget with active pane border"
```

---

### Task 5: Update Left Pane Border Styling

**Files:**
- Modify: `src/nagare/nagare.tcss`

**Step 1: Update CSS**

Replace `src/nagare/nagare.tcss`:

```css
Screen {
    layout: horizontal;
}

#left-pane {
    width: 30%;
    border: solid $primary;
}

#left-pane.inactive-pane {
    border: solid $surface;
}

SessionList {
    height: 1fr;
}

SessionDetail {
    height: auto;
}

TerminalView {
    width: 70%;
}

FooterBar {
    dock: bottom;
    width: 100%;
}
```

**Step 2: Verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add src/nagare/nagare.tcss
git commit -m "feat: active/inactive pane border styling"
```

---

### Task 6: Rewire NagareApp with Transport and Pane Focus

This is the big integration task. The app gets:
- A `PollingTransport` instance
- Active pane tracking (left/right)
- Ctrl+] toggle binding
- `on_key` handler that forwards keys in interactive mode
- Separate timers for preview vs streaming

**Files:**
- Modify: `src/nagare/app.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_integration.py`
- Delete: `src/nagare/widgets/preview_pane.py` (replaced by TerminalView)
- Delete: `src/nagare/tmux/attach.py` (no longer needed)

**Step 1: Write the failing test**

Replace `tests/test_app.py`:

```python
from unittest.mock import patch, MagicMock
from nagare.app import NagareApp
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.IDLE),
]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_app_launches(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "hello from pane"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from nagare.widgets.session_list import SessionList
        from nagare.widgets.terminal_view import TerminalView
        from nagare.widgets.footer_bar import FooterBar
        assert app.query_one(SessionList) is not None
        assert app.query_one(TerminalView) is not None
        assert app.query_one(FooterBar) is not None


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_starts_in_browse_mode(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "content"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._active_pane == "left"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL

**Step 3: Rewrite app.py**

Replace `src/nagare/app.py`:

```python
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical

from nagare.models import Session
from nagare.tmux.scanner import scan_sessions
from nagare.themes import THEMES, DEFAULT_THEME
from nagare.transport.polling import PollingTransport
from nagare.widgets.session_list import SessionList
from nagare.widgets.session_detail import SessionDetail
from nagare.widgets.terminal_view import TerminalView
from nagare.widgets.footer_bar import FooterBar
from nagare.widgets.theme_picker import ThemePicker


class NagareApp(App):
    CSS_PATH = "nagare.tcss"
    TITLE = "nagare"

    BINDINGS = [
        Binding("ctrl+right_square_bracket", "toggle_pane", "Toggle Pane", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._transport = PollingTransport()
        self._active_pane: str = "left"  # "left" or "right"
        self._active_session: Session | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="left-pane"):
            yield SessionList()
            yield SessionDetail()
        yield TerminalView()
        yield FooterBar()

    def on_mount(self) -> None:
        self._theme_names = list(THEMES.keys())
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = DEFAULT_THEME
        self._refresh_sessions()
        self._scan_timer = self.set_interval(3, self._refresh_sessions)
        self._preview_timer = self.set_interval(3, self._refresh_preview)
        self._set_pane_focus("left")

    # --- Pane focus management ---

    def _set_pane_focus(self, pane: str) -> None:
        self._active_pane = pane
        left = self.query_one("#left-pane")
        terminal = self.query_one(TerminalView)
        footer = self.query_one(FooterBar)

        if pane == "left":
            left.remove_class("inactive-pane")
            terminal.set_active(False)
            footer.set_browse_mode()
            self._transport.stop_streaming()
            if self._preview_timer is not None:
                self._preview_timer.resume()
            self.query_one(SessionList).focus()
        else:
            left.add_class("inactive-pane")
            terminal.set_active(True)
            footer.set_interactive_mode()
            if self._preview_timer is not None:
                self._preview_timer.pause()
            session = self.query_one(SessionList).selected_session
            if session:
                self._active_session = session
                self._transport.start_streaming(
                    session,
                    lambda content: self.call_from_thread(self._on_stream_content, content),
                )
            terminal.focus()

    def _on_stream_content(self, content: str) -> None:
        self.query_one(TerminalView).update_content(content)

    def action_toggle_pane(self) -> None:
        if self._active_pane == "left":
            self._set_pane_focus("right")
        else:
            self._set_pane_focus("left")

    # --- Key forwarding ---

    def on_key(self, event: events.Key) -> None:
        if self._active_pane != "right":
            return
        if event.key == "ctrl+right_square_bracket":
            return  # handled by binding
        session = self._active_session
        if session:
            self._transport.send_keys(session, event.key, event.character)
            event.prevent_default()
            event.stop()

    # --- Session refresh ---

    def _refresh_sessions(self) -> None:
        sessions = scan_sessions()
        session_list = self.query_one(SessionList)
        session_list.update_sessions(sessions)
        detail = self.query_one(SessionDetail)
        detail.update_session(session_list.selected_session)
        if self._active_pane == "left":
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._active_pane != "left":
            return
        session_list = self.query_one(SessionList)
        session = session_list.selected_session
        terminal = self.query_one(TerminalView)
        if session is None:
            terminal.update_content("No sessions found.")
            return
        content = self._transport.get_content(session)
        terminal.update_content(content)

    def on_session_list_session_highlighted(self, event: SessionList.SessionHighlighted) -> None:
        detail = self.query_one(SessionDetail)
        detail.update_session(event.session)
        if self._active_pane == "left":
            terminal = self.query_one(TerminalView)
            content = self._transport.get_content(event.session)
            terminal.update_content(content)

    # --- Browse mode bindings ---

    def _check_browse_mode(self) -> bool:
        return self._active_pane == "left"

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        browse_only = {"quit", "refresh", "pick_theme", "cursor_down", "cursor_up"}
        if action in browse_only and not self._check_browse_mode():
            return False
        return True

    def action_refresh(self) -> None:
        self._refresh_sessions()

    def action_quit(self) -> None:
        self._transport.stop_streaming()
        self.exit()

    def action_pick_theme(self) -> None:
        prev_theme = self.theme

        def on_dismiss(result: str | None) -> None:
            if result is None:
                self.theme = prev_theme
            else:
                self.theme = result

        self.push_screen(
            ThemePicker(self._theme_names, self.theme),
            callback=on_dismiss,
        )

    def action_cursor_down(self) -> None:
        self.query_one(SessionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(SessionList).action_cursor_up()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py -v`
Expected: 2 passed

**Step 5: Update integration tests**

Replace `tests/test_integration.py`:

```python
from unittest.mock import patch, MagicMock
from nagare.app import NagareApp
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.IDLE),
    Session(name="proj-b", session_id="$2", path="/home/user/b", pane_index=0, status=SessionStatus.IDLE),
]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_navigate_sessions(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "mock content"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from nagare.widgets.session_list import SessionList
        session_list = app.query_one(SessionList)

        assert session_list.selected_session == MOCK_SESSIONS[0]
        await pilot.press("j")
        await pilot.pause()
        assert session_list.selected_session == MOCK_SESSIONS[1]
        await pilot.press("k")
        await pilot.pause()
        assert session_list.selected_session == MOCK_SESSIONS[0]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_toggle_pane(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "mock content"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._active_pane == "left"

        await pilot.press("ctrl+right_square_bracket")
        await pilot.pause()
        assert app._active_pane == "right"
        mock_transport.start_streaming.assert_called_once()

        await pilot.press("ctrl+right_square_bracket")
        await pilot.pause()
        assert app._active_pane == "left"
        mock_transport.stop_streaming.assert_called()


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_quit(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "mock content"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.pause()
```

**Step 6: Remove old files**

Delete `src/nagare/widgets/preview_pane.py` and `src/nagare/tmux/attach.py`.
Delete `tests/test_preview_pane.py` and `tests/test_attach.py`.

**Step 7: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All pass (with updated test count)

**Step 8: Commit**

```bash
git add src/nagare/app.py src/nagare/nagare.tcss tests/test_app.py tests/test_integration.py
git rm src/nagare/widgets/preview_pane.py src/nagare/tmux/attach.py tests/test_preview_pane.py tests/test_attach.py
git commit -m "feat: rewire app with transport, pane toggle, and interactive mode"
```

---

### Task 7: Smoke Test and Polish

**Files:**
- Possibly tweak any file based on manual testing

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All pass

**Step 2: Manual smoke test**

Run: `uv run nagare`

Test the following:
1. Sessions appear in left pane with correct statuses
2. Preview updates as you navigate with j/k
3. Ctrl+] switches to right pane (border changes, footer changes)
4. Typing in right pane forwards to tmux session
5. Ctrl+] switches back to left pane (streaming stops, preview resumes)
6. j/k navigation works again in left pane
7. Theme picker still works (t)
8. q quits cleanly

**Step 3: Fix any issues found**

**Step 4: Commit if needed**

```bash
git add -A
git commit -m "fix: polish interactive mode after smoke testing"
```

---

## Summary

| Task | What | Key Files |
|------|------|-----------|
| 1 | Transport ABC + key mapper | transport/base.py, transport/keys.py |
| 2 | PollingTransport | transport/polling.py |
| 3 | Reactive footer bar | widgets/footer_bar.py |
| 4 | TerminalView widget | widgets/terminal_view.py |
| 5 | CSS border styling | nagare.tcss |
| 6 | Rewire NagareApp | app.py (big integration) |
| 7 | Smoke test + polish | any |
