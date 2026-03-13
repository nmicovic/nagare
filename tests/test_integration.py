from unittest.mock import patch
from nagare.app import NagareApp
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.IDLE),
    Session(name="proj-b", session_id="$2", path="/home/user/b", pane_index=0, status=SessionStatus.IDLE),
]


@patch("nagare.app.capture_pane", return_value="mock pane content")
@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
async def test_navigate_sessions(mock_scan, mock_capture):
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        session_list = app.query_one("SessionList")

        # Initial selection is first session
        assert session_list.selected_session == MOCK_SESSIONS[0]

        # Navigate down
        await pilot.press("j")
        await pilot.pause()
        assert session_list.selected_session == MOCK_SESSIONS[1]

        # Navigate back up
        await pilot.press("k")
        await pilot.pause()
        assert session_list.selected_session == MOCK_SESSIONS[0]


@patch("nagare.app.capture_pane", return_value="mock pane content")
@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
async def test_quit(mock_scan, mock_capture):
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.press("q")
        await pilot.pause()
        # App should have exited
