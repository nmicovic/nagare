"""Hook handler for Claude Code lifecycle events.

Called by Claude Code hooks via: nagare hook-state
Reads JSON from stdin, writes a state file, detects task completion,
and dispatches notifications through config-driven delivery.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from nagare.config import load_config, NagareConfig
from nagare.notifications.deliver import send_toast, send_bell, send_os_notify, send_popup
from nagare.notifications.store import NotificationStore

STATES_DIR = Path.home() / ".local" / "share" / "nagare" / "states"
STORE_PATH = Path.home() / ".local" / "share" / "nagare" / "notifications.json"

_NEEDS_INPUT_TYPES = ("permission_prompt", "elicitation_dialog")


def _now_utc() -> str:
    """Return current UTC time as ISO string. Separate for test mocking."""
    return datetime.now(timezone.utc).isoformat()


def _format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if secs:
        return f"{minutes}m {secs}s"
    return f"{minutes}m"


def _build_message(
    session_name: str,
    event_type: str,
    notification_type: str,
    *,
    working_seconds: int = 0,
) -> str:
    """Format a human-readable notification message."""
    if event_type == "needs_input":
        if notification_type == "permission_prompt":
            return f"{session_name} needs permission"
        elif notification_type == "elicitation_dialog":
            return f"{session_name} is asking a question"
        else:
            return f"{session_name} needs your input"
    elif event_type == "task_complete":
        return f"{session_name} finished (worked {_format_duration(working_seconds)})"
    return f"{session_name}: {event_type}"


def _deliver(
    session_name: str,
    event_type: str,
    message: str,
    config: NagareConfig,
    working_seconds: int,
    store_path: Path,
) -> None:
    """Dispatch notification to enabled delivery channels."""
    if not config.notifications.enabled:
        return

    # Per-session overrides
    session_overrides = config.notifications.sessions.get(session_name, {})
    if not session_overrides.get("enabled", True):
        return

    # Get base event config
    if event_type == "needs_input":
        event_cfg = config.notifications.needs_input
    elif event_type == "task_complete":
        event_cfg = config.notifications.task_complete
    else:
        return

    # Apply per-session overrides on top of event config
    toast = session_overrides.get("toast", event_cfg.toast)
    bell = session_overrides.get("bell", event_cfg.bell)
    os_notify = session_overrides.get("os_notify", event_cfg.os_notify)
    popup = session_overrides.get("popup", event_cfg.popup)
    popup_timeout = session_overrides.get("popup_timeout", event_cfg.popup_timeout)

    # Deliver via enabled channels
    if toast:
        send_toast(message, duration=config.notification_duration)
    if bell:
        send_bell()
    if os_notify:
        send_os_notify("nagare", message)
    if popup:
        send_popup(session_name, event_type, message, working_seconds=working_seconds, popup_timeout=popup_timeout)

    # Always persist
    store = NotificationStore(store_path)
    store.add(session_name, message)


def handle_hook() -> None:
    """Read hook JSON from stdin, write state file, and dispatch notifications."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return

    if not raw:
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    event = data.get("hook_event_name", "")
    session_id = data.get("session_id", "")
    cwd = data.get("cwd", "")

    if not session_id:
        return

    state = _event_to_state(event, data)
    last_message = ""
    notification_type = ""

    if event == "Stop":
        last_message = data.get("last_assistant_message", "")
    elif event == "Notification":
        notification_type = data.get("notification_type", "")

    STATES_DIR.mkdir(parents=True, exist_ok=True)

    # Read previous state before overwriting (for task completion detection)
    state_path = STATES_DIR / f"{session_id}.json"
    prev_state_data = None
    if state_path.exists():
        try:
            prev_state_data = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError):
            pass

    # On new session, clean up dead state files for the same cwd
    if event == "SessionStart" and cwd:
        for old in STATES_DIR.glob("*.json"):
            if old.stem == session_id:
                continue
            try:
                old_data = json.loads(old.read_text())
                if old_data.get("cwd") == cwd and old_data.get("state") == "dead":
                    old.unlink()
            except (OSError, json.JSONDecodeError):
                continue

    # Write new state file
    now = _now_utc()
    state_data = {
        "state": state,
        "session_id": session_id,
        "cwd": cwd,
        "event": event,
        "notification_type": notification_type,
        "last_message": last_message,
        "timestamp": now,
    }
    state_path.write_text(json.dumps(state_data))

    # Determine if notification is needed
    try:
        _maybe_notify(state, prev_state_data, now, notification_type, cwd, session_id)
    except Exception:
        pass


def _maybe_notify(
    state: str,
    prev_state_data: dict | None,
    now: str,
    notification_type: str,
    cwd: str,
    session_id: str,
) -> None:
    """Determine event type and dispatch notification if warranted."""
    event_type: str | None = None
    working_seconds = 0

    if state == "waiting_input":
        event_type = "needs_input"
    elif state == "idle" and prev_state_data and prev_state_data.get("state") == "working":
        # Task completion: idle after working
        try:
            old_ts = datetime.fromisoformat(prev_state_data["timestamp"])
            new_ts = datetime.fromisoformat(now)
            working_seconds = int((new_ts - old_ts).total_seconds())
        except (KeyError, ValueError):
            working_seconds = 0

        config = load_config()
        min_secs = config.notifications.task_complete.min_working_seconds
        if working_seconds >= min_secs:
            event_type = "task_complete"

    if event_type is None:
        return

    session_name = _get_session_name(cwd)
    if not session_name:
        session_name = cwd

    if _is_active_session(session_name):
        return

    # Load config (may already be loaded for task_complete path)
    config = load_config()

    message = _build_message(
        session_name, event_type, notification_type, working_seconds=working_seconds,
    )

    _deliver(session_name, event_type, message, config, working_seconds, STORE_PATH)


def _event_to_state(event: str, data: dict) -> str:
    if event == "UserPromptSubmit":
        return "working"
    elif event == "PreToolUse":
        return "working"
    elif event == "Stop":
        return "idle"
    elif event == "Notification":
        ntype = data.get("notification_type", "")
        if ntype in _NEEDS_INPUT_TYPES:
            return "waiting_input"
        return "idle"
    elif event == "SessionEnd":
        return "dead"
    elif event == "SessionStart":
        return "idle"
    return "unknown"


def _get_session_name(cwd: str) -> str | None:
    """Try to get the tmux session name from the cwd."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}:#{session_path}"],
            capture_output=True, text=True, timeout=2,
        )
        for line in result.stdout.splitlines():
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[1] == cwd:
                return parts[0]
    except Exception:
        pass
    return None


def _is_active_session(session_name: str) -> bool:
    """Check if this session is the one the user is currently viewing.

    Uses tmux list-clients instead of display-message because hooks run
    inside the session they're reporting about, so display-message would
    always return that session's name.
    """
    try:
        result = subprocess.run(
            ["tmux", "list-clients", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=2,
        )
        # Any attached client viewing this session means it's active
        active_sessions = result.stdout.strip().splitlines()
        return session_name in active_sessions
    except Exception:
        return False
