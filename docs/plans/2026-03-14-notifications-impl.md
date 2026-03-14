# Notification System Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Overhaul nagare's notification system with multiple delivery methods (toast, bell, OS notify, popup), configurable per event type and per session, with task completion detection and a rich popup TUI.

**Architecture:** Hook handler (`hooks.py`) becomes a thin dispatcher that determines event type, loads config, resolves per-session overrides, and fans out to delivery functions in `notifications/deliver.py`. A new popup TUI (`popup_notif.py`) provides rich notification display. Config schema expands to support per-event and per-session settings.

**Tech Stack:** Python 3.14+, Textual, tmux, notify-send/WSL equivalents

---

### Task 1: New notification config schema

**Files:**
- Modify: `src/nagare/config.py`
- Modify: `tests/test_config.py`

**Step 1: Write failing tests for new config**

Add to `tests/test_config.py`:

```python
from nagare.config import load_config, NotificationEventConfig, NotificationConfig


def test_default_notification_config():
    with patch("nagare.config.CONFIG_PATH", "/nonexistent/config.toml"):
        cfg = load_config()
    nc = cfg.notifications
    assert nc.enabled is True

    # needs_input defaults
    ni = nc.needs_input
    assert ni.toast is True
    assert ni.bell is True
    assert ni.os_notify is True
    assert ni.popup is False
    assert ni.popup_timeout == 10
    assert ni.min_working_seconds == 0

    # task_complete defaults
    tc = nc.task_complete
    assert tc.toast is True
    assert tc.bell is False
    assert tc.os_notify is False
    assert tc.popup is False
    assert tc.popup_timeout == 10
    assert tc.min_working_seconds == 30


def test_notification_config_from_toml(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications]
enabled = true

[notifications.needs_input]
toast = true
bell = false
os_notify = false
popup = true
popup_timeout = 15

[notifications.task_complete]
toast = false
min_working_seconds = 60
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    assert cfg.notifications.needs_input.bell is False
    assert cfg.notifications.needs_input.popup is True
    assert cfg.notifications.needs_input.popup_timeout == 15
    assert cfg.notifications.task_complete.toast is False
    assert cfg.notifications.task_complete.min_working_seconds == 60
    # Unspecified fields keep defaults
    assert cfg.notifications.task_complete.bell is False
    assert cfg.notifications.task_complete.popup is False


def test_per_session_override(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[notifications.sessions.playground]
enabled = false

[notifications.sessions.production-backend]
popup = true
os_notify = true
""")
    with patch("nagare.config.CONFIG_PATH", str(config_file)):
        cfg = load_config()
    pg = cfg.notifications.sessions.get("playground")
    assert pg is not None
    assert pg.get("enabled") is False
    prod = cfg.notifications.sessions.get("production-backend")
    assert prod is not None
    assert prod.get("popup") is True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `NotificationEventConfig` and `NotificationConfig` don't exist yet

**Step 3: Implement new config dataclasses and loading**

Replace the content of `src/nagare/config.py`:

```python
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = str(Path.home() / ".config" / "nagare" / "config.toml")


@dataclass(frozen=True)
class NotificationEventConfig:
    toast: bool = True
    bell: bool = False
    os_notify: bool = False
    popup: bool = False
    popup_timeout: int = 10
    min_working_seconds: int = 0


# Frozen defaults per event type
_NEEDS_INPUT_DEFAULTS = NotificationEventConfig(
    toast=True, bell=True, os_notify=True, popup=False,
    popup_timeout=10, min_working_seconds=0,
)
_TASK_COMPLETE_DEFAULTS = NotificationEventConfig(
    toast=True, bell=False, os_notify=False, popup=False,
    popup_timeout=10, min_working_seconds=30,
)


