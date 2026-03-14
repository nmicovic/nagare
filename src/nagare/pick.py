import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, ListView, ListItem, Static

from nagare.config import load_config, save_theme
from nagare.history import load_conversation_topics
from nagare.models import Session, SessionStatus
from nagare.themes import THEMES
from nagare.tmux import run_tmux
from nagare.tmux.scanner import scan_sessions

_STATUS_SORT = {
    SessionStatus.WAITING_INPUT: 0,
    SessionStatus.RUNNING: 1,
    SessionStatus.IDLE: 2,
    SessionStatus.DEAD: 3,
}

_STATUS_LABEL = {
    SessionStatus.WAITING_INPUT: "[bold red]NEEDS INPUT[/bold red]",
    SessionStatus.RUNNING: "[bold yellow]WORKING[/bold yellow]",
    SessionStatus.IDLE: "[bold green]IDLE[/bold green]",
    SessionStatus.DEAD: "[dim]EXITED[/dim]",
}


def _format_line1(session: Session) -> str:
    icon = session.status_icon
    label = _STATUS_LABEL.get(session.status, "")
    return f"{icon}  [b]{session.name}[/b]  {label}"


def _format_line2(session: Session) -> str:
    d = session.details
    parts = []
    if d.git_branch:
        parts.append(f" {d.git_branch}")
    if d.model:
        parts.append(f"  🤖 {d.model}")
    if d.context_usage:
        parts.append(f"  📊 {d.context_usage}")
    return "   " + "".join(parts) if parts else ""


def _format_line3(session: Session) -> str:
    return f"    📁 {session.path}"


def _format_topic(session: Session, topics: dict[str, str]) -> str:
    # Prefer last_message from hooks (Claude's last response) over history
    topic = session.last_message or topics.get(session.path, "")
    if not topic:
        return ""
    # Take just the first line and truncate
    topic = topic.strip().split("\n")[0]
    if len(topic) > 80:
        topic = topic[:77] + "..."
    return f"    [dim italic]💬 {topic}[/dim italic]"


def _make_item(session: Session, topics: dict[str, str]) -> ListItem:
    children = [
        Static(_format_line1(session)),
        Static(_format_line2(session)),
        Static(_format_line3(session)),
    ]
    topic_line = _format_topic(session, topics)
    if topic_line:
        children.append(Static(topic_line))
    lines = Vertical(*children, classes="session-item")
    return ListItem(lines)


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
        self._topics: dict[str, str] = {}
        self._theme_names = list(THEMES.keys())
        self._theme_index = 0

    def compose(self) -> ComposeResult:
        yield Static(id="title-bar")
        yield Input(placeholder="Search sessions...", id="search")
        yield ListView(id="session-list")
        yield Static(id="hint-bar")

    def on_mount(self) -> None:
        config = load_config()
        for t in THEMES.values():
            self.register_theme(t)
        saved = config.theme if config.theme in THEMES else self._theme_names[0]
        self.theme = saved
        self._theme_index = self._theme_names.index(saved)

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        self._topics = load_conversation_topics()
        self._sessions = scan_sessions()
        self._sessions.sort(key=lambda s: _STATUS_SORT.get(s.status, 99))
        self._filtered_sessions = list(self._sessions)
        self._rebuild_list()
        self._update_title_bar()
        self._update_hint_bar()
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
        self._update_title_bar()

    def _rebuild_list(self) -> None:
        lv = self.query_one("#session-list", ListView)
        lv.clear()
        for session in self._filtered_sessions:
            lv.append(_make_item(session, self._topics))
        if self._filtered_sessions:
            lv.index = 0
        if not self._filtered_sessions:
            lv.append(ListItem(Static("[dim]No matching sessions[/dim]")))

    def _update_title_bar(self) -> None:
        total = len(self._sessions)
        shown = len(self._filtered_sessions)
        waiting = sum(1 for s in self._sessions if s.status == SessionStatus.WAITING_INPUT)

        count = f"{shown}/{total}" if shown != total else str(total)
        parts = [f"[b]nagare[/b]  ·  {count} sessions"]
        if waiting:
            parts.append(f"  🟡 {waiting} need{'s' if waiting == 1 else ''} input")
        self.query_one("#title-bar", Static).update("".join(parts))

    def _jump_to_session(self, session) -> None:
        target = f"{session.name}:{session.window_index}.{session.pane_index}"
        run_tmux("switch-client", "-t", target)
        self.exit()

    def _jump_to_highlighted(self) -> None:
        lv = self.query_one("#session-list", ListView)
        idx = lv.index
        if idx is not None and 0 <= idx < len(self._filtered_sessions):
            self._jump_to_session(self._filtered_sessions[idx])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        lv = self.query_one("#session-list", ListView)
        idx = lv.index
        if idx is not None and 0 <= idx < len(self._filtered_sessions):
            self._jump_to_session(self._filtered_sessions[idx])

    def on_key(self, event) -> None:
        if event.key in ("down", "up"):
            lv = self.query_one("#session-list", ListView)
            if event.key == "down":
                lv.action_cursor_down()
            else:
                lv.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            self._jump_to_highlighted()
            event.prevent_default()
            event.stop()
        elif event.key == "ctrl+t":
            self._cycle_theme()
            event.prevent_default()
            event.stop()

    def _update_hint_bar(self) -> None:
        name = self._theme_names[self._theme_index]
        self.query_one("#hint-bar", Static).update(
            f"[b]Enter[/b] Jump  [b]↑/↓[/b] Navigate  [b]Ctrl+t[/b] Theme  [b]Esc[/b] Cancel"
            f"  │  🎨 {name}"
        )

    def _cycle_theme(self) -> None:
        self._theme_index = (self._theme_index + 1) % len(self._theme_names)
        name = self._theme_names[self._theme_index]
        self.theme = name
        save_theme(name)
        self._update_hint_bar()
