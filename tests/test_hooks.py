import json
from io import StringIO
from unittest.mock import patch, MagicMock, call

from nagare.hooks import handle_hook, _event_to_state, _build_message, _deliver
from nagare.config import NagareConfig, NotificationConfig, NotificationEventConfig


def _make_config(**overrides) -> NagareConfig:
    """Build a NagareConfig with sensible test defaults."""
    notif_kw = {
        "enabled": True,
        "needs_input": NotificationEventConfig(
            toast=True, bell=False, os_notify=False, popup=False,
            popup_timeout=10, min_working_seconds=0,
        ),
        "task_complete": NotificationEventConfig(
            toast=True, bell=False, os_notify=False, popup=False,
            popup_timeout=10, min_working_seconds=30,
        ),
        "sessions": {},
    }
    notif_kw.update(overrides.pop("notifications", {}))
    return NagareConfig(
        notifications=NotificationConfig(**notif_kw),
        **overrides,
    )


# ── _event_to_state tests (unchanged) ───────────────────────────────

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


# ── _build_message tests ────────────────────────────────────────────

def test_build_message_permission():
    assert _build_message("proj", "needs_input", "permission_prompt") == "proj needs permission"


def test_build_message_elicitation():
    assert _build_message("proj", "needs_input", "elicitation_dialog") == "proj is asking a question"


def test_build_message_generic_input():
    assert _build_message("proj", "needs_input", "other") == "proj needs your input"


def test_build_message_task_complete():
    msg = _build_message("proj", "task_complete", "", working_seconds=90)
    assert msg == "proj finished (worked 1m 30s)"


def test_build_message_task_complete_short():
    msg = _build_message("proj", "task_complete", "", working_seconds=5)
    assert msg == "proj finished (worked 5s)"


# ── handle_hook: state writing ──────────────────────────────────────

