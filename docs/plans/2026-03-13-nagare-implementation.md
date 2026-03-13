# nagare TUI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a full-screen Textual TUI that auto-discovers Claude Code sessions in tmux and lets you preview/attach to them without leaving the app.

**Architecture:** Two-layer design — `tmux/` module handles all subprocess calls to tmux (discovery, capture, attach), `widgets/` module handles all Textual rendering. `models.py` is the shared data contract. `app.py` wires everything together with a polling timer.

**Tech Stack:** Python 3.14+, uv, Textual (TUI framework), Rich (ANSI rendering)

**Design doc:** `docs/plans/2026-03-13-nagare-tui-design.md`

---

### Task 1: Project Setup & Dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `main.py`
- Create: `src/nagare/__init__.py`

**Step 1: Update pyproject.toml**

Replace the contents of `pyproject.toml` with:

```toml
[project]
name = "nagare"
version = "0.1.0"
description = "Agent manager TUI for Claude Code sessions in tmux"
readme = "README.md"
requires-python = ">=3.14"
dependencies = [
    "textual>=3.0.0",
]

[project.scripts]
nagare = "nagare:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/nagare"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Step 2: Install dependencies**

Run: `uv add textual && uv add --dev pytest pytest-asyncio textual-dev`

**Step 3: Create package init**

Create `src/nagare/__init__.py`:

```python
from nagare.app import NagareApp


def main() -> None:
    app = NagareApp()
    app.run()
```

**Step 4: Update main.py**

Replace `main.py` with:

```python
from nagare import main

if __name__ == "__main__":
    main()
```

**Step 5: Create empty placeholder files**

Create these empty files so imports don't break as we build:
- `src/nagare/models.py`
- `src/nagare/tmux/__init__.py`
- `src/nagare/tmux/scanner.py`
- `src/nagare/tmux/capture.py`
- `src/nagare/tmux/attach.py`
- `src/nagare/widgets/__init__.py`
- `src/nagare/widgets/session_list.py`
- `src/nagare/widgets/preview_pane.py`
- `src/nagare/widgets/footer_bar.py`
- `src/nagare/app.py` (minimal: `from textual.app import App; class NagareApp(App): pass`)
- `tests/__init__.py`

**Step 6: Verify setup**

Run: `uv run python -c "from nagare import main; print('OK')"`
Expected: `OK`

**Step 7: Commit**

```bash
git add pyproject.toml main.py src/ tests/ uv.lock
git commit -m "feat: project setup with textual dependency and package structure"
```

---

### Task 2: Session Model

**Files:**
- Create: `src/nagare/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
from nagare.models import Session, SessionStatus


def test_session_creation():
    session = Session(
        name="my-project",
        session_id="$1",
        path="/home/user/projects/my-project",
        pane_index=0,
        status=SessionStatus.ALIVE,
    )
    assert session.name == "my-project"
    assert session.session_id == "$1"
    assert session.path == "/home/user/projects/my-project"
    assert session.pane_index == 0
    assert session.status == SessionStatus.ALIVE


def test_session_display_name():
    session = Session(
        name="my-project",
        session_id="$1",
        path="/home/user/projects/my-project",
        pane_index=0,
        status=SessionStatus.ALIVE,
    )
    assert session.display == "● my-project"


def test_session_status_icons():
    alive = Session(name="a", session_id="$1", path="/tmp", pane_index=0, status=SessionStatus.ALIVE)
    dead = Session(name="b", session_id="$2", path="/tmp", pane_index=0, status=SessionStatus.DEAD)

    assert alive.status_icon == "●"
    assert dead.status_icon == "○"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/models.py`:

```python
from dataclasses import dataclass
from enum import Enum


class SessionStatus(Enum):
    ALIVE = "alive"
    DEAD = "dead"


STATUS_ICONS: dict[SessionStatus, str] = {
    SessionStatus.ALIVE: "●",
    SessionStatus.DEAD: "○",
}


@dataclass(frozen=True)
class Session:
    name: str
    session_id: str
    path: str
    pane_index: int
    status: SessionStatus

    @property
    def status_icon(self) -> str:
        return STATUS_ICONS[self.status]

    @property
    def display(self) -> str:
        return f"{self.status_icon} {self.name}"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/nagare/models.py tests/test_models.py
git commit -m "feat: add Session model with status tracking"
```

---

### Task 3: tmux Session Scanner

**Files:**
- Create: `src/nagare/tmux/scanner.py`
- Create: `tests/test_scanner.py`

**Step 1: Write the failing test**

Create `tests/test_scanner.py`:

```python
from unittest.mock import patch
from nagare.tmux.scanner import scan_sessions, _parse_sessions, _find_claude_pane
from nagare.models import Session, SessionStatus


