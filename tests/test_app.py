from unittest.mock import patch, MagicMock
from nagare.app import NagareApp
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.IDLE),
]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_app_launches(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "hello from pane"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from nagare.widgets.session_list import SessionList
        from nagare.widgets.terminal_view import TerminalView
        from nagare.widgets.footer_bar import FooterBar
        assert app.query_one(SessionList) is not None
        assert app.query_one(TerminalView) is not None
        assert app.query_one(FooterBar) is not None


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_starts_in_browse_mode(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "content"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._active_pane == "left"
