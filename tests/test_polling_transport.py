from unittest.mock import patch, MagicMock, call
from nagare.transport.polling import PollingTransport
from nagare.models import Session, SessionStatus


MOCK_SESSION = Session(
    name="proj-a", session_id="$1", path="/home/user/a",
    pane_index=0, status=SessionStatus.IDLE,
)


@patch("nagare.transport.polling.run_tmux")
def test_get_content(mock_run):
    mock_run.return_value = "pane content here"
    transport = PollingTransport()
    result = transport.get_content(MOCK_SESSION)
    assert result == "pane content here"
    mock_run.assert_called_once_with("capture-pane", "-t", "proj-a:0", "-p", "-e")


@patch("nagare.transport.polling.run_tmux")
def test_send_keys_regular_char(mock_run):
    transport = PollingTransport()
    transport.send_keys(MOCK_SESSION, "a", "a")
    mock_run.assert_called_once_with("send-keys", "-t", "proj-a:0", "-l", "a")


@patch("nagare.transport.polling.run_tmux")
def test_send_keys_special(mock_run):
    transport = PollingTransport()
    transport.send_keys(MOCK_SESSION, "enter", None)
    mock_run.assert_called_once_with("send-keys", "-t", "proj-a:0", "Enter")


@patch("nagare.transport.polling.run_tmux")
def test_send_keys_ctrl(mock_run):
    transport = PollingTransport()
    transport.send_keys(MOCK_SESSION, "ctrl+c", None)
    mock_run.assert_called_once_with("send-keys", "-t", "proj-a:0", "C-c")


@patch("nagare.transport.polling.run_tmux")
def test_send_keys_intercepted_ignored(mock_run):
    transport = PollingTransport()
    transport.send_keys(MOCK_SESSION, "ctrl+right_square_bracket", None)
    mock_run.assert_not_called()
