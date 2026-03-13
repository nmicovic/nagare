from textual.app import App, ComposeResult
from nagare.widgets.session_detail import SessionDetail
from nagare.models import Session, SessionStatus, SessionDetails


class DetailApp(App):
    def compose(self) -> ComposeResult:
        yield SessionDetail()


async def test_session_detail_renders():
    app = DetailApp()
    async with app.run_test() as pilot:
        detail = app.query_one(SessionDetail)
        session = Session(
            name="cosmo-ai",
            session_id="$1",
            path="/home/user/projects/cosmo-ai",
            pane_index=0,
            status=SessionStatus.WAITING_INPUT,
            details=SessionDetails(
                git_branch="main",
                model="Opus 4.6",
                context_usage="51%",
            ),
        )
        detail.update_session(session)
        await pilot.pause()
        assert detail is not None


async def test_session_detail_no_session():
    app = DetailApp()
    async with app.run_test() as pilot:
        detail = app.query_one(SessionDetail)
        detail.update_session(None)
        await pilot.pause()
        assert detail is not None