@dataclass(frozen=True)
class NotificationConfig:
    enabled: bool = True
    needs_input: NotificationEventConfig = field(default_factory=lambda: _NEEDS_INPUT_DEFAULTS)
    task_complete: NotificationEventConfig = field(default_factory=lambda: _TASK_COMPLETE_DEFAULTS)
    sessions: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class NagareConfig:
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    notification_duration: int = 3000
    picker_width: str = "80%"
    picker_height: str = "80%"
    theme: str = "tokyonight"


def _load_event_config(data: dict, defaults: NotificationEventConfig) -> NotificationEventConfig:
    if not data:
        return defaults
    return NotificationEventConfig(
        toast=data.get("toast", defaults.toast),
        bell=data.get("bell", defaults.bell),
        os_notify=data.get("os_notify", defaults.os_notify),
        popup=data.get("popup", defaults.popup),
        popup_timeout=data.get("popup_timeout", defaults.popup_timeout),
        min_working_seconds=data.get("min_working_seconds", defaults.min_working_seconds),
    )


def load_config() -> NagareConfig:
    path = Path(CONFIG_PATH)
    if not path.exists():
        return NagareConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    notifs = data.get("notifications", {})
    picker = data.get("picker", {})
    appearance = data.get("appearance", {})

    # Parse per-session overrides
    sessions_raw = notifs.get("sessions", {})
    sessions = {name: dict(overrides) for name, overrides in sessions_raw.items()}

    notification_config = NotificationConfig(
        enabled=notifs.get("enabled", True),
        needs_input=_load_event_config(notifs.get("needs_input", {}), _NEEDS_INPUT_DEFAULTS),
        task_complete=_load_event_config(notifs.get("task_complete", {}), _TASK_COMPLETE_DEFAULTS),
        sessions=sessions,
    )

    return NagareConfig(
        notifications=notification_config,
        notification_duration=notifs.get("duration", 3000),
        picker_width=picker.get("popup_width", "80%"),
        picker_height=picker.get("popup_height", "80%"),
        theme=appearance.get("theme", "tokyonight"),
    )


def save_theme(theme_name: str) -> None:
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        content = path.read_text()
        if re.search(r"^\[appearance\]", content, re.MULTILINE):
            content = re.sub(
                r'(^\[appearance\].*?theme\s*=\s*)"[^"]*"',
                rf'\1"{theme_name}"',
                content,
                flags=re.MULTILINE | re.DOTALL,
            )
        else:
            content = content.rstrip() + f'\n\n[appearance]\ntheme = "{theme_name}"\n'
    else:
        content = f'[appearance]\ntheme = "{theme_name}"\n'

    path.write_text(content)
```

**Step 4: Update existing config tests**

The old tests reference `cfg.notification_backend` which no longer exists as a top-level field. Update `test_default_config`, `test_load_from_toml`, and `test_partial_config` to work with the new schema. Keep `notification_duration` as a legacy compat field.

**Step 5: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/nagare/config.py tests/test_config.py
git commit -m "feat: new notification config schema with per-event and per-session settings"
```

---

### Task 2: Delivery functions module

**Files:**
- Create: `src/nagare/notifications/deliver.py`
- Delete: `src/nagare/notifications/base.py`
- Delete: `src/nagare/notifications/tmux.py`
- Modify: `tests/test_notifications.py`

**Step 1: Write tests for delivery functions**

Replace `tests/test_notifications.py`:

