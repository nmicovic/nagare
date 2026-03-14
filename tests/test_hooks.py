import json
from io import StringIO
from unittest.mock import patch
from pathlib import Path

from nagare.hooks import handle_hook, STATES_DIR, _event_to_state


def test_event_to_state_user_prompt():
    assert _event_to_state("UserPromptSubmit", {}) == "working"


def test_event_to_state_stop():
    assert _event_to_state("Stop", {}) == "idle"


def test_event_to_state_notification_permission():
    assert _event_to_state("Notification", {"notification_type": "permission_prompt"}) == "waiting_input"


def test_event_to_state_notification_idle():
    assert _event_to_state("Notification", {"notification_type": "idle_prompt"}) == "idle"


def test_event_to_state_notification_elicitation():
    assert _event_to_state("Notification", {"notification_type": "elicitation_dialog"}) == "waiting_input"


def test_event_to_state_session_end():
    assert _event_to_state("SessionEnd", {}) == "dead"


def test_event_to_state_pre_tool_use():
    assert _event_to_state("PreToolUse", {}) == "working"


def test_handle_hook_writes_state(tmp_path):
    hook_input = json.dumps({
        "hook_event_name": "Stop",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "last_assistant_message": "Done! All tests pass.",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    state_file = tmp_path / "abc-123.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["state"] == "idle"
    assert data["session_id"] == "abc-123"
    assert data["cwd"] == "/home/user/project"
    assert data["last_message"] == "Done! All tests pass."


def test_handle_hook_working_state(tmp_path):
    hook_input = json.dumps({
        "hook_event_name": "UserPromptSubmit",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    data = json.loads((tmp_path / "abc-123.json").read_text())
    assert data["state"] == "working"


def test_handle_hook_waiting_input(tmp_path):
    hook_input = json.dumps({
        "hook_event_name": "Notification",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "notification_type": "permission_prompt",
        "message": "Claude needs permission",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    data = json.loads((tmp_path / "abc-123.json").read_text())
    assert data["state"] == "waiting_input"
    assert data["notification_type"] == "permission_prompt"


def test_handle_hook_empty_stdin(tmp_path):
    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("sys.stdin", StringIO("")):
        handle_hook()
    # Should not crash, no files written
    assert list(tmp_path.glob("*.json")) == []
