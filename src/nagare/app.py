from textual.app import App, ComposeResult
from textual.binding import Binding

from nagare.models import Session
from nagare.tmux.scanner import scan_sessions
from nagare.tmux.capture import capture_pane
from nagare.tmux.attach import attach_session
from nagare.widgets.session_list import SessionList
from nagare.widgets.preview_pane import PreviewPane
from nagare.widgets.footer_bar import FooterBar


class NagareApp(App):
    CSS_PATH = "nagare.tcss"
    TITLE = "nagare"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "attach_session", "Attach"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield SessionList()
        yield PreviewPane()
        yield FooterBar()

    def on_mount(self) -> None:
        self._refresh_sessions()
        self.set_interval(3, self._refresh_sessions)

    def _refresh_sessions(self) -> None:
        sessions = scan_sessions()
        session_list = self.query_one(SessionList)
        session_list.update_sessions(sessions)
        self._update_preview(session_list.selected_session)

    def _update_preview(self, session: Session | None) -> None:
        preview = self.query_one(PreviewPane)
        if session is None:
            preview.update_content("No sessions found.")
            return
        content = capture_pane(session.name, session.pane_index)
        preview.update_content(content)

    def on_session_list_session_highlighted(self, event: SessionList.SessionHighlighted) -> None:
        self._update_preview(event.session)

    def action_refresh(self) -> None:
        self._refresh_sessions()

    def action_attach_session(self) -> None:
        session_list = self.query_one(SessionList)
        session = session_list.selected_session
        if session is None:
            return
        with self.suspend():
            attach_session(session.name)
        self._refresh_sessions()

    def action_cursor_down(self) -> None:
        self.query_one(SessionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(SessionList).action_cursor_up()
