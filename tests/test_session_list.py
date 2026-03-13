from textual.app import App, ComposeResult
from nagare.widgets.session_list import SessionList
from nagare.models import Session, SessionStatus


MOCK_SESSIONS = [
    Session(name="proj-a", session_id="$1", path="/home/user/a", pane_index=0, status=SessionStatus.ALIVE),
    Session(name="proj-b", session_id="$2", path="/home/user/b", pane_index=1, status=SessionStatus.DEAD),
]


class SessionListApp(App):
    def compose(self) -> ComposeResult:
        yield SessionList()


async def test_session_list_renders():
    app = SessionListApp()
    async with app.run_test() as pilot:
        widget = app.query_one(SessionList)
        widget.update_sessions(MOCK_SESSIONS)
        await pilot.pause()
        assert len(widget.children) == 2


async def test_session_list_selection():
    app = SessionListApp()
    async with app.run_test() as pilot:
        widget = app.query_one(SessionList)
        widget.update_sessions(MOCK_SESSIONS)
        await pilot.pause()
        assert widget.selected_session == MOCK_SESSIONS[0]
