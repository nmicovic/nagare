from unittest.mock import patch
from nagare.pick import PickerApp
from nagare.models import Session, SessionStatus, SessionDetails


MOCK_SESSIONS = [
    Session(name="cosmo-ai", session_id="$1", path="/home/user/cosmo",
            window_index=0, pane_index=0, status=SessionStatus.WAITING_INPUT,
            details=SessionDetails(git_branch="main", model="Opus", context_usage="50%")),
    Session(name="nagare", session_id="$2", path="/home/user/nagare",
            window_index=0, pane_index=0, status=SessionStatus.IDLE,
            details=SessionDetails(git_branch="feat", model="Sonnet", context_usage="20%")),
    Session(name="proj-b", session_id="$3", path="/home/user/projb",
            window_index=0, pane_index=0, status=SessionStatus.RUNNING,
            details=SessionDetails(git_branch="dev", model="Opus", context_usage="80%")),
]


@patch("nagare.pick.scan_sessions", return_value=MOCK_SESSIONS)
async def test_picker_shows_sessions(mock_scan):
    app = PickerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import ListView
        lv = app.query_one(ListView)
        assert len(lv.children) == 3


@patch("nagare.pick.scan_sessions", return_value=MOCK_SESSIONS)
async def test_picker_waiting_sessions_first(mock_scan):
    app = PickerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # WAITING_INPUT sessions should sort to the top
        assert app._filtered_sessions[0].name == "cosmo-ai"


@patch("nagare.pick.scan_sessions", return_value=MOCK_SESSIONS)
async def test_picker_fuzzy_filter(mock_scan):
    app = PickerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Input
        search = app.query_one(Input)
        search.value = "cos"
        await pilot.pause()
        assert len(app._filtered_sessions) == 1


@patch("nagare.pick.scan_sessions", return_value=MOCK_SESSIONS)
async def test_picker_escape_exits(mock_scan):
    app = PickerApp()
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        # App should exit with no result
