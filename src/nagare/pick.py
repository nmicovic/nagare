import os
import re
import time

from rich.text import Text

# Strip ANSI background color sequences (48;5;N, 48;2;R;G;B, 49)
# These clash with Textual's themed backgrounds and appear as white blocks.
_BG_COLOR_RE = re.compile(r"\x1b\[(?:48;[25](?:;[\d]+)*|49)m")

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
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
    SessionStatus.IDLE: "[bold #00D26A]IDLE[/bold #00D26A]",
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


def _capture_pane(session: Session) -> str:
    """Capture the current visible content of a tmux pane."""
    target = f"{session.name}:{session.window_index}.{session.pane_index}"
    try:
        raw = run_tmux("capture-pane", "-t", target, "-p", "-e")
        # Strip background colors that clash with Textual's theme
        return _BG_COLOR_RE.sub("", raw)
    except Exception:
        return "[dim]Unable to capture pane content[/dim]"


def _human_duration(seconds: float) -> str:
    """Convert seconds to a human-readable duration string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_m = minutes % 60
    if hours < 24:
        return f"{hours}h {remaining_m}m"
    days = hours // 24
    remaining_h = hours % 24
    return f"{days}d {remaining_h}h"


def _get_session_details(session: Session) -> str:
    """Get detailed info about a tmux session for the detail panel."""
    parts = []
    name = session.name

    # Session age
    try:
        created = int(run_tmux("display-message", "-t", name, "-p", "#{session_created}"))
        age = _human_duration(time.time() - created)
        parts.append(f"  ⏱  Session age: [b]{age}[/b]")
    except (ValueError, Exception):
        pass

    # Windows/tabs
    try:
        windows_raw = run_tmux(
            "list-windows", "-t", name,
            "-F", "#{window_index}:#{window_name}:#{window_panes}:#{window_active}",
        )
        if windows_raw:
            window_lines = []
            for line in windows_raw.splitlines():
                idx, wname, panes, active = line.split(":")
                marker = " [b]*[/b]" if active == "1" else ""
                pane_info = f" ({panes} panes)" if int(panes) > 1 else ""
                window_lines.append(f"    {idx}: {wname}{pane_info}{marker}")
            parts.append(f"  🪟  Windows ({len(windows_raw.splitlines())}):")
            parts.extend(window_lines)
    except Exception:
        pass

    # Processes in panes
    try:
        panes_raw = run_tmux(
            "list-panes", "-s", "-t", name,
            "-F", "#{window_index}.#{pane_index}:#{pane_current_command}:#{pane_pid}",
        )
        if panes_raw:
            proc_lines = []
            for line in panes_raw.splitlines():
                pane_id, cmd, pid = line.split(":")
                proc_lines.append(f"    {pane_id}  {cmd} [dim](pid {pid})[/dim]")
            parts.append(f"  ⚙  Processes:")
            parts.extend(proc_lines)
    except Exception:
        pass

    # Pane dimensions
    try:
        dims = run_tmux(
            "display-message", "-t",
            f"{name}:{session.window_index}.{session.pane_index}",
            "-p", "#{pane_width}x#{pane_height}",
        )
        if dims:
            parts.append(f"  📐 Pane size: {dims}")
    except Exception:
        pass

    return "\n".join(parts) if parts else "[dim]No details available[/dim]"


def _get_dashboard_stats(sessions: list[Session]) -> str:
    """Build a dashboard stats string for the bottom of the left panel."""
    total = len(sessions)
    by_status = {}
    for s in sessions:
        by_status[s.status] = by_status.get(s.status, 0) + 1

    parts = []

    # Status breakdown
    status_parts = []
    for status, icon in [
        (SessionStatus.WAITING_INPUT, "🔴"),
        (SessionStatus.RUNNING, "🟡"),
        (SessionStatus.IDLE, "🟢"),
        (SessionStatus.DEAD, "⚪"),
    ]:
        count = by_status.get(status, 0)
        if count:
            status_parts.append(f"{icon} {count}")
    parts.append(f"  {total} sessions  " + "  ".join(status_parts))

    # System load
    try:
        with open("/proc/loadavg") as f:
            load_1, load_5, load_15, *_ = f.read().split()
        parts.append(f"  📊 Load: {load_1} / {load_5} / {load_15}")
    except Exception:
        pass

    # Memory
    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                if line.startswith(("MemTotal:", "MemAvailable:")):
                    key, val, *_ = line.split()
                    mem[key.rstrip(":")] = int(val)
            if "MemTotal" in mem and "MemAvailable" in mem:
                total_gb = mem["MemTotal"] / 1048576
                used_gb = (mem["MemTotal"] - mem["MemAvailable"]) / 1048576
                parts.append(f"  🧠 Mem: {used_gb:.1f}G / {total_gb:.1f}G")
    except Exception:
        pass

    # Tmux server uptime
    try:
        pid_raw = run_tmux("display-message", "-p", "#{pid}")
        if pid_raw:
            stat = f"/proc/{pid_raw}/stat"
            with open(stat) as f:
                fields = f.read().split()
            # Field 21 is starttime in clock ticks
            start_ticks = int(fields[21])
            with open("/proc/uptime") as f:
                uptime_s = float(f.read().split()[0])
            hz = os.sysconf("SC_CLK_TCK")
            tmux_age = uptime_s - (start_ticks / hz)
            if tmux_age > 0:
                parts.append(f"  🖥  tmux uptime: {_human_duration(tmux_age)}")
    except Exception:
        pass

    return "\n".join(parts)


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
        self._preview_session: Session | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="title-bar")
        yield Input(placeholder="Search sessions...", id="search")
        with Horizontal(id="main-area"):
            with Vertical(id="left-panel"):
                yield ListView(id="session-list")
                yield Static(id="dashboard")
            with Vertical(id="right-panel"):
                yield Static(id="session-details")
                with VerticalScroll(id="preview-scroll"):
                    yield Static(id="preview-content")
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

        self._current_session = run_tmux("display-message", "-p", "#S")
        self._topics = load_conversation_topics()
        self._refresh_sessions()
        self._select_current_session()
        self._update_hint_bar()
        self._update_dashboard()
        self.query_one("#search", Input).focus()
        self.set_interval(2, self._poll_state)
        self.set_interval(1, self._poll_preview)

    def _select_current_session(self) -> None:
        """Highlight the session we launched the picker from."""
        if not self._current_session:
            return
        lv = self.query_one("#session-list", ListView)
        for i, session in enumerate(self._filtered_sessions):
            if session.name == self._current_session:
                lv.index = i
                self._update_preview(session)
                break

    def _refresh_sessions(self) -> None:
        self._sessions = scan_sessions()
        self._sessions.sort(key=lambda s: _STATUS_SORT.get(s.status, 99))
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.query_one("#search", Input).value.strip()
        if not query:
            self._filtered_sessions = list(self._sessions)
        else:
            self._filtered_sessions = [
                s for s in self._sessions if _fuzzy_match(query, s.name)
            ]
        self._rebuild_list()
        self._update_title_bar()

    def _poll_state(self) -> None:
        old_snapshot = {s.name: s.status for s in self._sessions}
        self._sessions = scan_sessions()
        self._sessions.sort(key=lambda s: _STATUS_SORT.get(s.status, 99))
        new_snapshot = {s.name: s.status for s in self._sessions}
        if old_snapshot != new_snapshot:
            lv = self.query_one("#session-list", ListView)
            old_idx = lv.index
            self._apply_filter()
            if old_idx is not None and 0 <= old_idx < len(self._filtered_sessions):
                lv.index = old_idx
        self._update_dashboard()

    def _poll_preview(self) -> None:
        """Refresh the preview pane content every second."""
        session = self._get_highlighted_session()
        if session is not None:
            self._update_preview(session)

    def _get_highlighted_session(self) -> Session | None:
        lv = self.query_one("#session-list", ListView)
        idx = lv.index
        if idx is not None and 0 <= idx < len(self._filtered_sessions):
            return self._filtered_sessions[idx]
        return None

    def _update_preview(self, session: Session) -> None:
        """Update the preview panel with the pane capture of the given session."""
        self._preview_session = session

        # Update session details panel
        label = _STATUS_LABEL.get(session.status, "")
        header = f"{session.status_icon}  [b]{session.name}[/b]  {label}\n"
        details = _get_session_details(session)
        self.query_one("#session-details", Static).update(header + details)

        # Update pane preview
        content = _capture_pane(session)
        # Strip trailing blank lines for cleaner display
        lines = content.rstrip("\n").split("\n")
        # Remove leading empty lines too
        while lines and not lines[0].strip():
            lines.pop(0)
        # Truncate lines to preview panel width to prevent wrapping
        try:
            panel = self.query_one("#preview-scroll")
            max_width = panel.size.width - 2  # account for padding
            if max_width > 0:
                lines = [line[:max_width] for line in lines]
        except Exception:
            pass
        rich_text = Text.from_ansi("\n".join(lines))
        self.query_one("#preview-content", Static).update(rich_text)
        # Scroll preview to bottom so latest output is visible
        self.query_one("#preview-scroll").scroll_end(animate=False)

    def _update_dashboard(self) -> None:
        """Update the dashboard stats at the bottom of the left panel."""
        stats = _get_dashboard_stats(self._sessions)
        self.query_one("#dashboard", Static).update(stats)

    def on_input_changed(self, event: Input.Changed) -> None:
        self._apply_filter()

    def _rebuild_list(self) -> None:
        lv = self.query_one("#session-list", ListView)
        lv.clear()
        for session in self._filtered_sessions:
            lv.append(_make_item(session, self._topics))
        if self._filtered_sessions:
            lv.index = 0
        if not self._filtered_sessions:
            lv.append(ListItem(Static("[dim]No matching sessions[/dim]")))
        # Update preview for the first item
        session = self._get_highlighted_session()
        if session is not None:
            self._update_preview(session)
        else:
            self.query_one("#session-details", Static).update("")
            self.query_one("#preview-content", Static).update(
                "[dim]No session selected[/dim]"
            )

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
            # Immediately update preview on navigation
            session = self._get_highlighted_session()
            if session is not None:
                self._update_preview(session)
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
