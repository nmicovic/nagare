from unittest.mock import patch
from nagare.tmux.capture import capture_pane


@patch("nagare.tmux.capture.run_tmux")
def test_capture_pane(mock_run):
    mock_run.return_value = "line 1\nline 2\nline 3"
    result = capture_pane("my-session", 0)
    assert result == "line 1\nline 2\nline 3"
    mock_run.assert_called_once_with("capture-pane", "-t", "my-session:0", "-p", "-e")


@patch("nagare.tmux.capture.run_tmux")
def test_capture_pane_empty(mock_run):
    mock_run.return_value = ""
    result = capture_pane("my-session", 0)
    assert result == ""