def test_parse_sessions():
    raw = "my-project:$1:/home/user/projects/my-project\nother:$2:/home/user/other"
    result = _parse_sessions(raw)
    assert result == [
        ("my-project", "$1", "/home/user/projects/my-project"),
        ("other", "$2", "/home/user/other"),
    ]


def test_parse_sessions_empty():
    assert _parse_sessions("") == []


def test_find_claude_pane_found():
    pane_output = "0:zsh\n1:claude\n2:zsh"
    assert _find_claude_pane(pane_output) == 1


def test_find_claude_pane_not_found():
    pane_output = "0:zsh\n1:vim"
    assert _find_claude_pane(pane_output) is None


@patch("nagare.tmux.scanner._run_tmux")
def test_scan_sessions(mock_run):
    mock_run.side_effect = [
        # list-sessions
        "proj-a:$1:/home/user/a\nproj-b:$2:/home/user/b",
        # list-panes for proj-a — has claude
        "0:claude",
        # list-panes for proj-b — no claude
        "0:zsh",
    ]
    sessions = scan_sessions()
    assert len(sessions) == 1
    assert sessions[0] == Session(
        name="proj-a",
        session_id="$1",
        path="/home/user/a",
        pane_index=0,
        status=SessionStatus.ALIVE,
    )
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/tmux/scanner.py`:

```python
import subprocess

from nagare.models import Session, SessionStatus


def _run_tmux(*args: str) -> str:
    result = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _parse_sessions(raw: str) -> list[tuple[str, str, str]]:
    if not raw:
        return []
    sessions = []
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            sessions.append((parts[0], parts[1], parts[2]))
    return sessions


def _find_claude_pane(pane_output: str) -> int | None:
    for line in pane_output.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[1].strip() == "claude":
            return int(parts[0])
    return None


def scan_sessions() -> list[Session]:
    raw = _run_tmux("list-sessions", "-F", "#{session_name}:#{session_id}:#{session_path}")
    parsed = _parse_sessions(raw)
    sessions = []
    for name, session_id, path in parsed:
        pane_output = _run_tmux("list-panes", "-t", name, "-F", "#{pane_index}:#{pane_current_command}")
        pane_index = _find_claude_pane(pane_output)
        if pane_index is not None:
            sessions.append(Session(
                name=name,
                session_id=session_id,
                path=path,
                pane_index=pane_index,
                status=SessionStatus.ALIVE,
            ))
    return sessions
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scanner.py -v`
Expected: 4 passed

**Step 5: Smoke test against live tmux**

Run: `uv run python -c "from nagare.tmux.scanner import scan_sessions; print(scan_sessions())"`
Expected: List of Session objects matching your running Claude Code sessions

**Step 6: Commit**

```bash
git add src/nagare/tmux/scanner.py tests/test_scanner.py
git commit -m "feat: tmux session scanner with claude process detection"
```

---

### Task 4: Pane Capture

**Files:**
- Create: `src/nagare/tmux/capture.py`
- Create: `tests/test_capture.py`

**Step 1: Write the failing test**

Create `tests/test_capture.py`:

```python
from unittest.mock import patch
from nagare.tmux.capture import capture_pane


@patch("nagare.tmux.capture._run_tmux")
def test_capture_pane(mock_run):
    mock_run.return_value = "line 1\nline 2\nline 3"
    result = capture_pane("my-session", 0)
    assert result == "line 1\nline 2\nline 3"
    mock_run.assert_called_once_with("capture-pane", "-t", "my-session:0", "-p", "-e")


@patch("nagare.tmux.capture._run_tmux")
def test_capture_pane_empty(mock_run):
    mock_run.return_value = ""
    result = capture_pane("my-session", 0)
    assert result == ""
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_capture.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/tmux/capture.py`:

```python
import subprocess


def _run_tmux(*args: str) -> str:
    result = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def capture_pane(session_name: str, pane_index: int) -> str:
    return _run_tmux("capture-pane", "-t", f"{session_name}:{pane_index}", "-p", "-e")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_capture.py -v`
Expected: 2 passed

**Step 5: Smoke test against live tmux**

Run: `uv run python -c "from nagare.tmux.capture import capture_pane; print(capture_pane('mugen', 0)[-200:])"`
Expected: Last 200 chars of the mugen session's visible pane content

**Step 6: Commit**

```bash
git add src/nagare/tmux/capture.py tests/test_capture.py
git commit -m "feat: tmux pane capture with ANSI support"
```

---

### Task 5: tmux Attach Helper

**Files:**
- Create: `src/nagare/tmux/attach.py`
- Create: `tests/test_attach.py`

**Step 1: Write the failing test**

Create `tests/test_attach.py`:

```python
from unittest.mock import patch, call
from nagare.tmux.attach import attach_session