def test_handle_hook_writes_state(tmp_path):
    hook_input = json.dumps({
        "hook_event_name": "Stop",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "last_assistant_message": "Done! All tests pass.",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks.load_config", return_value=_make_config()), \
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
         patch("nagare.hooks.load_config", return_value=_make_config()), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    data = json.loads((tmp_path / "abc-123.json").read_text())
    assert data["state"] == "working"


# ── handle_hook: needs_input notification ────────────────────────────

@patch("nagare.hooks._is_active_session", return_value=False)
@patch("nagare.hooks._get_session_name", return_value="my-project")
@patch("nagare.hooks._deliver")
def test_handle_hook_sends_notification_on_permission(mock_deliver, mock_name, mock_active, tmp_path):
    hook_input = json.dumps({
        "hook_event_name": "Notification",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "notification_type": "permission_prompt",
        "message": "Claude needs permission",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks.load_config", return_value=_make_config()), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    # State should be waiting_input
    data = json.loads((tmp_path / "abc-123.json").read_text())
    assert data["state"] == "waiting_input"

    # _deliver should be called with event_type="needs_input"
    mock_deliver.assert_called_once()
    kw = mock_deliver.call_args
    assert kw[0][0] == "my-project"           # session_name
    assert kw[0][1] == "needs_input"           # event_type
    assert "permission" in kw[0][2]            # message


@patch("nagare.hooks._is_active_session", return_value=True)
@patch("nagare.hooks._get_session_name", return_value="my-project")
@patch("nagare.hooks._deliver")
def test_handle_hook_skips_active_session(mock_deliver, mock_name, mock_active, tmp_path):
    hook_input = json.dumps({
        "hook_event_name": "Notification",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "notification_type": "permission_prompt",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks.load_config", return_value=_make_config()), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    # No delivery when session is active
    mock_deliver.assert_not_called()


def test_handle_hook_no_notification_on_idle(tmp_path):
    """Stop event without prior working state should not trigger notification."""
    hook_input = json.dumps({
        "hook_event_name": "Stop",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "last_assistant_message": "Done.",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks.load_config", return_value=_make_config()), \
         patch("nagare.hooks._deliver") as mock_deliver, \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    mock_deliver.assert_not_called()


def test_handle_hook_empty_stdin(tmp_path):
    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("sys.stdin", StringIO("")):
        handle_hook()
    assert list(tmp_path.glob("*.json")) == []


# ── Task completion detection ────────────────────────────────────────

@patch("nagare.hooks._is_active_session", return_value=False)
@patch("nagare.hooks._get_session_name", return_value="my-project")
@patch("nagare.hooks._deliver")
def test_task_complete_notification(mock_deliver, mock_name, mock_active, tmp_path):
    """Stop after working > 30s triggers task_complete notification."""
    # Create a prior "working" state file with a timestamp 60s ago
    from datetime import datetime, timezone, timedelta
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    prior_state = {
        "state": "working",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "event": "UserPromptSubmit",
        "notification_type": "",
        "last_message": "",
        "timestamp": old_ts,
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "abc-123.json").write_text(json.dumps(prior_state))

    hook_input = json.dumps({
        "hook_event_name": "Stop",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "last_assistant_message": "All done.",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks.load_config", return_value=_make_config()), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    mock_deliver.assert_called_once()
    args = mock_deliver.call_args[0]
    assert args[0] == "my-project"
    assert args[1] == "task_complete"
    assert args[4] >= 55  # working_seconds (index 4: after session_name, event_type, message, config)


@patch("nagare.hooks._is_active_session", return_value=False)
@patch("nagare.hooks._get_session_name", return_value="my-project")
@patch("nagare.hooks._deliver")
def test_task_complete_skipped_short_duration(mock_deliver, mock_name, mock_active, tmp_path):
    """Stop after working < 30s should not trigger task_complete."""
    from datetime import datetime, timezone, timedelta
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    prior_state = {
        "state": "working",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "event": "UserPromptSubmit",
        "notification_type": "",
        "last_message": "",
        "timestamp": old_ts,
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "abc-123.json").write_text(json.dumps(prior_state))

    hook_input = json.dumps({
        "hook_event_name": "Stop",
        "session_id": "abc-123",
        "cwd": "/home/user/project",
        "last_assistant_message": "Quick fix.",
    })

    with patch("nagare.hooks.STATES_DIR", tmp_path), \
         patch("nagare.hooks.STORE_PATH", tmp_path / "notifs.json"), \
         patch("nagare.hooks.load_config", return_value=_make_config()), \
         patch("sys.stdin", StringIO(hook_input)):
        handle_hook()

    mock_deliver.assert_not_called()


# ── _deliver: config controls ───────────────────────────────────────

@patch("nagare.hooks.NotificationStore")
@patch("nagare.hooks.send_toast")
def test_per_session_disabled(mock_toast, mock_store_cls, tmp_path):
    """Session with enabled=False gets no delivery calls (except store)."""
    cfg = _make_config(notifications={"sessions": {"proj": {"enabled": False}}})

    _deliver("proj", "needs_input", "proj needs input", cfg, 0, tmp_path / "notifs.json")

    mock_toast.assert_not_called()
    mock_store_cls.assert_not_called()


@patch("nagare.hooks.NotificationStore")
@patch("nagare.hooks.send_toast")
def test_notifications_master_disabled(mock_toast, mock_store_cls, tmp_path):
    """config.notifications.enabled=False means no notifications at all."""
    cfg = _make_config(notifications={"enabled": False})

    _deliver("proj", "needs_input", "proj needs input", cfg, 0, tmp_path / "notifs.json")

    mock_toast.assert_not_called()
    mock_store_cls.assert_not_called()


@patch("nagare.hooks.NotificationStore")
@patch("nagare.hooks.send_toast")
@patch("nagare.hooks.send_bell")
@patch("nagare.hooks.send_os_notify")
@patch("nagare.hooks.send_popup")
def test_deliver_calls_enabled_methods(mock_popup, mock_os, mock_bell, mock_toast, mock_store_cls, tmp_path):
    """_deliver calls each method enabled in event config."""
    cfg = _make_config(notifications={
        "needs_input": NotificationEventConfig(
            toast=True, bell=True, os_notify=True, popup=True,
            popup_timeout=5, min_working_seconds=0,
        ),
    })

    mock_store_instance = MagicMock()
    mock_store_cls.return_value = mock_store_instance

    _deliver("proj", "needs_input", "proj needs input", cfg, 0, tmp_path / "notifs.json")

    # Toast is skipped when popup is enabled
    mock_toast.assert_not_called()
    mock_bell.assert_called_once()
    mock_os.assert_called_once_with("nagare", "proj needs input")
    mock_popup.assert_called_once_with("proj", "needs_input", "proj needs input", working_seconds=0, popup_timeout=5)
    mock_store_instance.add.assert_called_once_with("proj", "proj needs input")


@patch("nagare.hooks.NotificationStore")
@patch("nagare.hooks.send_toast")
@patch("nagare.hooks.send_popup")
def test_deliver_per_session_override(mock_popup, mock_toast, mock_store_cls, tmp_path):
    """Per-session override can enable popup even if event default has it off."""
    cfg = _make_config(notifications={
        "needs_input": NotificationEventConfig(
            toast=True, bell=False, os_notify=False, popup=False,
        ),
        "sessions": {"proj": {"popup": True, "popup_timeout": 7}},
    })

    mock_store_instance = MagicMock()
    mock_store_cls.return_value = mock_store_instance

    _deliver("proj", "needs_input", "proj needs input", cfg, 0, tmp_path / "notifs.json")

    # Toast skipped because per-session override enables popup
    mock_toast.assert_not_called()
    mock_popup.assert_called_once_with("proj", "needs_input", "proj needs input", working_seconds=0, popup_timeout=7)
