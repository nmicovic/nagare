from unittest.mock import patch, MagicMock
from nagare.daemon import SessionMonitor
from nagare.models import Session, SessionStatus


def _make_session(name: str, status: SessionStatus) -> Session:
    return Session(name=name, session_id="$1", path=f"/home/user/{name}",
                   window_index=0, pane_index=0, status=status)


@patch("nagare.daemon._get_active_session", return_value="other-session")
@patch("nagare.daemon.scan_sessions")
def test_detects_new_waiting_session(mock_scan, _):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    mock_scan.return_value = [_make_session("proj-a", SessionStatus.RUNNING)]
    monitor.poll()

    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()

    backend.notify.assert_called_once()
    assert "proj-a" in backend.notify.call_args[0][0]
    store.add.assert_called_once()


@patch("nagare.daemon._get_active_session", return_value="other-session")
@patch("nagare.daemon.scan_sessions")
def test_no_duplicate_notification(mock_scan, _):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()
    monitor.poll()
    monitor.poll()

    assert backend.notify.call_count == 1


@patch("nagare.daemon._get_active_session", return_value="other-session")
@patch("nagare.daemon.scan_sessions")
def test_renotifies_after_status_change(mock_scan, _):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()
    mock_scan.return_value = [_make_session("proj-a", SessionStatus.RUNNING)]
    monitor.poll()
    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()

    assert backend.notify.call_count == 2


@patch("nagare.daemon._get_active_session", return_value="other-session")
@patch("nagare.daemon.scan_sessions")
def test_no_notification_for_running(mock_scan, _):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    mock_scan.return_value = [_make_session("proj-a", SessionStatus.RUNNING)]
    monitor.poll()

    backend.notify.assert_not_called()


@patch("nagare.daemon._get_active_session", return_value="proj-a")
@patch("nagare.daemon.scan_sessions")
def test_no_notification_for_active_session(mock_scan, _):
    backend = MagicMock()
    store = MagicMock()
    monitor = SessionMonitor(backend, store)

    mock_scan.return_value = [_make_session("proj-a", SessionStatus.WAITING_INPUT)]
    monitor.poll()

    backend.notify.assert_not_called()
    store.add.assert_not_called()