@patch("nagare.tmux.attach.subprocess.run")
def test_attach_session(mock_run):
    attach_session("my-project")
    mock_run.assert_called_once_with(["tmux", "attach-session", "-t", "my-project"])
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_attach.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/tmux/attach.py`:

```python
import subprocess


def attach_session(session_name: str) -> None:
    subprocess.run(["tmux", "attach-session", "-t", session_name])
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_attach.py -v`
Expected: 1 passed

**Step 5: Commit**

```bash
git add src/nagare/tmux/attach.py tests/test_attach.py
git commit -m "feat: tmux attach helper"
```

---

### Task 6: Refactor — Extract shared _run_tmux

**Files:**
- Modify: `src/nagare/tmux/__init__.py`
- Modify: `src/nagare/tmux/scanner.py`
- Modify: `src/nagare/tmux/capture.py`

Both `scanner.py` and `capture.py` define their own `_run_tmux`. Extract it to `tmux/__init__.py`.

**Step 1: Move _run_tmux to tmux/__init__.py**

Write `src/nagare/tmux/__init__.py`:

```python
import subprocess


def run_tmux(*args: str) -> str:
    result = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
```

**Step 2: Update scanner.py**

Remove the `_run_tmux` function. Replace `_run_tmux` calls with:

```python
from nagare.tmux import run_tmux
```

Use `run_tmux` instead of `_run_tmux` throughout.

**Step 3: Update capture.py**

Remove the `_run_tmux` function. Replace with:

```python
from nagare.tmux import run_tmux
```

Use `run_tmux` instead of `_run_tmux`.

**Step 4: Update test mocks**

In `tests/test_scanner.py`, change mock path:
```python
@patch("nagare.tmux.scanner.run_tmux")
```

In `tests/test_capture.py`, change mock path:
```python
@patch("nagare.tmux.capture.run_tmux")
```

**Step 5: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/nagare/tmux/__init__.py src/nagare/tmux/scanner.py src/nagare/tmux/capture.py tests/test_scanner.py tests/test_capture.py
git commit -m "refactor: extract shared run_tmux to tmux package init"
```

---

### Task 7: Session List Widget

**Files:**
- Create: `src/nagare/widgets/session_list.py`
- Create: `tests/test_session_list.py`

**Step 1: Write the failing test**

Create `tests/test_session_list.py`:

```python
from textual.app import App, ComposeResult
from nagare.widgets.session_list import SessionList
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.ALIVE),
    Session(name="proj-b", session_id="$2", path="/home/user/b", pane_index=1, status=SessionStatus.DEAD),
]


class SessionListApp(App):
    def compose(self) -> ComposeResult:
        yield SessionList()


async def test_session_list_renders():
    app = SessionListApp()
    async with app.run_test() as pilot:
        widget = app.query_one(SessionList)
        widget.update_sessions(MOCK_SESSIONS)
        await pilot.pause()
        assert widget.child_count == 2


async def test_session_list_selection():
    app = SessionListApp()
    async with app.run_test() as pilot:
        widget = app.query_one(SessionList)
        widget.update_sessions(MOCK_SESSIONS)
        await pilot.pause()
        assert widget.selected_session == MOCK_SESSIONS[0]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_list.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/widgets/session_list.py`:

```python
from textual.widgets import ListView, ListItem, Label
from textual.message import Message

from nagare.models import Session


class SessionList(ListView):

    class SessionHighlighted(Message):
        def __init__(self, session: Session) -> None:
            super().__init__()
            self.session = session

    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[Session] = []

    @property
    def selected_session(self) -> Session | None:
        if self.index is not None and self._sessions:
            return self._sessions[self.index]
        return None

    def update_sessions(self, sessions: list[Session]) -> None:
        prev_name = self.selected_session.name if self.selected_session else None
        self._sessions = sessions
        self.clear()
        for session in sessions:
            self.append(ListItem(Label(f"{session.display}  [dim]{session.path}[/dim]")))
        # Restore selection by name
        if prev_name:
            for i, s in enumerate(sessions):
                if s.name == prev_name:
                    self.index = i
                    break

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        session = self.selected_session
        if session:
            self.post_message(self.SessionHighlighted(session))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_session_list.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add src/nagare/widgets/session_list.py tests/test_session_list.py
git commit -m "feat: session list widget with selection tracking"
```

