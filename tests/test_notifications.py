from unittest.mock import patch, MagicMock

from nagare.notifications.deliver import (
    send_toast,
    send_bell,
    send_os_notify,
    detect_os_notify_cmd,
    send_popup,
)


@patch("nagare.notifications.deliver._get_active_session", return_value="nagare")
@patch("nagare.notifications.deliver.run_tmux")
def test_send_toast(mock_run, mock_session):
    send_toast("session ready", duration=5000)
    mock_run.assert_called_once()
    args = mock_run.call_args[0]
    assert args[0] == "run-shell"
    assert args[1] == "-b"
    assert "display-message" in args[2]
    assert "-t nagare" in args[2]
    assert "session ready" in args[2]


@patch("nagare.notifications.deliver.subprocess.run")
def test_send_bell(mock_run):
    send_bell()
    mock_run.assert_called_once()
    args = mock_run.call_args
    assert args[0][0][0] == "tmux"
    assert "run-shell" in args[0][0]


@patch("nagare.notifications.deliver.detect_os_notify_cmd", return_value=["notify-send"])
@patch("nagare.notifications.deliver.subprocess.run")
def test_send_os_notify_linux(mock_run, mock_detect):
    send_os_notify("Nagare", "Session ready")
    mock_run.assert_called_once_with(
        ["notify-send", "Nagare", "Session ready"],
        capture_output=True,
        text=True,
        timeout=5,
    )


@patch("nagare.notifications.deliver.detect_os_notify_cmd", return_value=None)
@patch("nagare.notifications.deliver.subprocess.run")
def test_send_os_notify_unavailable(mock_run, mock_detect):
    send_os_notify("Nagare", "Session ready")
    mock_run.assert_not_called()


@patch.dict("os.environ", {"WSL_DISTRO_NAME": "Ubuntu"})
@patch("shutil.which", return_value="/usr/bin/wsl-notify-send")
def test_detect_wsl(mock_which):
    result = detect_os_notify_cmd()
    assert result == ["wsl-notify-send"]
    mock_which.assert_called_with("wsl-notify-send")


@patch.dict("os.environ", {}, clear=True)
@patch("shutil.which", return_value="/usr/bin/notify-send")
def test_detect_native_linux(mock_which):
    # Ensure WSL_DISTRO_NAME is not set
    import os
    os.environ.pop("WSL_DISTRO_NAME", None)
    result = detect_os_notify_cmd()
    assert result == ["notify-send"]


@patch.dict("os.environ", {}, clear=True)
@patch("shutil.which", return_value=None)
def test_detect_nothing_available(mock_which):
    import os
    os.environ.pop("WSL_DISTRO_NAME", None)
    result = detect_os_notify_cmd()
    assert result is None


@patch("nagare.notifications.deliver._get_active_session", return_value="nagare")
@patch("nagare.notifications.deliver._find_nagare_bin", return_value="/usr/local/bin/nagare")
@patch("nagare.notifications.deliver.run_tmux")
def test_send_popup(mock_run, mock_find, mock_session):
    send_popup("my-project", "waiting_for_input", "Needs attention", working_seconds=120, popup_timeout=15)
    mock_run.assert_called_once()
    args = mock_run.call_args[0]
    assert args[0] == "run-shell"
    assert args[1] == "-b"
    inner_cmd = args[2]
    assert "display-popup" in inner_cmd
    assert "-t nagare" in inner_cmd
    assert "popup-notif" in inner_cmd
    assert "--session" in inner_cmd
    assert "my-project" in inner_cmd
    assert "--duration" in inner_cmd
