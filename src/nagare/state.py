"""Read session state files written by Claude Code hooks."""

import json
from dataclasses import dataclass
from pathlib import Path

STATES_DIR = Path.home() / ".local" / "share" / "nagare" / "states"


@dataclass(frozen=True)
class SessionState:
    state: str  # working, waiting_input, idle, dead, unknown
    session_id: str
    cwd: str
    event: str
    notification_type: str
    last_message: str
    timestamp: str


def load_all_states() -> dict[str, SessionState]:
    """Load all state files, keyed by cwd (project path)."""
    states: dict[str, SessionState] = {}
    if not STATES_DIR.exists():
        return states

    for f in STATES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            st = SessionState(
                state=data.get("state", "unknown"),
                session_id=data.get("session_id", ""),
                cwd=data.get("cwd", ""),
                event=data.get("event", ""),
                notification_type=data.get("notification_type", ""),
                last_message=data.get("last_message", ""),
                timestamp=data.get("timestamp", ""),
            )
            if st.cwd:
                states[st.cwd] = st
        except (OSError, json.JSONDecodeError):
            continue

    return states
