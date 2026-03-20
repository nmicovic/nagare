import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from nagare.notifications.deliver import (
    send_toast,
    send_bell,
    send_os_notify,
    detect_os_notify_cmd,
    send_popup,
)


@patch("nagare.notifications.deliver._get_client_name", return_value="/dev/pts/0")
@patch("nagare.notifications.deliver.run_tmux")
def test_send_toast(mock_run, mock_client):
    send_toast("session ready", duration=5000)
    mock_run.assert_called_once_with(
        "display-message", "-t", "/dev/pts/0", "-d", "5000", "🔴 session ready"
    )


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


@patch("nagare.notifications.deliver.POPUP_FIFO", Path("/nonexistent/fifo"))
@patch("nagare.notifications.deliver._get_client_name", return_value="/dev/pts/0")
@patch("nagare.notifications.deliver._find_nagare_bin", return_value="/usr/local/bin/nagare")
@patch("nagare.notifications.deliver.subprocess.Popen")
def test_send_popup_fallback(mock_popen, mock_find, mock_client):
    """When FIFO doesn't exist, falls back to direct Popen."""
    send_popup("my-project", "waiting_for_input", "Needs attention", working_seconds=120, popup_timeout=15)
    mock_popen.assert_called_once()
    args = mock_popen.call_args[0][0]
    assert args[0] == "tmux"
    assert "display-popup" in args
    assert "-E" in args
    cmd_str = args[-1]
    assert "popup-notif" in cmd_str
    assert "my-project" in cmd_str
    assert "--duration" in cmd_str


def test_send_popup_fifo(tmp_path):
    """When FIFO exists, writes command to it."""
    fifo_path = tmp_path / "popup.fifo"
    os.mkfifo(str(fifo_path))

    import threading

    # Reader thread (simulates watcher)
    received = []
    def reader():
        with open(fifo_path) as f:
            for line in f:
                received.append(line.strip())

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    with patch("nagare.notifications.deliver.POPUP_FIFO", fifo_path), \
         patch("nagare.notifications.deliver._find_nagare_bin", return_value="/usr/bin/nagare"):
        send_popup("test-proj", "needs_input", "test msg", popup_timeout=5)

    # Close the FIFO to unblock reader
    with open(fifo_path, "w") as f:
        pass
    t.join(timeout=2)

    assert len(received) == 1
    assert "display-popup" in received[0]
    assert "test-proj" in received[0]