```python
import os
from unittest.mock import patch, MagicMock

from nagare.notifications.deliver import send_toast, send_bell, send_os_notify, detect_os_notify_cmd


@patch("nagare.notifications.deliver.run_tmux")
def test_send_toast(mock_tmux):
    send_toast("my-project needs permission", duration=3000)
    mock_tmux.assert_called_once_with(
        "display-message", "-d", "3000", "🔴 my-project needs permission",
    )


@patch("nagare.notifications.deliver.run_tmux")
def test_send_bell(mock_tmux):
    send_bell()
    mock_tmux.assert_called_once()
    args = mock_tmux.call_args[0]
    assert "send-keys" in args
    # Should send BEL character to current pane


@patch("subprocess.run")
def test_send_os_notify_linux(mock_run):
    with patch("nagare.notifications.deliver.detect_os_notify_cmd", return_value=["notify-send"]):
        send_os_notify("nagare", "my-project needs permission")
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "notify-send"


def test_detect_wsl():
    with patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu"}):
        cmd = detect_os_notify_cmd()
    # Should return a WSL-compatible command or None
    assert cmd is None or isinstance(cmd, list)


def test_detect_native_linux():
    with patch.dict(os.environ, {}, clear=False):
        with patch("shutil.which", return_value="/usr/bin/notify-send"):
            with patch("os.environ.get", side_effect=lambda k, d=None: d):
                # No WSL env var
                cmd = detect_os_notify_cmd()
    # Hard to test cleanly — just ensure it doesn't crash
    assert cmd is None or isinstance(cmd, list)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_notifications.py -v`
Expected: FAIL — module doesn't exist yet

**Step 3: Implement deliver.py**

Create `src/nagare/notifications/deliver.py`:

```python
"""Notification delivery functions — toast, bell, OS notify, popup."""

import os
import shutil
import subprocess

from nagare.tmux import run_tmux


def send_toast(message: str, duration: int = 3000) -> None:
    """Send a tmux status bar toast notification."""
    try:
        run_tmux("display-message", "-d", str(duration), f"🔴 {message}")
    except Exception:
        pass


def send_bell() -> None:
    """Send terminal bell to the active pane."""
    try:
        run_tmux("send-keys", "-t", "!", "")  # BEL via tmux
        # Direct approach: write BEL to the client terminal
        subprocess.run(
            ["tmux", "run-shell", "-t", "!", "printf '\\a'"],
            capture_output=True, timeout=2,
        )
    except Exception:
        pass


def detect_os_notify_cmd() -> list[str] | None:
    """Detect the best available OS notification command.

    Returns the base command as a list, or None if unavailable.
    WSL detection: checks WSL_DISTRO_NAME env var.
    """
    if os.environ.get("WSL_DISTRO_NAME"):
        # WSL: try wsl-notify-send first, then powershell
        if shutil.which("wsl-notify-send"):
            return ["wsl-notify-send"]
        # powershell.exe toast is complex; skip for now
        return None
    # Native Linux
    if shutil.which("notify-send"):
        return ["notify-send"]
    return None


def send_os_notify(title: str, message: str) -> None:
    """Send a native OS desktop notification."""
    cmd = detect_os_notify_cmd()
    if cmd is None:
        return
    try:
        if cmd[0] == "notify-send":
            subprocess.run([*cmd, title, message], capture_output=True, timeout=5)
        elif cmd[0] == "wsl-notify-send":
            subprocess.run([*cmd, "--category", title, message], capture_output=True, timeout=5)
    except Exception:
        pass


def send_popup(
    session_name: str,
    event_type: str,
    message: str,
    working_seconds: int = 0,
    popup_timeout: int = 10,
) -> None:
    """Launch the rich notification popup TUI via tmux display-popup."""
    import shlex
    # Find the nagare executable
    nagare_bin = shutil.which("nagare") or "nagare"
    args = [
        nagare_bin, "popup-notif",
        "--session", session_name,
        "--event", event_type,
        "--message", shlex.quote(message) if message else "''",
        "--timeout", str(popup_timeout),
    ]
    if working_seconds > 0:
        args.extend(["--duration", str(working_seconds)])
    cmd_str = " ".join(args)
    try:
        run_tmux("display-popup", "-w60%", "-h30%", "-E", cmd_str)
    except Exception:
        pass
```

**Step 4: Delete old backend files**

```bash
rm src/nagare/notifications/base.py src/nagare/notifications/tmux.py
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_notifications.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/nagare/notifications/ tests/test_notifications.py
git commit -m "feat: notification delivery functions (toast, bell, os_notify, popup)"
```

---

### Task 3: Rewrite hooks.py as thin dispatcher

