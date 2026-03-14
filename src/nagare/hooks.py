"""Hook handler for Claude Code lifecycle events.

Called by Claude Code hooks via: nagare hook-state
Reads JSON from stdin, writes a state file to ~/.local/share/nagare/states/<session_id>.json
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATES_DIR = Path.home() / ".local" / "share" / "nagare" / "states"


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


def _event_to_state(event: str, data: dict) -> str:
    if event == "UserPromptSubmit":
        return "working"
    elif event == "PreToolUse":
        return "working"
    elif event == "Stop":
        return "idle"
    elif event == "Notification":
        ntype = data.get("notification_type", "")
        if ntype in ("permission_prompt", "elicitation_dialog"):
            return "waiting_input"
        elif ntype == "idle_prompt":
            return "idle"
        return "idle"
    elif event == "SessionEnd":
        return "dead"
    elif event == "SessionStart":
        return "idle"
    return "unknown"
