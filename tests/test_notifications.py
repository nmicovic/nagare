from unittest.mock import patch
from nagare.notifications.base import NotificationBackend
from nagare.notifications.tmux import TmuxNotificationBackend


def test_backend_is_abstract():
    """NotificationBackend cannot be instantiated directly."""
    import pytest
    with pytest.raises(TypeError):
        NotificationBackend()


@patch("nagare.notifications.tmux.run_tmux")
def test_tmux_backend_notify(mock_run):
    backend = TmuxNotificationBackend(duration=2000)
    backend.notify("cosmo-ai is waiting for input", "cosmo-ai", "high")
    mock_run.assert_called_once_with(
        "display-message", "-d", "2000",
        "\u26a1 cosmo-ai is waiting for input",
    )


@patch("nagare.notifications.tmux.run_tmux")
def test_tmux_backend_custom_duration(mock_run):
    backend = TmuxNotificationBackend(duration=5000)
    backend.notify("test message", "proj-a", "low")
    mock_run.assert_called_once_with(
        "display-message", "-d", "5000",
        "\u26a1 test message",
    )
