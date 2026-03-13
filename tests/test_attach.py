from unittest.mock import patch
from nagare.tmux.attach import attach_session


@patch("nagare.tmux.attach.subprocess.run")
def test_attach_session(mock_run):
    attach_session("my-project")
    mock_run.assert_called_once_with(["tmux", "attach-session", "-t", "my-project"])