---

### Task 8: Preview Pane Widget

**Files:**
- Create: `src/nagare/widgets/preview_pane.py`
- Create: `tests/test_preview_pane.py`

**Step 1: Write the failing test**

Create `tests/test_preview_pane.py`:

```python
from textual.app import App, ComposeResult
from nagare.widgets.preview_pane import PreviewPane


class PreviewApp(App):
    def compose(self) -> ComposeResult:
        yield PreviewPane()


async def test_preview_pane_update():
    app = PreviewApp()
    async with app.run_test() as pilot:
        pane = app.query_one(PreviewPane)
        pane.update_content("hello\nworld")
        await pilot.pause()
        # Widget should exist and not raise
        assert pane is not None


async def test_preview_pane_empty():
    app = PreviewApp()
    async with app.run_test() as pilot:
        pane = app.query_one(PreviewPane)
        pane.update_content("")
        await pilot.pause()
        assert pane is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_preview_pane.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/widgets/preview_pane.py`:

```python
from rich.text import Text
from textual.widgets import RichLog


class PreviewPane(RichLog):

    def __init__(self) -> None:
        super().__init__(wrap=False, highlight=False, markup=False)

    def update_content(self, raw_output: str) -> None:
        self.clear()
        if raw_output:
            rendered = Text.from_ansi(raw_output)
            self.write(rendered)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_preview_pane.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add src/nagare/widgets/preview_pane.py tests/test_preview_pane.py
git commit -m "feat: preview pane widget with ANSI rendering"
```

---

### Task 9: Footer Bar Widget

**Files:**
- Create: `src/nagare/widgets/footer_bar.py`
- Create: `tests/test_footer_bar.py`

**Step 1: Write the failing test**

Create `tests/test_footer_bar.py`:

```python
from textual.app import App, ComposeResult
from nagare.widgets.footer_bar import FooterBar


class FooterApp(App):
    def compose(self) -> ComposeResult:
        yield FooterBar()


async def test_footer_renders():
    app = FooterApp()
    async with app.run_test() as pilot:
        footer = app.query_one(FooterBar)
        assert footer is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_footer_bar.py -v`
Expected: FAIL (ImportError)

**Step 3: Write implementation**

Create `src/nagare/widgets/footer_bar.py`:

```python
from textual.widgets import Static


class FooterBar(Static):

    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 2;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        content = (
            "[b]↑/k[/b] Up  [b]↓/j[/b] Down  [b]Enter[/b] Attach  [b]r[/b] Refresh  [b]q[/b] Quit\n"
            "Detach from session: [b]Ctrl+b d[/b]"
        )
        super().__init__(content)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_footer_bar.py -v`
Expected: 1 passed

**Step 5: Commit**

```bash
git add src/nagare/widgets/footer_bar.py tests/test_footer_bar.py
git commit -m "feat: footer bar widget with keybinding hints"
```

---

### Task 10: Main App — Wire Everything Together

**Files:**
- Create: `src/nagare/app.py`
- Create: `src/nagare/nagare.tcss`
- Create: `tests/test_app.py`

**Step 1: Write the failing test**

Create `tests/test_app.py`:

```python
from unittest.mock import patch
from nagare.app import NagareApp
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.ALIVE),
]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.capture_pane", return_value="hello from pane")
async def test_app_launches(mock_capture, mock_scan):
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # App should have session list and preview pane
        from nagare.widgets.session_list import SessionList
        from nagare.widgets.preview_pane import PreviewPane
        from nagare.widgets.footer_bar import FooterBar
        assert app.query_one(SessionList) is not None
        assert app.query_one(PreviewPane) is not None
        assert app.query_one(FooterBar) is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL (ImportError)

**Step 3: Write the CSS file**

Create `src/nagare/nagare.tcss`:

```css
Screen {
    layout: horizontal;
}

SessionList {
    width: 30%;
    border-right: solid $accent;
}

PreviewPane {
    width: 70%;
}

FooterBar {
    dock: bottom;
    width: 100%;
}
```

**Step 4: Write the app**

Create `src/nagare/app.py`:

```python
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from nagare.models import Session
from nagare.tmux.scanner import scan_sessions
from nagare.tmux.capture import capture_pane
from nagare.tmux.attach import attach_session
from nagare.widgets.session_list import SessionList
from nagare.widgets.preview_pane import PreviewPane
from nagare.widgets.footer_bar import FooterBar


