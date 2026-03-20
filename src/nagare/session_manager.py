"""Session manager — load/unload registered sessions."""

import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, ListView, ListItem, Static

from nagare.config import load_config
from nagare.log import logger
from nagare.registry import RegisteredSession, SessionRegistry
from nagare.session import create_session
from nagare.themes import THEMES
from nagare.tmux import run_tmux


def _is_session_loaded(name: str) -> bool:
    """Check if a tmux session with this name has an agent running."""
    try:
        panes = run_tmux(
            "list-panes", "-s", "-t", name,
            "-F", "#{pane_current_command}",
        )
        for cmd in panes.splitlines():
            if cmd.strip() in ("claude", "opencode"):
                return True
        return False
    except Exception:
        return False


def _unload_session(name: str) -> None:
    """Kill a tmux session."""
    try:
        run_tmux("kill-session", "-t", name)
        logger.info("unloaded session %s", name)
    except Exception:
        logger.exception("failed to unload session %s", name)


def _format_session_lines(s: RegisteredSession, loaded: bool) -> list[str]:
    """Format a registered session as multiple lines for display."""
    if loaded:
        status = "[bold #00D26A]● RUNNING[/]"
    else:
        status = "[#565f89]● NOT LOADED[/]"

    agent_icon = {
        "claude": "[bold #da7756 on #3b2820] C [/]",
        "opencode": "[bold #00e5ff on #002b33] O [/]",
    }.get(s.agent, "[dim] ? [/]")

    date = ""
    if s.last_accessed:
        date = s.last_accessed[:10]

    line1 = f"{status}  {agent_icon} [b]{s.name}[/b]"
    line2 = f"    📁 {s.path}"
    line3 = f"    [dim]Last accessed: {date}[/dim]" if date else "    [dim]Never accessed[/dim]"

    return [line1, line2, line3]


def _fuzzy_match(query: str, text: str) -> bool:
    q = query.lower()
    t = text.lower()
    qi = 0
    for char in t:
        if qi < len(q) and char == q[qi]:
            qi += 1
    return qi == len(q)


class SessionManagerApp(App):
    CSS_PATH = "session_manager.tcss"
    TITLE = "nagare sessions"

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._reg = SessionRegistry()
        self._filtered: list[RegisteredSession] = []
        self._recently_loaded: set[str] = set()  # Track sessions we just loaded

    def compose(self) -> ComposeResult:
        yield Static("[b]Session Manager[/b]", id="title-bar")
        yield Input(placeholder="Search sessions...", id="search")
        yield ListView(id="session-list")
        yield Static(id="hint-bar")

    def on_mount(self) -> None:
        config = load_config()
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = config.theme if config.theme in THEMES else "tokyonight"

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        # Auto-discover on first open if registry is empty
        if not self._reg.list_all():
            count = self._reg.auto_discover()
            if count:
                logger.info("auto-discovered %d sessions", count)

        self._rebuild()
        self._update_hint_bar()
        self.query_one("#search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        query = self.query_one("#search", Input).value.strip()
        all_sessions = self._reg.list_all()

        # Sort by last accessed (newest first)
        all_sessions.sort(key=lambda s: s.last_accessed or "", reverse=True)

        if query:
            self._filtered = [s for s in all_sessions if _fuzzy_match(query, s.name)]
        else:
            self._filtered = all_sessions

        lv = self.query_one("#session-list", ListView)
        lv.clear()

        if self._filtered:
            for s in self._filtered:
                loaded = _is_session_loaded(s.name) or s.name in self._recently_loaded
                lines = _format_session_lines(s, loaded)
                item = ListItem(
                    Vertical(*[Static(l) for l in lines], classes="session-item"),
                )
                lv.append(item)
            self.call_after_refresh(self._ensure_selection, 0)
        else:
            lv.append(ListItem(Vertical(Static("[dim]No sessions found[/dim]"))))

    def _ensure_selection(self, index: int) -> None:
        lv = self.query_one("#session-list", ListView)
        if not self._filtered:
            return
        lv.index = None
        lv.index = min(index, len(self._filtered) - 1)

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
            self._toggle_session()
            event.prevent_default()
            event.stop()
        elif event.key == "ctrl+x":
            self._delete_session()
            event.prevent_default()
            event.stop()

    def _toggle_session(self) -> None:
        """Load or unload the selected session."""
        lv = self.query_one("#session-list", ListView)
        idx = lv.index
        if idx is None or idx >= len(self._filtered):
            return

        s = self._filtered[idx]
        loaded = _is_session_loaded(s.name)

        if loaded:
            _unload_session(s.name)
            self._recently_loaded.discard(s.name)
            logger.info("unloaded session %s", s.name)
        else:
            try:
                create_session(
                    path=s.path,
                    name=s.name,
                    agent=s.agent,
                    continue_session=True,
                )
                self._recently_loaded.add(s.name)
                self._reg.touch(s.name)
                logger.info("loaded session %s", s.name)
            except (ValueError, RuntimeError) as e:
                logger.exception("failed to load session %s", s.name)
                self.query_one("#title-bar", Static).update(
                    f"[b]Session Manager[/b]  [bold red]Error: {e}[/bold red]"
                )
                return

        self._rebuild()

    def _delete_session(self) -> None:
        """Remove the selected session from the registry."""
        lv = self.query_one("#session-list", ListView)
        idx = lv.index
        if idx is None or idx >= len(self._filtered):
            return

        s = self._filtered[idx]
        self._reg.remove(s.name)
        logger.info("deleted session %s from registry", s.name)
        self._rebuild()

    def _update_hint_bar(self) -> None:
        self.query_one("#hint-bar", Static).update(
            "[b]Enter[/b] Load/Unload  "
            "[#db4b4b][b]Ctrl+x[/b] Delete from registry[/]  "
            "[b]Esc[/b] Back to picker"
        )

    def action_cancel(self) -> None:
        self.exit(result="back_to_picker")
