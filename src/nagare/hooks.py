"""Hook handler for Claude Code lifecycle events.

Called by Claude Code hooks via: nagare hook-state
Reads JSON from stdin, writes a state file and sends notifications.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATES_DIR = Path.home() / ".local" / "share" / "nagare" / "states"
STORE_PATH = Path.home() / ".local" / "share" / "nagare" / "notifications.json"

_NEEDS_INPUT_TYPES = ("permission_prompt", "elicitation_dialog")


def handle_hook() -> None:
    """Read hook JSON from stdin and write state file."""
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

    # Write state file
    state_data = {
        "state": state,
        "session_id": session_id,
        "cwd": cwd,
        "event": event,
        "notification_type": notification_type,
        "last_message": last_message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    STATES_DIR.mkdir(parents=True, exist_ok=True)
    state_path = STATES_DIR / f"{session_id}.json"
    state_path.write_text(json.dumps(state_data))

    # Send notification for events that need user attention
    if state == "waiting_input":
        session_name = _get_session_name(cwd)
        _send_notification(session_name or cwd, notification_type)


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
    """Check if this session is the one the user is currently viewing."""
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "#{session_name}"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout.strip() == session_name
    except Exception:
        return False


def _send_notification(session_name: str, notification_type: str) -> None:
    """Send notification via tmux display-message and store it."""
    if _is_active_session(session_name):
        return

    if notification_type == "permission_prompt":
        msg = f"{session_name} needs permission"
    elif notification_type == "elicitation_dialog":
        msg = f"{session_name} is asking a question"
    else:
        msg = f"{session_name} needs your input"

    # tmux toast notification (non-dismissable, auto-close after 3s)
    try:
        subprocess.run(
            ["tmux", "display-message", "-d", "3000", "-N", f"🔴 {msg}"],
            capture_output=True, timeout=2,
        )
    except Exception:
        pass

    # Persist to notification store
    _store_notification(session_name, msg)


def _store_notification(session_name: str, message: str) -> None:
    """Append to the JSON notification store."""
    import uuid

    store_path = STORE_PATH
    store_path.parent.mkdir(parents=True, exist_ok=True)

    notifications = []
    if store_path.exists():
        try:
            notifications = json.loads(store_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    notifications.append({
        "id": str(uuid.uuid4()),
        "session_name": session_name,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "read": False,
    })

    store_path.write_text(json.dumps(notifications))
