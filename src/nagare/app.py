from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical

from nagare.models import Session
from nagare.tmux.scanner import scan_sessions
from nagare.themes import THEMES, DEFAULT_THEME
from nagare.transport.polling import PollingTransport
from nagare.widgets.session_list import SessionList
from nagare.widgets.session_detail import SessionDetail
from nagare.widgets.terminal_view import TerminalView
from nagare.widgets.footer_bar import FooterBar
from nagare.widgets.theme_picker import ThemePicker


class NagareApp(App):
    CSS_PATH = "nagare.tcss"
    TITLE = "nagare"

    BINDINGS = [
        Binding("ctrl+right_square_bracket", "toggle_pane", "Toggle Pane", show=False),
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "pick_theme", "Theme"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._transport = PollingTransport()
        self._active_pane: str = "left"
        self._active_session: Session | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="left-pane"):
            yield SessionList()
            yield SessionDetail()
        yield TerminalView()
        yield FooterBar()

    def on_mount(self) -> None:
        self._theme_names = list(THEMES.keys())
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = DEFAULT_THEME
        self._refresh_sessions()
        self._scan_timer = self.set_interval(3, self._refresh_sessions)
        self._preview_timer = self.set_interval(3, self._refresh_preview)
        self._set_pane_focus("left")

    # --- Pane focus management ---

    def _set_pane_focus(self, pane: str) -> None:
        self._active_pane = pane
        left = self.query_one("#left-pane")
        terminal = self.query_one(TerminalView)
        footer = self.query_one(FooterBar)

        if pane == "left":
            left.remove_class("inactive-pane")
            terminal.set_active(False)
            footer.set_browse_mode()
            self._transport.stop_streaming()
            if self._preview_timer is not None:
                self._preview_timer.resume()
            self.query_one(SessionList).focus()
        else:
            left.add_class("inactive-pane")
            terminal.set_active(True)
            footer.set_interactive_mode()
            if self._preview_timer is not None:
                self._preview_timer.pause()
            session = self.query_one(SessionList).selected_session
            if session:
                self._active_session = session
                self._transport.start_streaming(
                    session,
                    lambda content: self.call_from_thread(self._on_stream_content, content),
                )
            terminal.focus()

    def _on_stream_content(self, content: str) -> None:
        self.query_one(TerminalView).update_content(content)

    def action_toggle_pane(self) -> None:
        if self._active_pane == "left":
            self._set_pane_focus("right")
        else:
            self._set_pane_focus("left")

    # --- Key forwarding ---

    def on_key(self, event: events.Key) -> None:
        if self._active_pane != "right":
            return
        if event.key == "ctrl+right_square_bracket":
            return  # handled by binding
        session = self._active_session
        if session:
            self._transport.send_keys(session, event.key, event.character)
            event.prevent_default()
            event.stop()

    # --- Session refresh ---

    def _refresh_sessions(self) -> None:
        sessions = scan_sessions()
        session_list = self.query_one(SessionList)
        session_list.update_sessions(sessions)
        detail = self.query_one(SessionDetail)
        detail.update_session(session_list.selected_session)
        if self._active_pane == "left":
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._active_pane != "left":
            return
        session_list = self.query_one(SessionList)
        session = session_list.selected_session
        terminal = self.query_one(TerminalView)
        if session is None:
            terminal.update_content("No sessions found.")
            return
        content = self._transport.get_content(session)
        terminal.update_content(content)

    def on_session_list_session_highlighted(self, event: SessionList.SessionHighlighted) -> None:
        detail = self.query_one(SessionDetail)
        detail.update_session(event.session)
        if self._active_pane == "left":
            terminal = self.query_one(TerminalView)
            content = self._transport.get_content(event.session)
            terminal.update_content(content)

    # --- Browse mode bindings ---

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        browse_only = {"quit", "refresh", "pick_theme", "cursor_down", "cursor_up"}
        if action in browse_only and self._active_pane != "left":
            return False
        return True

    def action_refresh(self) -> None:
        self._refresh_sessions()

    def action_quit(self) -> None:
        self._transport.stop_streaming()
        self.exit()

    def action_pick_theme(self) -> None:
        prev_theme = self.theme

        def on_dismiss(result: str | None) -> None:
            if result is None:
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
