# nagare v2: tmux-integrated implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Pivot nagare from a standalone Textual TUI to a tmux-integrated CLI with session picker, notification daemon, and notification center — all rendered through tmux's native `display-popup`.

**Architecture:** Three CLI commands (`nagare pick`, `nagare notifs`, `nagare daemon`) plus `nagare setup` for onboarding. Reuses existing tmux scanner, status detection, and models. New notification backend abstraction, JSON notification store, config loader, and two small Textual apps for the popups.

**Tech Stack:** Python 3.14+, Textual (for popup UIs), tmux `display-popup`, `tomllib` (stdlib) for config, JSON for notification storage.

---

### Task 1: Config Loader

**Files:**
- Create: `src/nagare/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing tests**

```python
# tests/test_config.py
import os
from unittest.mock import patch
from nagare.config import load_config, NagareConfig


def test_default_config():
    with patch.dict(os.environ, {}, clear=True):
        with patch("nagare.config.CONFIG_PATH", "/nonexistent/config.toml"):
            cfg = load_config()
    assert cfg.notification_backend == "tmux"
    assert cfg.notification_duration == 2000
    assert cfg.poll_interval == 3
    assert cfg.picker_width == "80%"
    assert cfg.picker_height == "80%"


def test_load_from_toml(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
backend = "notify-send"
duration = 3000
poll_interval = 5

[picker]
popup_width = "90%"
popup_height = "70%"
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notification_backend == "notify-send"
    assert cfg.notification_duration == 3000
    assert cfg.poll_interval == 5
    assert cfg.picker_width == "90%"
    assert cfg.picker_height == "70%"


def test_partial_config(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
duration = 4000
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notification_backend == "tmux"
    assert cfg.notification_duration == 4000
    assert cfg.poll_interval == 3
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nagare.config'`

**Step 3: Write implementation**

```python
# src/nagare/config.py
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = str(Path.home() / ".config" / "nagare" / "config.toml")


@dataclass(frozen=True)
class NagareConfig:
    notification_backend: str = "tmux"
    notification_duration: int = 2000
    poll_interval: int = 3
    picker_width: str = "80%"
    picker_height: str = "80%"


def load_config() -> NagareConfig:
    path = Path(CONFIG_PATH)
    if not path.exists():
        return NagareConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    notifs = data.get("notifications", {})
    picker = data.get("picker", {})

    return NagareConfig(
        notification_backend=notifs.get("backend", "tmux"),
        notification_duration=notifs.get("duration", 2000),
        poll_interval=notifs.get("poll_interval", 3),
        picker_width=picker.get("popup_width", "80%"),
        picker_height=picker.get("popup_height", "80%"),
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/nagare/config.py tests/test_config.py
git commit -m "feat: config loader with TOML support and sensible defaults"
```

---

### Task 2: Notification Backend Abstraction + tmux Backend

**Files:**
- Create: `src/nagare/notifications/__init__.py`
- Create: `src/nagare/notifications/base.py`
- Create: `src/nagare/notifications/tmux.py`
- Test: `tests/test_notifications.py`

**Step 1: Write the failing tests**

```python
# tests/test_notifications.py
from unittest.mock import patch
from nagare.notifications.base import NotificationBackend
from nagare.notifications.tmux import TmuxNotificationBackend


def test_backend_is_abstract():
    """NotificationBackend cannot be instantiated directly."""
    import pytest
    with pytest.raises(TypeError):
        NotificationBackend()


@patch("nagare.notifications.tmux.run_tmux")
def test_tmux_backend_notify(mock_run):
    backend = TmuxNotificationBackend(duration=2000)
    backend.notify("cosmo-ai is waiting for input", "cosmo-ai", "high")
    mock_run.assert_called_once_with(
        "display-message", "-d", "2000",
        "⚡ cosmo-ai is waiting for input",
    )


@patch("nagare.notifications.tmux.run_tmux")
def test_tmux_backend_custom_duration(mock_run):
    backend = TmuxNotificationBackend(duration=5000)
    backend.notify("test message", "proj-a", "low")
    mock_run.assert_called_once_with(
        "display-message", "-d", "5000",
        "⚡ test message",
    )
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notifications.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/nagare/notifications/__init__.py
```

```python
# src/nagare/notifications/base.py
from abc import ABC, abstractmethod


class NotificationBackend(ABC):

    @abstractmethod
    def notify(self, message: str, session_name: str, urgency: str) -> None:
        """Send a notification to the user."""
```

```python
# src/nagare/notifications/tmux.py
from nagare.notifications.base import NotificationBackend
from nagare.tmux import run_tmux


class TmuxNotificationBackend(NotificationBackend):

    def __init__(self, duration: int = 2000) -> None:
        self._duration = duration

    def notify(self, message: str, session_name: str, urgency: str) -> None:
        run_tmux("display-message", "-d", str(self._duration), f"⚡ {message}")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_notifications.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/nagare/notifications/ tests/test_notifications.py
git commit -m "feat: notification backend abstraction with tmux display-message"
```

---

### Task 3: Notification Store

**Files:**
- Create: `src/nagare/notifications/store.py`
- Test: `tests/test_notification_store.py`

**Step 1: Write the failing tests**

```python
# tests/test_notification_store.py
import json
from nagare.notifications.store import NotificationStore, Notification


def test_add_and_list(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("cosmo-ai", "Waiting for input")
    store.add("proj-b", "Waiting for input")

    notifs = store.list_all()
    assert len(notifs) == 2
    assert notifs[0].session_name == "proj-b"  # newest first
    assert notifs[1].session_name == "cosmo-ai"
    assert notifs[0].read is False


def test_mark_read(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("cosmo-ai", "Waiting for input")
    notifs = store.list_all()
    store.mark_read(notifs[0].id)

    notifs = store.list_all()
    assert notifs[0].read is True


def test_dismiss_one(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("cosmo-ai", "Waiting for input")
    store.add("proj-b", "Waiting for input")
    notifs = store.list_all()
    store.dismiss(notifs[0].id)

    notifs = store.list_all()
    assert len(notifs) == 1
    assert notifs[0].session_name == "cosmo-ai"


def test_dismiss_all(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("cosmo-ai", "msg1")
    store.add("proj-b", "msg2")
    store.dismiss_all()

    assert store.list_all() == []


def test_persistence(tmp_path):
    path = tmp_path / "notifs.json"
    store1 = NotificationStore(path)
    store1.add("cosmo-ai", "Waiting for input")

    store2 = NotificationStore(path)
    notifs = store2.list_all()
    assert len(notifs) == 1
    assert notifs[0].session_name == "cosmo-ai"


def test_empty_store(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    assert store.list_all() == []


def test_unread_count(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("a", "msg")
    store.add("b", "msg")
    assert store.unread_count() == 2
    notifs = store.list_all()
    store.mark_read(notifs[0].id)
    assert store.unread_count() == 1
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notification_store.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/nagare/notifications/store.py
import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Notification:
    id: str
    session_name: str
    message: str
    timestamp: str
    read: bool = False


class NotificationStore:

    def __init__(self, path: Path) -> None:
        self._path = path
        self._notifications: list[Notification] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text())
            self._notifications = [Notification(**n) for n in data]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps([asdict(n) for n in self._notifications]))

    def add(self, session_name: str, message: str) -> None:
        notif = Notification(
            id=str(uuid.uuid4()),
            session_name=session_name,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._notifications.append(notif)
        self._save()

    def list_all(self) -> list[Notification]:
        return list(reversed(self._notifications))

    def mark_read(self, notif_id: str) -> None:
        for n in self._notifications:
            if n.id == notif_id:
                n.read = True
                break
        self._save()

    def dismiss(self, notif_id: str) -> None:
        self._notifications = [n for n in self._notifications if n.id != notif_id]
        self._save()

    def dismiss_all(self) -> None:
        self._notifications.clear()
        self._save()

    def unread_count(self) -> int:
        return sum(1 for n in self._notifications if not n.read)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_notification_store.py -v`
Expected: 7 PASSED

**Step 5: Commit**

```bash
git add src/nagare/notifications/store.py tests/test_notification_store.py
git commit -m "feat: JSON-backed notification store with add, dismiss, mark-read"
```

---

### Task 4: Daemon

**Files:**
- Create: `src/nagare/daemon.py`
- Test: `tests/test_daemon.py`

**Step 1: Write the failing tests**

```python
# tests/test_daemon.py
from unittest.mock import patch, MagicMock, call
from nagare.daemon import SessionMonitor
from nagare.models import Session, SessionStatus, SessionDetails


def _make_session(name: str, status: SessionStatus) -> Session:
    return Session(name=name, session_id="$1", path=f"/home/user/{name}",
                   pane_index=0, status=status)


@patch("nagare.daemon.scan_sessions")
def test_detects_new_waiting_session(mock_scan):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    # First poll: session is running
    mock_scan.return_value = [_make_session("proj-a", SessionStatus.RUNNING)]
    monitor.poll()

    # Second poll: session now waiting
    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()

    backend.notify.assert_called_once()
    assert "proj-a" in backend.notify.call_args[0][0]
    store.add.assert_called_once()


@patch("nagare.daemon.scan_sessions")
def test_no_duplicate_notification(mock_scan):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()
    monitor.poll()
    monitor.poll()

    # Only notified once (on first detection)
    assert backend.notify.call_count == 1


@patch("nagare.daemon.scan_sessions")
def test_renotifies_after_status_change(mock_scan):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    # waiting -> running -> waiting should notify twice
    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()
    mock_scan.return_value = [_make_session("proj-a", SessionStatus.RUNNING)]
    monitor.poll()
    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()

    assert backend.notify.call_count == 2


@patch("nagare.daemon.scan_sessions")
def test_no_notification_for_running(mock_scan):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    mock_scan.return_value = [_make_session("proj-a", SessionStatus.RUNNING)]
    monitor.poll()

    backend.notify.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/nagare/daemon.py
import sys
import time
import signal
from pathlib import Path

from nagare.config import load_config
from nagare.models import SessionStatus
from nagare.notifications.base import NotificationBackend
from nagare.notifications.store import NotificationStore
from nagare.notifications.tmux import TmuxNotificationBackend
from nagare.tmux.scanner import scan_sessions

DATA_DIR = Path.home() / ".local" / "share" / "nagare"
PID_FILE = DATA_DIR / "daemon.pid"
STORE_PATH = DATA_DIR / "notifications.json"


class SessionMonitor:

    def __init__(self, backend: NotificationBackend, store: NotificationStore) -> None:
        self._backend = backend
        self._store = store
        self._prev_status: dict[str, SessionStatus] = {}

    def poll(self) -> None:
        sessions = scan_sessions()
        for session in sessions:
            prev = self._prev_status.get(session.name)
            if session.status == SessionStatus.WAITING_INPUT and prev != SessionStatus.WAITING_INPUT:
                msg = f"{session.name} is waiting for input"
                self._backend.notify(msg, session.name, "high")
                self._store.add(session.name, msg)
            self._prev_status[session.name] = session.status


def run_daemon() -> None:
    config = load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write PID file
    PID_FILE.write_text(str(os.getpid()))

    backend = TmuxNotificationBackend(duration=config.notification_duration)
    store = NotificationStore(STORE_PATH)
    monitor = SessionMonitor(backend, store)

    def handle_signal(sig, frame):
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        while True:
            monitor.poll()
            time.sleep(config.poll_interval)
    finally:
        PID_FILE.unlink(missing_ok=True)
```

Note: add `import os` at the top of the file (after `import sys`).

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_daemon.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add src/nagare/daemon.py tests/test_daemon.py
git commit -m "feat: session monitor daemon with status change detection"
```

---

### Task 5: Session Picker App

**Files:**
- Create: `src/nagare/pick.py`
- Create: `src/nagare/pick.tcss`
- Test: `tests/test_pick.py`

This is the Textual app that runs inside `tmux display-popup`.

**Step 1: Write the failing tests**

```python
# tests/test_pick.py
from unittest.mock import patch, MagicMock
from nagare.pick import PickerApp
from nagare.models import Session, SessionStatus, SessionDetails


MOCK_SESSIONS = [
    Session(name="cosmo-ai", session_id="$1", path="/home/user/cosmo",
            pane_index=0, status=SessionStatus.WAITING_INPUT,
            details=SessionDetails(git_branch="main", model="Opus", context_usage="50%")),
    Session(name="nagare", session_id="$2", path="/home/user/nagare",
            pane_index=0, status=SessionStatus.IDLE,
            details=SessionDetails(git_branch="feat", model="Sonnet", context_usage="20%")),
    Session(name="proj-b", session_id="$3", path="/home/user/projb",
            pane_index=0, status=SessionStatus.RUNNING,
            details=SessionDetails(git_branch="dev", model="Opus", context_usage="80%")),
]


@patch("nagare.pick.scan_sessions", return_value=MOCK_SESSIONS)
async def test_picker_shows_sessions(mock_scan):
    app = PickerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList
        option_list = app.query_one(OptionList)
        assert option_list.option_count == 3


@patch("nagare.pick.scan_sessions", return_value=MOCK_SESSIONS)
async def test_picker_waiting_sessions_first(mock_scan):
    app = PickerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # WAITING_INPUT sessions should sort to the top
        assert app._filtered_sessions[0].name == "cosmo-ai"


@patch("nagare.pick.scan_sessions", return_value=MOCK_SESSIONS)
async def test_picker_fuzzy_filter(mock_scan):
    app = PickerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Input, OptionList
        search = app.query_one(Input)
        search.value = "cos"
        await pilot.pause()
        option_list = app.query_one(OptionList)
        assert option_list.option_count == 1


@patch("nagare.pick.scan_sessions", return_value=MOCK_SESSIONS)
async def test_picker_escape_exits(mock_scan):
    app = PickerApp()
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        # App should exit with no result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pick.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/nagare/pick.py
import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from nagare.models import Session, SessionStatus
from nagare.themes import THEMES, DEFAULT_THEME
from nagare.tmux import run_tmux
from nagare.tmux.scanner import scan_sessions

# Sort priority: WAITING_INPUT first, then RUNNING, IDLE, DEAD
_STATUS_SORT = {
    SessionStatus.WAITING_INPUT: 0,
    SessionStatus.RUNNING: 1,
    SessionStatus.IDLE: 2,
    SessionStatus.DEAD: 3,
}


def _format_session(session: Session) -> str:
    parts = [f"{session.status_icon} [b]{session.name}[/b]"]
    d = session.details
    if d.git_branch:
        parts.append(f"  [dim]{d.git_branch}[/dim]")
    if d.model:
        parts.append(f"  {d.model}")
    if d.context_usage:
        parts.append(f"  ctx:{d.context_usage}")
    parts.append(f"\n   [dim]{session.path}[/dim]")
    return "".join(parts)


def _fuzzy_match(query: str, text: str) -> bool:
    query = query.lower()
    text = text.lower()
    qi = 0
    for char in text:
        if qi < len(query) and char == query[qi]:
            qi += 1
    return qi == len(query)


class PickerApp(App):
    CSS_PATH = "pick.tcss"
    TITLE = "nagare pick"

    BINDINGS = [
        Binding("escape", "quit", "Cancel", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[Session] = []
        self._filtered_sessions: list[Session] = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search sessions...", id="search")
        yield OptionList(id="session-list")
        yield Static(
            "[b]Enter[/b] Jump  [b]↑/↓[/b] Navigate  [b]Esc[/b] Cancel",
            id="hint-bar",
        )

    def on_mount(self) -> None:
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = DEFAULT_THEME

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        self._sessions = scan_sessions()
        self._sessions.sort(key=lambda s: _STATUS_SORT.get(s.status, 99))
        self._filtered_sessions = list(self._sessions)
        self._rebuild_list()
        self.query_one("#search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        if not query:
            self._filtered_sessions = list(self._sessions)
        else:
            self._filtered_sessions = [
                s for s in self._sessions if _fuzzy_match(query, s.name)
            ]
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        option_list = self.query_one("#session-list", OptionList)
        option_list.clear_options()
        for session in self._filtered_sessions:
            option_list.add_option(Option(_format_session(session), id=session.name))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if 0 <= idx < len(self._filtered_sessions):
            session = self._filtered_sessions[idx]
            run_tmux("switch-client", "-t", session.name)
            self.exit()

    def on_key(self, event) -> None:
        # Forward arrow keys to option list when input is focused
        if event.key in ("down", "up", "j", "k"):
            option_list = self.query_one("#session-list", OptionList)
            if event.key in ("down", "j"):
                option_list.action_cursor_down()
            elif event.key in ("up", "k"):
                option_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            option_list = self.query_one("#session-list", OptionList)
            highlighted = option_list.highlighted
            if highlighted is not None and 0 <= highlighted < len(self._filtered_sessions):
                session = self._filtered_sessions[highlighted]
                run_tmux("switch-client", "-t", session.name)
                self.exit()
            event.prevent_default()
            event.stop()
```

```css
/* src/nagare/pick.tcss */
Screen {
    layout: vertical;
}

#search {
    dock: top;
    margin: 0 0 1 0;
}

#session-list {
    height: 1fr;
}

#hint-bar {
    dock: bottom;
    height: 1;
    background: $surface;
    color: $text-muted;
    padding: 0 1;
}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_pick.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add src/nagare/pick.py src/nagare/pick.tcss tests/test_pick.py
git commit -m "feat: fuzzy session picker with status-sorted list"
```

---

### Task 6: Notification Center App

**Files:**
- Create: `src/nagare/notifs.py`
- Create: `src/nagare/notifs.tcss`
- Test: `tests/test_notifs.py`

**Step 1: Write the failing tests**

```python
# tests/test_notifs.py
from unittest.mock import patch, MagicMock
from nagare.notifs import NotifsApp
from nagare.notifications.store import NotificationStore, Notification


def _make_store(tmp_path, items=None):
    store = NotificationStore(tmp_path / "notifs.json")
    if items:
        for session_name, message in items:
            store.add(session_name, message)
    return store


@patch("nagare.notifs.STORE_PATH", None)
async def test_notifs_shows_list(tmp_path):
    store = _make_store(tmp_path, [("cosmo-ai", "Waiting for input"), ("proj-b", "Waiting for input")])
    app = NotifsApp(store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList
        option_list = app.query_one(OptionList)
        assert option_list.option_count == 2


@patch("nagare.notifs.STORE_PATH", None)
async def test_notifs_dismiss_all(tmp_path):
    store = _make_store(tmp_path, [("a", "msg1"), ("b", "msg2")])
    app = NotifsApp(store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        assert store.list_all() == []


@patch("nagare.notifs.STORE_PATH", None)
async def test_notifs_escape_exits(tmp_path):
    store = _make_store(tmp_path)
    app = NotifsApp(store=store)
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notifs.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/nagare/notifs.py
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from nagare.notifications.store import NotificationStore
from nagare.themes import THEMES, DEFAULT_THEME
from nagare.tmux import run_tmux

STORE_PATH = Path.home() / ".local" / "share" / "nagare" / "notifications.json"


def _format_notification(notif) -> str:
    dot = "●" if not notif.read else " "
    ts = notif.timestamp[:19].replace("T", " ")
    return f"{dot} [b]{notif.session_name}[/b]  {notif.message}\n   [dim]{ts}[/dim]"


class NotifsApp(App):
    CSS_PATH = "notifs.tcss"
    TITLE = "nagare notifications"

    BINDINGS = [
        Binding("escape", "quit", "Close", show=False),
        Binding("d", "dismiss", "Dismiss", show=False),
        Binding("D", "dismiss_all", "Dismiss All", show=False),
    ]

    def __init__(self, store: NotificationStore | None = None) -> None:
        super().__init__()
        self._store = store or NotificationStore(STORE_PATH)

    def compose(self) -> ComposeResult:
        yield OptionList(id="notif-list")
        yield Static(
            "[b]Enter[/b] Jump  [b]d[/b] Dismiss  [b]D[/b] Dismiss all  [b]Esc[/b] Close",
            id="hint-bar",
        )

    def on_mount(self) -> None:
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = DEFAULT_THEME

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        self._rebuild_list()

    def _rebuild_list(self) -> None:
        notifs = self._store.list_all()
        option_list = self.query_one("#notif-list", OptionList)
        option_list.clear_options()
        for notif in notifs:
            option_list.add_option(Option(_format_notification(notif), id=notif.id))
        if not notifs:
            option_list.add_option(Option("[dim]No notifications[/dim]"))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        notifs = self._store.list_all()
        idx = event.option_index
        if 0 <= idx < len(notifs):
            notif = notifs[idx]
            self._store.mark_read(notif.id)
            run_tmux("switch-client", "-t", notif.session_name)
            self.exit()

    def action_dismiss(self) -> None:
        option_list = self.query_one("#notif-list", OptionList)
        highlighted = option_list.highlighted
        notifs = self._store.list_all()
        if highlighted is not None and 0 <= highlighted < len(notifs):
            self._store.dismiss(notifs[highlighted].id)
            self._rebuild_list()

    def action_dismiss_all(self) -> None:
        self._store.dismiss_all()
        self._rebuild_list()
```

```css
/* src/nagare/notifs.tcss */
Screen {
    layout: vertical;
}

#notif-list {
    height: 1fr;
}

#hint-bar {
    dock: bottom;
    height: 1;
    background: $surface;
    color: $text-muted;
    padding: 0 1;
}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_notifs.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/nagare/notifs.py src/nagare/notifs.tcss tests/test_notifs.py
git commit -m "feat: notification center with dismiss and jump-to-session"
```

---

### Task 7: CLI Entry Point + Setup Command

**Files:**
- Modify: `src/nagare/__init__.py`
- Create: `src/nagare/setup.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

```python
# tests/test_cli.py
from unittest.mock import patch, MagicMock
from nagare.setup import generate_tmux_config


def test_generate_tmux_config():
    config = generate_tmux_config()
    assert "nagare pick" in config
    assert "nagare notifs" in config
    assert "display-popup" in config
    assert "bind" in config
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/nagare/setup.py
from pathlib import Path

from nagare.config import NagareConfig, load_config, CONFIG_PATH

DATA_DIR = Path.home() / ".local" / "share" / "nagare"


def generate_tmux_config(config: NagareConfig | None = None) -> str:
    if config is None:
        config = load_config()
    return (
        "# nagare - Claude Code session manager\n"
        f'bind g display-popup -w{config.picker_width} -h{config.picker_height} -E "nagare pick"\n'
        'bind n display-popup -w60% -h60% -E "nagare notifs"\n'
    )


def run_setup() -> None:
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "[notifications]\n"
            "backend = \"tmux\"\n"
            "duration = 2000\n"
            "poll_interval = 3\n"
            "\n"
            "[picker]\n"
            "popup_width = \"80%\"\n"
            "popup_height = \"80%\"\n"
        )
        print(f"Created config: {config_path}")
    else:
        print(f"Config already exists: {config_path}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Data directory: {DATA_DIR}")

    print("\nAdd these lines to your ~/.tmux.conf:\n")
    print(generate_tmux_config())
    print("Then reload tmux config: tmux source-file ~/.tmux.conf")
```

```python
# src/nagare/__init__.py
import os
import sys


def main() -> None:
    if not os.environ.get("COLORTERM"):
        os.environ["COLORTERM"] = "truecolor"

    args = sys.argv[1:]
    command = args[0] if args else "pick"

    if command == "pick":
        from nagare.pick import PickerApp
        app = PickerApp()
        app.run()
    elif command == "notifs":
        from nagare.notifs import NotifsApp
        app = NotifsApp()
        app.run()
    elif command == "daemon":
        from nagare.daemon import run_daemon
        run_daemon()
    elif command == "setup":
        from nagare.setup import run_setup
        run_setup()
    else:
        print(f"Unknown command: {command}")
        print("Usage: nagare [pick|notifs|daemon|setup]")
        sys.exit(1)
```

Update `pyproject.toml` — no changes needed since `nagare = "nagare:main"` already points to the right entry point.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 1 PASSED

**Step 5: Commit**

```bash
git add src/nagare/__init__.py src/nagare/setup.py tests/test_cli.py
git commit -m "feat: CLI entry point with pick, notifs, daemon, setup commands"
```

---

### Task 8: Cleanup Old Code

**Files:**
- Delete: `src/nagare/app.py`
- Delete: `src/nagare/nagare.tcss`
- Delete: `src/nagare/transport/__init__.py`
- Delete: `src/nagare/transport/base.py`
- Delete: `src/nagare/transport/keys.py`
- Delete: `src/nagare/transport/polling.py`
- Delete: `src/nagare/widgets/__init__.py`
- Delete: `src/nagare/widgets/footer_bar.py`
- Delete: `src/nagare/widgets/session_detail.py`
- Delete: `src/nagare/widgets/session_list.py`
- Delete: `src/nagare/widgets/terminal_view.py`
- Delete: `src/nagare/widgets/theme_picker.py`
- Delete: `src/nagare/tmux/capture.py`
- Delete: `tests/test_app.py`
- Delete: `tests/test_integration.py`
- Delete: `tests/test_capture.py`
- Delete: `tests/test_footer_bar.py`
- Delete: `tests/test_session_detail.py`
- Delete: `tests/test_session_list.py`
- Delete: `tests/test_terminal_view.py`
- Delete: `tests/test_keys.py`
- Delete: `tests/test_polling_transport.py`

**Step 1: Delete old files**

```bash
rm -f src/nagare/app.py src/nagare/nagare.tcss
rm -rf src/nagare/transport/
rm -rf src/nagare/widgets/
rm -f src/nagare/tmux/capture.py
rm -f tests/test_app.py tests/test_integration.py tests/test_capture.py
rm -f tests/test_footer_bar.py tests/test_session_detail.py tests/test_session_list.py
rm -f tests/test_terminal_view.py tests/test_keys.py tests/test_polling_transport.py
```

**Step 2: Run all tests to verify nothing is broken**

Run: `uv run pytest tests/ -v`
Expected: All new tests pass, no imports from deleted modules

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove v1 standalone TUI code (app, transport, widgets)"
```

---

### Task 9: End-to-End Smoke Test

**Step 1: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass.

**Step 2: Test setup command**

```bash
uv run nagare setup
```

Expected: Creates config, prints tmux keybindings.

**Step 3: Test picker manually**

```bash
uv run nagare pick
```

Expected: Shows session picker with fuzzy search. Escape to exit.

**Step 4: Test notification center manually**

```bash
uv run nagare notifs
```

Expected: Shows empty notification list. Escape to exit.

**Step 5: Test daemon briefly**

```bash
uv run nagare daemon &
sleep 5
kill %1
```

Expected: Daemon starts, polls sessions, exits cleanly on SIGTERM.

**Step 6: Commit any fixes from smoke testing**

```bash
git add -A
git commit -m "fix: smoke test adjustments"
```