class NagareApp(App):
    CSS_PATH = "nagare.tcss"
    TITLE = "nagare"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "attach_session", "Attach"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield SessionList()
        yield PreviewPane()
        yield FooterBar()

    def on_mount(self) -> None:
        self._refresh_sessions()
        self.set_interval(3, self._refresh_sessions)

    def _refresh_sessions(self) -> None:
        sessions = scan_sessions()
        session_list = self.query_one(SessionList)
        session_list.update_sessions(sessions)
        # Update preview for current selection
        self._update_preview(session_list.selected_session)

    def _update_preview(self, session: Session | None) -> None:
        preview = self.query_one(PreviewPane)
        if session is None:
            preview.update_content("No sessions found.")
            return
        content = capture_pane(session.name, session.pane_index)
        preview.update_content(content)

    def on_session_list_session_highlighted(self, event: SessionList.SessionHighlighted) -> None:
        self._update_preview(event.session)

    def action_refresh(self) -> None:
        self._refresh_sessions()

    def action_attach_session(self) -> None:
        session_list = self.query_one(SessionList)
        session = session_list.selected_session
        if session is None:
            return
        with self.suspend():
            attach_session(session.name)
        self._refresh_sessions()

    def action_cursor_down(self) -> None:
        self.query_one(SessionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(SessionList).action_cursor_up()
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py -v`
Expected: 1 passed

**Step 6: Commit**

```bash
git add src/nagare/app.py src/nagare/nagare.tcss tests/test_app.py
git commit -m "feat: main NagareApp wiring session list, preview, and attach flow"
```

---

### Task 11: Update Package Init & Entry Point

**Files:**
- Modify: `src/nagare/__init__.py`
- Modify: `main.py`
- Modify: `src/nagare/widgets/__init__.py`
- Modify: `src/nagare/tmux/__init__.py`

**Step 1: Finalize src/nagare/__init__.py**

This was done in Task 1 but verify it has:

```python
from nagare.app import NagareApp


def main() -> None:
    app = NagareApp()
    app.run()
```

**Step 2: Verify main.py**

Should be:

```python
from nagare import main

if __name__ == "__main__":
    main()
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 4: Manual smoke test**

Run: `uv run nagare`
Expected: Full-screen TUI launches showing your active Claude Code sessions on the left, preview on the right, footer at the bottom. Arrow keys / j/k navigate. Enter attaches. q quits.

**Step 5: Commit if any changes**

```bash
git add -A
git commit -m "feat: finalize entry point and package wiring"
```

---

### Task 12: End-to-End Integration Test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

Create `tests/test_integration.py`:

```python
from unittest.mock import patch
from nagare.app import NagareApp
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.ALIVE),
    Session(name="proj-b", session_id="$2", path="/home/user/b", pane_index=0, status=SessionStatus.ALIVE),
]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.capture_pane", return_value="mock pane content")
async def test_navigate_sessions(mock_capture, mock_scan):
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from nagare.widgets.session_list import SessionList
        session_list = app.query_one(SessionList)

        # Initial selection is first session
        assert session_list.selected_session == MOCK_SESSIONS[0]

        # Navigate down
        await pilot.press("j")
        await pilot.pause()
        assert session_list.selected_session == MOCK_SESSIONS[1]

        # Navigate back up
        await pilot.press("k")
        await pilot.pause()
        assert session_list.selected_session == MOCK_SESSIONS[0]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.capture_pane", return_value="mock pane content")
async def test_quit(mock_capture, mock_scan):
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.pause()
        # App should have exited
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_integration.py -v`
Expected: 2 passed

**Step 3: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration tests for navigation and quit"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Project setup & deps | pyproject.toml, main.py, package structure |
| 2 | Session model | models.py |
| 3 | tmux session scanner | tmux/scanner.py |
| 4 | Pane capture | tmux/capture.py |
| 5 | Attach helper | tmux/attach.py |
| 6 | Refactor shared run_tmux | tmux/__init__.py |
| 7 | Session list widget | widgets/session_list.py |
| 8 | Preview pane widget | widgets/preview_pane.py |
| 9 | Footer bar widget | widgets/footer_bar.py |
| 10 | Main app wiring | app.py, nagare.tcss |
| 11 | Entry point finalization | __init__.py, main.py |
| 12 | Integration tests | test_integration.py |
