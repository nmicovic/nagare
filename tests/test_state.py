import json
from unittest.mock import patch

from nagare.state import load_all_states, SessionState


def test_load_states(tmp_path):
    state1 = {
        "state": "idle",
        "session_id": "abc",
        "cwd": "/home/user/project-a",
        "event": "Stop",
        "notification_type": "",
        "last_message": "Done!",
        "timestamp": "2026-03-14T10:00:00Z",
    }
    state2 = {
        "state": "working",
        "session_id": "def",
        "cwd": "/home/user/project-b",
        "event": "UserPromptSubmit",
        "notification_type": "",
        "last_message": "",
        "timestamp": "2026-03-14T10:01:00Z",
    }
    (tmp_path / "abc.json").write_text(json.dumps(state1))
    (tmp_path / "def.json").write_text(json.dumps(state2))

    with patch("nagare.state.STATES_DIR", tmp_path):
        states = load_all_states()

    assert len(states) == 2
    assert states["/home/user/project-a"].state == "idle"
    assert states["/home/user/project-a"].last_message == "Done!"
    assert states["/home/user/project-b"].state == "working"


def test_load_states_empty(tmp_path):
    with patch("nagare.state.STATES_DIR", tmp_path):
        states = load_all_states()
    assert states == {}


def test_load_states_corrupt_file(tmp_path):
    (tmp_path / "bad.json").write_text("not json{{{")
    (tmp_path / "good.json").write_text(json.dumps({
        "state": "idle",
        "session_id": "abc",
        "cwd": "/home/user/proj",
        "event": "Stop",
        "notification_type": "",
        "last_message": "",
        "timestamp": "",
    }))

    with patch("nagare.state.STATES_DIR", tmp_path):
        states = load_all_states()
    # Corrupt file skipped, good file loaded
    assert len(states) == 1


def test_load_states_missing_dir():
    from pathlib import Path
    with patch("nagare.state.STATES_DIR", Path("/nonexistent/path")):
        states = load_all_states()
    assert states == {}
