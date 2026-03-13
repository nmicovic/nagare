from unittest.mock import patch, MagicMock
from nagare.app import NagareApp
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.IDLE),
    Session(name="proj-b", session_id="$2", path="/home/user/b", pane_index=0, status=SessionStatus.IDLE),
]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_navigate_sessions(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "mock content"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from nagare.widgets.session_list import SessionList
        session_list = app.query_one(SessionList)

        assert session_list.selected_session == MOCK_SESSIONS[0]
        await pilot.press("j")
        await pilot.pause()
        assert session_list.selected_session == MOCK_SESSIONS[1]
        await pilot.press("k")
        await pilot.pause()
        assert session_list.selected_session == MOCK_SESSIONS[0]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_toggle_pane(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "mock content"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._active_pane == "left"

        await pilot.press("ctrl+right_square_bracket")
        await pilot.pause()
        assert app._active_pane == "right"
        mock_transport.start_streaming.assert_called_once()

        await pilot.press("ctrl+right_square_bracket")
        await pilot.pause()
        assert app._active_pane == "left"
        mock_transport.stop_streaming.assert_called()


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.PollingTransport")
async def test_quit(MockTransport, mock_scan):
    mock_transport = MockTransport.return_value
    mock_transport.get_content.return_value = "mock content"
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.pause()