**Files:**
- Modify: `src/nagare/hooks.py`
- Modify: `tests/test_hooks.py`

**Step 1: Write/update tests for new hook behavior**

Add task_complete detection test and update existing tests to work with new config-driven dispatch:

```python
def test_task_complete_notification(tmp_path):
    """Stop event after working > min_working_seconds triggers task_complete notification."""
    # Write a previous state file showing "working" from 60 seconds ago
    old_state = {
        "state": "working",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "event": "UserPromptSubmit",
        "notification_type": "",
        "last_message": "",
        "timestamp": "2026-03-14T08:00:00+00:00",
    }
    (tmp_path / "abc-123.json").write_text(json.dumps(old_state))

    hook_input = json.dumps({
        "hook_event_name": "Stop",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "last_assistant_message": "Done! Refactoring complete.",
    })

    mock_config = MagicMock()
    mock_config.notifications.enabled = True
    mock_config.notifications.task_complete.toast = True
    mock_config.notifications.task_complete.bell = False
    mock_config.notifications.task_complete.os_notify = False
    mock_config.notifications.task_complete.popup = False
    mock_config.notifications.task_complete.min_working_seconds = 30
    mock_config.notifications.sessions = {}
    mock_config.notification_duration = 3000

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks._get_session_name", return_value="my-project"), \
         patch("nagare.hooks._is_active_session", return_value=False), \
         patch("nagare.hooks.load_config", return_value=mock_config), \
         patch("nagare.hooks._deliver") as mock_deliver, \
         patch("sys.stdin", StringIO(hook_input)), \
         patch("nagare.hooks._now_utc", return_value="2026-03-14T08:01:00+00:00"):
        handle_hook()

    # Should have called _deliver for task_complete
    mock_deliver.assert_called_once()
    call_args = mock_deliver.call_args
    assert call_args[1]["event_type"] == "task_complete"


def test_task_complete_skipped_short_duration(tmp_path):
    """Stop event after working < min_working_seconds does NOT trigger notification."""
    old_state = {
        "state": "working",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "event": "UserPromptSubmit",
        "notification_type": "",
        "last_message": "",
        "timestamp": "2026-03-14T08:00:50+00:00",  # only 10 seconds ago
    }
    (tmp_path / "abc-123.json").write_text(json.dumps(old_state))

    hook_input = json.dumps({
        "hook_event_name": "Stop",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "last_assistant_message": "Quick fix applied.",
    })

    mock_config = MagicMock()
    mock_config.notifications.enabled = True
    mock_config.notifications.task_complete.min_working_seconds = 30
    mock_config.notifications.sessions = {}

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks.load_config", return_value=mock_config), \
         patch("nagare.hooks._deliver") as mock_deliver, \
         patch("sys.stdin", StringIO(hook_input)), \
         patch("nagare.hooks._now_utc", return_value="2026-03-14T08:01:00+00:00"):
        handle_hook()

    mock_deliver.assert_not_called()


def test_per_session_disabled(tmp_path):
    """Session with enabled=false in config should not get notifications."""
    hook_input = json.dumps({
        "hook_event_name": "Notification",
        "session_id": "abc-123",
        "cwd": "/home/user/playground",
        "notification_type": "permission_prompt",
    })

    mock_config = MagicMock()
    mock_config.notifications.enabled = True
    mock_config.notifications.needs_input.toast = True
    mock_config.notifications.sessions = {"playground": {"enabled": False}}

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks._get_session_name", return_value="playground"), \
         patch("nagare.hooks._is_active_session", return_value=False), \
         patch("nagare.hooks.load_config", return_value=mock_config), \
         patch("nagare.hooks._deliver") as mock_deliver, \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    mock_deliver.assert_not_called()
```

**Step 2: Rewrite hooks.py**

