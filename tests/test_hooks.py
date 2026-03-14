import json
from io import StringIO
from unittest.mock import patch, MagicMock

from nagare.hooks import handle_hook, _event_to_state


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
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
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
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    data = json.loads((tmp_path / "abc-123.json").read_text())
    assert data["state"] == "working"


@patch("nagare.hooks._is_active_session", return_value=False)
@patch("nagare.hooks._get_session_name", return_value="my-project")
@patch("subprocess.run")
def test_handle_hook_sends_notification_on_permission(mock_run, mock_name, mock_active, tmp_path):
    hook_input = json.dumps({
        "hook_event_name": "Notification",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "notification_type": "permission_prompt",
        "message": "Claude needs permission",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    # State should be waiting_input
    data = json.loads((tmp_path / "abc-123.json").read_text())
    assert data["state"] == "waiting_input"

    # tmux display-message should have been called
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "display-message" in call_args
    assert "my-project needs permission" in call_args[-1]

    # Notification should be stored
    notifs = json.loads((tmp_path / "notifs.json").read_text())
    assert len(notifs) == 1
    assert notifs[0]["session_name"] == "my-project"


@patch("nagare.hooks._is_active_session", return_value=True)
@patch("nagare.hooks._get_session_name", return_value="my-project")
@patch("subprocess.run")
def test_handle_hook_skips_active_session(mock_run, mock_name, mock_active, tmp_path):
    hook_input = json.dumps({
        "hook_event_name": "Notification",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "notification_type": "permission_prompt",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    # No tmux display-message call
    mock_run.assert_not_called()
    # No notification stored
    assert not (tmp_path / "notifs.json").exists()


def test_handle_hook_no_notification_on_idle(tmp_path):
    """Stop event should not trigger a notification."""
    hook_input = json.dumps({
        "hook_event_name": "Stop",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "last_assistant_message": "Done.",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    # No notification stored
    assert not (tmp_path / "notifs.json").exists()


def test_handle_hook_empty_stdin(tmp_path):
    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("sys.stdin", StringIO("")):
        handle_hook()
    assert list(tmp_path.glob("*.json")) == []
