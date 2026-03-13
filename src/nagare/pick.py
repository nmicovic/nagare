import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from nagare.models import Session, SessionStatus
from nagare.themes import THEMES, DEFAULT_THEME
from nagare.tmux import run_tmux
from nagare.tmux.scanner import scan_sessions

# Sort priority: WAITING_INPUT first, then RUNNING, IDLE, DEAD
_STATUS_SORT = {
    SessionStatus.WAITING_INPUT: 0,
    SessionStatus.RUNNING: 1,
    SessionStatus.IDLE: 2,
    SessionStatus.DEAD: 3,
}


def _format_session(session: Session) -> str:
    parts = [f"{session.status_icon} [b]{session.name}[/b]"]
    d = session.details
    if d.git_branch:
        parts.append(f"  [dim]{d.git_branch}[/dim]")
    if d.model:
        parts.append(f"  {d.model}")
    if d.context_usage:
        parts.append(f"  ctx:{d.context_usage}")
    parts.append(f"\n   [dim]{session.path}[/dim]")
    return "".join(parts)


def _fuzzy_match(query: str, text: str) -> bool:
    query = query.lower()
    text = text.lower()
    qi = 0
    for char in text:
        if qi < len(query) and char == query[qi]:
            qi += 1
    return qi == len(query)


class PickerApp(App):
    CSS_PATH = "pick.tcss"
    TITLE = "nagare pick"

    BINDINGS = [
        Binding("escape", "quit", "Cancel", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[Session] = []
        self._filtered_sessions: list[Session] = []

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search sessions...", id="search")
        yield OptionList(id="session-list")
        yield Static(
            "[b]Enter[/b] Jump  [b]\u2191/\u2193[/b] Navigate  [b]Esc[/b] Cancel",
            id="hint-bar",
        )

    def on_mount(self) -> None:
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = DEFAULT_THEME

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        self._sessions = scan_sessions()
        self._sessions.sort(key=lambda s: _STATUS_SORT.get(s.status, 99))
        self._filtered_sessions = list(self._sessions)
        self._rebuild_list()
        self.query_one("#search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        if not query:
            self._filtered_sessions = list(self._sessions)
        else:
            self._filtered_sessions = [
                s for s in self._sessions if _fuzzy_match(query, s.name)
            ]
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        option_list = self.query_one("#session-list", OptionList)
        option_list.clear_options()
        for session in self._filtered_sessions:
            option_list.add_option(Option(_format_session(session), id=session.name))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if 0 <= idx < len(self._filtered_sessions):
            session = self._filtered_sessions[idx]
            run_tmux("switch-client", "-t", session.name)
            self.exit()

    def on_key(self, event) -> None:
        # Forward arrow keys to option list when input is focused
        if event.key in ("down", "up", "j", "k"):
            option_list = self.query_one("#session-list", OptionList)
            if event.key in ("down", "j"):
                option_list.action_cursor_down()
            elif event.key in ("up", "k"):
                option_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            option_list = self.query_one("#session-list", OptionList)
            highlighted = option_list.highlighted
            if highlighted is not None and 0 <= highlighted < len(self._filtered_sessions):
                session = self._filtered_sessions[highlighted]
                run_tmux("switch-client", "-t", session.name)
                self.exit()
            event.prevent_default()
            event.stop()