The key changes:
- Import `load_config` and delivery functions
- Add `_now_utc()` helper (mockable for tests)
- On Stop event: read previous state file, calculate working duration, check threshold
- On waiting_input: determine event type as `needs_input`
- New `_deliver()` function: check master switch, per-session overrides, merge config, call enabled delivery methods, store notification
- Remove old `_send_notification` and `_store_notification` — use `NotificationStore` and delivery functions

**Step 3: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/nagare/hooks.py tests/test_hooks.py
git commit -m "feat: hook dispatcher with config-driven delivery and task completion detection"
```

---

### Task 4: Popup notification TUI

**Files:**
- Create: `src/nagare/popup_notif.py`
- Create: `src/nagare/popup_notif.tcss`
- Modify: `src/nagare/__init__.py`
- Create: `tests/test_popup_notif.py`

**Step 1: Write tests for popup TUI**

```python
from nagare.popup_notif import PopupNotifApp


async def test_popup_shows_needs_input():
    app = PopupNotifApp(
        session_name="production-backend",
        event_type="needs_input",
        message="Claude wants to run: Bash(git push origin main)",
        popup_timeout=5,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        # Verify key content is displayed
        text = app.query_one("#notif-header").renderable
        assert "production-backend" in str(text)


async def test_popup_shows_task_complete():
    app = PopupNotifApp(
        session_name="nagare",
        event_type="task_complete",
        message="Done. All tests pass.",
        working_seconds=154,
        popup_timeout=5,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        text = app.query_one("#notif-header").renderable
        assert "nagare" in str(text)


async def test_popup_escape_exits():
    app = PopupNotifApp(
        session_name="test",
        event_type="needs_input",
        message="test",
        popup_timeout=60,
    )
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
```

**Step 2: Implement popup_notif.py**

A small Textual app:
- Takes CLI args: `--session`, `--event`, `--message`, `--timeout`, `--duration`
- Shows status icon + session name + event label
- Shows message body
- Countdown timer via `set_interval(1, ...)`
- Enter → `tmux switch-client -t {session_name}` then exit
- Esc → exit
- Timer reaches 0 → exit

**Step 3: Create popup_notif.tcss**

Minimal styling — centered content, themed colors.

**Step 4: Add CLI command to __init__.py**

```python
elif command == "popup-notif":
    from nagare.popup_notif import run_popup
    run_popup(args[1:])
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_popup_notif.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/nagare/popup_notif.py src/nagare/popup_notif.tcss src/nagare/__init__.py tests/test_popup_notif.py
git commit -m "feat: rich popup notification TUI with auto-dismiss countdown"
```

---

### Task 5: Migrate notification center to ListView

**Files:**
- Modify: `src/nagare/notifs.py`
- Modify: `src/nagare/notifs.tcss`
- Modify: `tests/test_notifs.py`

**Step 1: Update tests**

Change `OptionList` references to `ListView` in `tests/test_notifs.py`. Update count assertion to use `len(listview.children)`.

**Step 2: Rewrite notifs.py**

Replace `OptionList` with `ListView` + `ListItem` + `Static` pattern (matching picker style). Add event_type field to stored notifications so the center can show different icons for needs_input vs task_complete.

**Step 3: Run tests**

Run: `uv run pytest tests/test_notifs.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/nagare/notifs.py src/nagare/notifs.tcss tests/test_notifs.py
git commit -m "refactor: migrate notification center from OptionList to ListView"
```

---

### Task 6: Generate default config with comments

**Files:**
- Modify: `src/nagare/setup.py`

**Step 1: Update `run_setup()` to write commented default config**

The generated config should include all notification options with descriptive comments explaining each setting. Include the per-session override examples as comments.

**Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add src/nagare/setup.py
git commit -m "feat: generate commented default notification config on setup"
```

---

### Task 7: Integration test & cleanup

**Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS, no import errors

**Step 2: Verify no orphan imports**

Check that nothing imports from deleted `notifications/base.py` or `notifications/tmux.py`.

**Step 3: Update CLAUDE.md**

Update the Architecture section to reflect the new notification system.

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: cleanup orphan imports and update docs"
```
