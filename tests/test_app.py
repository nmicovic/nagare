from unittest.mock import patch
from nagare.app import NagareApp
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.IDLE),
]


@patch("nagare.app.scan_sessions", return_value=MOCK_SESSIONS)
@patch("nagare.app.capture_pane", return_value="hello from pane")
async def test_app_launches(mock_capture, mock_scan):
    app = NagareApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from nagare.widgets.session_list import SessionList
        from nagare.widgets.preview_pane import PreviewPane
        from nagare.widgets.footer_bar import FooterBar
        assert app.query_one(SessionList) is not None
        assert app.query_one(PreviewPane) is not None
        assert app.query_one(FooterBar) is not None
