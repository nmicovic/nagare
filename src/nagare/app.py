from textual.app import App, ComposeResult
from textual.binding import Binding

from nagare.models import Session
from nagare.tmux.scanner import scan_sessions
from nagare.tmux.capture import capture_pane
from nagare.tmux.attach import attach_session
from textual.containers import Vertical

from nagare.themes import THEMES, DEFAULT_THEME
from nagare.widgets.session_list import SessionList
from nagare.widgets.session_detail import SessionDetail
from nagare.widgets.preview_pane import PreviewPane
from nagare.widgets.footer_bar import FooterBar
from nagare.widgets.theme_picker import ThemePicker


class NagareApp(App):
    CSS_PATH = "nagare.tcss"
    TITLE = "nagare"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "pick_theme", "Theme"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="left-pane"):
            yield SessionList()
            yield SessionDetail()
        yield PreviewPane()
        yield FooterBar()

    def on_mount(self) -> None:
        self._theme_names = list(THEMES.keys())
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = DEFAULT_THEME
        self._refresh_sessions()
        self.set_interval(3, self._refresh_sessions)

    def _refresh_sessions(self) -> None:
        sessions = scan_sessions()
        session_list = self.query_one(SessionList)
        session_list.update_sessions(sessions)
        self._update_selected(session_list.selected_session)

    def _update_selected(self, session: Session | None) -> None:
        preview = self.query_one(PreviewPane)
        detail = self.query_one(SessionDetail)
        detail.update_session(session)
        if session is None:
            preview.update_content("No sessions found.")
            return
        content = capture_pane(session.name, session.pane_index)
        preview.update_content(content)

    def on_session_list_session_highlighted(self, event: SessionList.SessionHighlighted) -> None:
        self._update_selected(event.session)

    def action_refresh(self) -> None:
        self._refresh_sessions()

    def on_list_view_selected(self, event: SessionList.Selected) -> None:
        if not isinstance(event.list_view, SessionList):
            return
        session = event.list_view.selected_session
        if session is None:
            return
        with self.suspend():
            attach_session(session.name)
        self._refresh_sessions()

    def action_pick_theme(self) -> None:
        prev_theme = self.theme

        def on_dismiss(result: str | None) -> None:
            if result is None:
                # Cancelled — revert to previous theme
                self.theme = prev_theme
            else:
                self.theme = result

        self.push_screen(
            ThemePicker(self._theme_names, self.theme),
            callback=on_dismiss,
        )

    def action_cursor_down(self) -> None:
        self.query_one(SessionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(SessionList).action_cursor_up()
