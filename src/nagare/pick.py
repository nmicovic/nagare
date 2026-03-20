import asyncio
import os
import re
import time

from rich.text import Text

# Strip ANSI background color sequences (48;5;N, 48;2;R;G;B, 49)
# These clash with Textual's themed backgrounds and appear as white blocks.
_BG_COLOR_RE = re.compile(r"\x1b\[(?:48;[25](?:;[\d]+)*|49)m")

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Provider, Hits, Hit, DiscoveryHit
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.timer import Timer
from textual.widgets import Input, ListView, ListItem, ProgressBar, Rule, Static

from nagare.config import AnimationConfig, load_config, save_theme
from nagare.log import logger
from nagare.history import load_conversation_topics
from nagare.models import Session, SessionStatus
from nagare.state import mark_path_dead
from nagare.themes import THEMES
from nagare.tmux import run_tmux
from nagare.tmux.scanner import scan_sessions

_STATUS_SORT = {
    SessionStatus.WAITING_INPUT: 0,
    SessionStatus.RUNNING: 1,
    SessionStatus.IDLE: 2,
    SessionStatus.DEAD: 3,
}

_SORT_MODES = ["status", "name", "agent"]


def _sort_sessions(sessions: list[Session], mode: str) -> list[Session]:
    """Sort sessions by the given mode."""
    if mode == "name":
        return sorted(sessions, key=lambda s: s.name.lower())
    elif mode == "agent":
        return sorted(sessions, key=lambda s: (s.agent_type.value, s.name.lower()))
    else:  # status (default)
        return sorted(sessions, key=lambda s: _STATUS_SORT.get(s.status, 99))


_HELP_TEXT = """\
[b]nagare — keyboard shortcuts[/b]

[b]Navigation[/b]
  [b]↑/↓[/b]          Move up/down (list & grid)
  [b]←/→[/b]          Move left/right (grid only)
  [b]Enter[/b]        Jump to selected session
  [b]Ctrl+y[/b]       Allow (NEEDS INPUT sessions only)
  [b]Ctrl+a[/b]       Allow always (NEEDS INPUT sessions only)
  [b]Ctrl+s[/b]       Session manager (load/unload)
  [b]Ctrl+n[/b]       New session
  [b]Ctrl+r[/b]       Quick prototype
  [b]F2[/b]            Rename session
  [b]Ctrl+w[/b]       Kill agent pane
  [b]Ctrl+x[/b]       Kill entire tmux session
  [b]Esc[/b]          Close picker

[b]Views[/b]
  [b]Tab[/b]          Toggle list / grid view
  [b]Ctrl+o[/b]       Cycle sort: status → name → agent

[b]Settings[/b]
  [b]Ctrl+e[/b]       Open config in editor
  [b]Ctrl+t[/b]       Cycle color theme

[b]Search[/b]
  Type to fuzzy-filter sessions.
  Best match is auto-selected.

[b]F1[/b]        Toggle this help
"""

_STATUS_LABEL = {
    SessionStatus.WAITING_INPUT: "[bold red]NEEDS INPUT[/bold red]",
    SessionStatus.RUNNING: "[bold yellow]WORKING[/bold yellow]",
    SessionStatus.IDLE: "[bold #00D26A]IDLE[/bold #00D26A]",
    SessionStatus.DEAD: "[dim]EXITED[/dim]",
}


def _get_all_session_ages() -> dict[str, str]:
    """Batch-fetch session ages from tmux in a single call."""
    try:
        raw = run_tmux("list-sessions", "-F", "#{session_name}:#{session_created}")
        now = time.time()
        ages = {}
        for line in raw.splitlines():
            parts = line.split(":", 1)
            if len(parts) == 2:
                ages[parts[0]] = _human_duration(int(now - int(parts[1])))
        return ages
    except Exception:
        return {}


def _format_line1(session: Session, ages: dict[str, str] | None = None, current: bool = False, show_window: bool = False) -> str:
    icon = session.status_icon
    agent = session.agent_icon
    label = _STATUS_LABEL.get(session.status, "")
    age = (ages or {}).get(session.name, "")
    age_str = f"  [dim]⏱ {age}[/dim]" if age else ""
    here = "  [#7aa2f7]◄ you[/]" if current else ""
    window = f"[dim]:{session.window_index}[/dim]" if show_window else ""
    return f"{icon}  {agent} [b]{session.name}[/b]{window}{here}  {label}{age_str}"


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
    topic = session.last_message or topics.get(session.path, "")
    if not topic:
        return ""
    topic = topic.strip().split("\n")[0]
    if len(topic) > 80:
        topic = topic[:77] + "..."
    return f"    [dim italic]💬 {topic}[/dim italic]"


def _make_item(session: Session, topics: dict[str, str], ages: dict[str, str] | None = None, current_session: str = "", name_counts: dict[str, int] | None = None) -> ListItem:
    is_current = session.name == current_session
    show_window = (name_counts or {}).get(session.name, 0) > 1
    children = [
        Static(_format_line1(session, ages, current=is_current, show_window=show_window)),
        Static(_format_line2(session)),
        Static(_format_line3(session)),
    ]
    topic_line = _format_topic(session, topics)
    if topic_line:
        children.append(Static(topic_line))
    lines = Vertical(*children, classes="session-item")
    classes = "current-session" if is_current else ""
    return ListItem(lines, classes=classes)


def _capture_pane(session: Session) -> str:
    """Capture the current visible content of a tmux pane."""
    target = f"{session.name}:{session.window_index}.{session.pane_index}"
    try:
        raw = run_tmux("capture-pane", "-t", target, "-p", "-e")
        return _BG_COLOR_RE.sub("", raw)
    except Exception:
        return ""


def _human_duration(seconds: float) -> str:
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
    parts = []
    name = session.name
    try:
        created = int(run_tmux("display-message", "-t", name, "-p", "#{session_created}"))
        age = _human_duration(time.time() - created)
        parts.append(f"  ⏱  Session age: [b]{age}[/b]")
    except (ValueError, Exception):
        pass
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
    total = len(sessions)
    by_status = {}
    for s in sessions:
        by_status[s.status] = by_status.get(s.status, 0) + 1
    parts = []
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
    try:
        with open("/proc/loadavg") as f:
            load_1, load_5, load_15, *_ = f.read().split()
        parts.append(f"  📊 Load: {load_1} / {load_5} / {load_15}")
    except Exception:
        pass
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
    try:
        pid_raw = run_tmux("display-message", "-p", "#{pid}")
        if pid_raw:
            stat = f"/proc/{pid_raw}/stat"
            with open(stat) as f:
                fields = f.read().split()
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


def _fuzzy_score(query: str, text: str) -> int:
    """Score a fuzzy match — higher is better. 0 means no match.

    Scoring: prefix match bonus, consecutive char bonus, shorter name bonus.
    """
    q = query.lower()
    t = text.lower()
    qi = 0
    score = 0
    prev_pos = -2
    for pos, char in enumerate(t):
        if qi < len(q) and char == q[qi]:
            score += 10
            # Bonus for consecutive matches
            if pos == prev_pos + 1:
                score += 5
            # Bonus for matching at start
            if pos == qi:
                score += 3
            prev_pos = pos
            qi += 1
    if qi < len(q):
        return 0  # Not a full match
    # Bonus for shorter names (more specific match)
    score += max(0, 20 - len(t))
    return score


def _grid_columns(count: int) -> int:
    """Determine number of grid columns based on session count."""
    if count <= 2:
        return 1
    if count <= 4:
        return 2
    return 3


class NagareCommands(Provider):
    """Command palette provider for nagare picker actions."""

    def _commands(self):
        quick_path = getattr(getattr(self.app, "_config", None), "quick_project_path", "~/Prototypes")
        return [
        ("New Session", "Create a new tmux session with an agent (Ctrl+n)", "_new_session"),
        ("Quick Prototype", f"Fast prototype in {quick_path} (Ctrl+r)", "_quick_prototype"),
        ("Session Manager", "Load/unload registered sessions (Ctrl+s)", "_session_manager"),
        ("Toggle Grid View", "Switch between list and grid (Tab)", "_toggle_view"),
        ("Cycle Sort", "Cycle sort: status → name → agent (Ctrl+o)", "_cycle_sort"),
        ("Cycle Theme", "Change color theme (Ctrl+t)", "_cycle_theme"),
        ("Open Config", "Edit config file in editor (Ctrl+e)", "_open_config"),
        ("Help", "Show keyboard shortcuts (F1)", "_toggle_help"),
        ("Allow", "Send allow to NEEDS INPUT session (Ctrl+y)", "_quick_approve"),
        ("Allow Always", "Send allow-always to NEEDS INPUT session (Ctrl+a)", "_quick_approve_always"),
        ("Rename Session", "Rename the selected session (F2)", "_rename_session"),
        ("Kill Agent Pane", "Kill the selected agent pane (Ctrl+w)", "_kill_agent_pane"),
        ("Kill Session", "Kill the entire tmux session (Ctrl+x)", "_kill_tmux_session"),
        ]

    def _make_callback(self, method_name: str):
        """Create a callback that calls an app method."""
        def callback() -> None:
            try:
                method = getattr(self.app, method_name, None)
                if method:
                    method()
            except Exception:
                logger.exception("command palette: %s failed", method_name)
        return callback

    async def discover(self) -> Hits:
        for name, help_text, method_name in self._commands():
            yield DiscoveryHit(name, self._make_callback(method_name), help=help_text)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, help_text, method_name in self._commands():
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), self._make_callback(method_name), help=help_text)


class PickerApp(App):
    CSS_PATH = "pick.tcss"
    TITLE = "nagare pick"
    COMMANDS = {NagareCommands}

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
        self._anim_config = AnimationConfig()
        self._rename_mode = False
        self._renaming_session: Session | None = None
        self._sort_mode = "status"
        self._help_visible = False
        self._view_mode = "list"  # "list" or "grid"
        self._grid_selected = 0  # Index in _filtered_sessions for grid
        self._grid_generation = 0  # Increments each rebuild to avoid duplicate IDs
        self._grid_refresh_interval = 0.5
        self._grid_timer: Timer | None = None
        self._list_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="title-bar")
        yield Input(placeholder="Search sessions...", id="search")
        # List view (default)
        with Horizontal(id="list-view"):
            with Vertical(id="left-panel"):
                yield ListView(id="session-list")
                yield Static(id="dashboard")
            with Vertical(id="right-panel"):
                yield Static(id="session-details")
                yield ProgressBar(total=100, show_eta=False, show_percentage=True, id="ctx-progress")
                yield Rule(id="detail-rule")
                with VerticalScroll(id="preview-scroll"):
                    yield Static(id="preview-content")
        # Grid view (hidden initially)
        yield VerticalScroll(id="grid-view")
        # Help overlay (hidden initially)
        yield Static(_HELP_TEXT, id="help-overlay")
        yield Static(id="hint-bar")

    def on_exception(self, error: Exception) -> None:
        """Log any unhandled Textual exceptions."""
        logger.exception("Unhandled Textual exception: %s", error)

    def on_mount(self) -> None:
        config = load_config()
        self._config = config
        self._anim_config = config.animation
        self._grid_refresh_interval = config.grid_refresh_interval
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
        self.query_one("#search", Input).focus()
        # Hide grid view and help initially
        self.query_one("#grid-view").display = False
        self.query_one("#help-overlay").display = False
        self.call_after_refresh(self._deferred_init)

    def _deferred_init(self) -> None:
        # Auto-register any new sessions we discovered
        try:
            from nagare.registry import SessionRegistry
            registry = SessionRegistry()
            for s in self._sessions:
                if not registry.find(s.name):
                    registry.register(s.name, s.path, s.agent_type.value)
        except Exception:
            pass
        self._update_dashboard()
        session = self._get_highlighted_session()
        if session is not None:
            self._update_preview(session)
        self._state_timer = self.set_interval(2, self._poll_state)
        self._list_timer = self.set_interval(1, self._poll_preview)

    def _select_current_session(self) -> None:
        if not self._current_session:
            return
        lv = self.query_one("#session-list", ListView)
        for i, session in enumerate(self._filtered_sessions):
            if session.name == self._current_session:
                lv.index = i
                self._grid_selected = i
                break

    def _refresh_sessions(self) -> None:
        self._sessions = _sort_sessions(scan_sessions(), self._sort_mode)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.query_one("#search", Input).value.strip()
        if not query:
            self._filtered_sessions = list(self._sessions)
        else:
            # Score and sort by best match
            scored = [
                (s, score)
                for s in self._sessions
                if (score := _fuzzy_score(query, s.name)) > 0
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            self._filtered_sessions = [s for s, _ in scored]

        if self._view_mode == "list":
            self._rebuild_list()
        else:
            self._rebuild_grid()

        # Select the best match (first item after sorting)
        if self._filtered_sessions:
            if self._view_mode == "list":
                self.query_one("#session-list", ListView).index = 0
            else:
                self._grid_selected = 0
                self._update_grid_selection()

        self._update_title_bar()

    async def _poll_state(self) -> None:
        try:
            highlighted = self._get_highlighted_session()
            highlighted_name = highlighted.name if highlighted else None

            old_snapshot = {s.name: s.status for s in self._sessions}
            new_sessions = await asyncio.to_thread(
                lambda: _sort_sessions(scan_sessions(), self._sort_mode)
            )
            new_snapshot = {s.name: s.status for s in new_sessions}
            self._sessions = new_sessions
            if old_snapshot != new_snapshot:
                self._apply_filter()
                # Restore selection by name, fall back to 0
                restored = False
                if highlighted_name:
                    for i, s in enumerate(self._filtered_sessions):
                        if s.name == highlighted_name:
                            if self._view_mode == "list":
                                self.query_one("#session-list", ListView).index = i
                            else:
                                self._grid_selected = i
                                self._update_grid_selection()
                            restored = True
                            break
                if not restored and self._filtered_sessions:
                    if self._view_mode == "list":
                        self.query_one("#session-list", ListView).index = 0
                    else:
                        self._grid_selected = 0
                        self._update_grid_selection()

            # Ensure list view always has a valid selection
            if self._view_mode == "list" and self._filtered_sessions:
                lv = self.query_one("#session-list", ListView)
                if lv.index is None:
                    lv.index = 0

            if self._view_mode == "list":
                self._update_dashboard()
        except Exception:
            logger.exception("poll_state failed")

    async def _poll_preview(self) -> None:
        if self._view_mode != "list":
            return
        session = self._get_highlighted_session()
        if session is not None:
            await self._update_preview_async(session)

    async def _poll_grid(self) -> None:
        if self._view_mode != "grid":
            return
        await self._update_grid_previews_async()

    def _get_highlighted_session(self) -> Session | None:
        if self._view_mode == "list":
            lv = self.query_one("#session-list", ListView)
            idx = lv.index
            if idx is not None and 0 <= idx < len(self._filtered_sessions):
                return self._filtered_sessions[idx]
        else:
            if 0 <= self._grid_selected < len(self._filtered_sessions):
                return self._filtered_sessions[self._grid_selected]
        return None

    def _update_preview(self, session: Session) -> None:
        """Sync preview update — blocks on tmux calls. Used for immediate UI feedback."""
        from nagare.tmux.status import parse_details as _parse_details
        self._preview_session = session
        label = _STATUS_LABEL.get(session.status, "")
        header = f"{session.status_icon}  [b]{session.name}[/b]  {label}\n"
        details = _get_session_details(session)
        self.query_one("#session-details", Static).update(header + details)

        content = _capture_pane(session)
        # Parse context usage from the pane content
        pane_details = _parse_details(content)
        self._update_context_progress(pane_details.context_usage)
        self._apply_preview_content(content)

    async def _update_preview_async(self, session: Session) -> None:
        """Async preview update — offloads tmux calls to a thread."""
        try:
            from nagare.tmux.status import parse_details as _parse_details
            self._preview_session = session
            label = _STATUS_LABEL.get(session.status, "")
            header = f"{session.status_icon}  [b]{session.name}[/b]  {label}\n"
            details, content = await asyncio.to_thread(
                lambda: (_get_session_details(session), _capture_pane(session))
            )
            # UI updates on main thread
            self.query_one("#session-details", Static).update(header + details)
            pane_details = _parse_details(content)
            self._update_context_progress(pane_details.context_usage)
            self._apply_preview_content(content)
        except Exception:
            logger.exception("update_preview_async failed")

    def _update_context_progress(self, ctx: str = "") -> None:
        """Update the context usage progress bar.

        Args:
            ctx: Context string like "17%" from the pane status bar.
        """
        try:
            progress = self.query_one("#ctx-progress", ProgressBar)
            if ctx:
                value = int(ctx.replace("%", ""))
                progress.update(progress=value)
                progress.display = True
            else:
                progress.display = False
        except Exception:
            pass

    def _apply_preview_content(self, content: str) -> None:
        """Apply captured pane content to the preview widget."""
        lines = content.rstrip("\n").split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        try:
            panel = self.query_one("#preview-scroll")
            max_width = panel.size.width - 2
            if max_width > 0:
                lines = [line[:max_width] for line in lines]
        except Exception:
            pass
        rich_text = Text.from_ansi("\n".join(lines))
        self.query_one("#preview-content", Static).update(rich_text)
        self.query_one("#preview-scroll").scroll_end(animate=False)

    def _update_dashboard(self) -> None:
        stats = _get_dashboard_stats(self._sessions)
        self.query_one("#dashboard", Static).update(stats)

    # ── Grid view ──

    def _rebuild_grid(self) -> None:
        """Rebuild the grid with session cells."""
        container = self.query_one("#grid-view")

        # Use a unique generation ID to avoid DuplicateIds errors.
        # Textual's remove() is async so old widgets may linger briefly.
        self._grid_generation += 1
        gen = self._grid_generation

        for child in list(container.children):
            child.remove()

        if not self._filtered_sessions:
            container.mount(Static("[dim]No matching sessions[/dim]"))
            return

        cols = _grid_columns(len(self._filtered_sessions))
        cells = []
        for i, session in enumerate(self._filtered_sessions):
            cells.append(self._make_grid_cell(session, i, gen))

        grid = Grid(*cells, id=f"session-grid-{gen}", classes=f"grid-cols-{cols}")
        container.mount(grid)
        self._update_grid_selection()

    def _make_grid_cell(self, session: Session, index: int, gen: int = 0) -> Vertical:
        """Create a single grid cell widget for a session."""
        icon = session.status_icon
        label = _STATUS_LABEL.get(session.status, "")
        topic = session.last_message or self._topics.get(session.path, "")
        if topic:
            topic = topic.strip().split("\n")[0]
            if len(topic) > 60:
                topic = topic[:57] + "..."

        d = session.details
        branch = f" {d.git_branch}" if d.git_branch else ""

        # Block art on the left (3 lines)
        block = session.agent_block
        block_widget = Static(
            f"{block[0]}\n{block[1]}\n{block[2]}",
            classes="cell-block",
        )

        # Session info on the right
        is_current = session.name == self._current_session
        here = "  [#7aa2f7]◄ you[/]" if is_current else ""
        info_lines = [
            Static(f"{icon} [b]{session.name}[/b]{here}  {label}", classes="cell-title"),
            Static(f"📁 {session.path}{branch}", classes="cell-meta"),
        ]
        if topic:
            info_lines.append(Static(f"[dim]💬 {topic}[/dim]", classes="cell-topic"))
        info_widget = Vertical(*info_lines, classes="cell-info")

        header_box = Horizontal(block_widget, info_widget, classes="cell-header")

        preview = VerticalScroll(
            Static("", id=f"cell-preview-{gen}-{index}"),
            classes="cell-preview",
        )

        cell = Vertical(
            header_box, preview,
            id=f"cell-{gen}-{index}",
            classes="grid-cell",
        )
        return cell

    def _update_grid_previews(self) -> None:
        """Update all grid cell pane captures (sync — used for immediate refresh)."""
        self._apply_grid_previews(
            [(i, _capture_pane(s)) for i, s in enumerate(self._filtered_sessions)]
        )

    async def _update_grid_previews_async(self) -> None:
        """Update all grid cell pane captures (async — offloads tmux to thread)."""
        try:
            sessions = list(enumerate(self._filtered_sessions))
            captures = await asyncio.to_thread(
                lambda: [(i, _capture_pane(s)) for i, s in sessions]
            )
            self._apply_grid_previews(captures)
        except Exception:
            logger.exception("update_grid_previews_async failed")

    def _apply_grid_previews(self, captures: list[tuple[int, str]]) -> None:
        """Apply captured pane contents to grid preview widgets."""
        gen = self._grid_generation
        for i, content in captures:
            try:
                preview_widget = self.query_one(f"#cell-preview-{gen}-{i}", Static)
            except Exception:
                continue

            lines = content.rstrip("\n").split("\n")
            while lines and not lines[0].strip():
                lines.pop(0)

            try:
                cell = self.query_one(f"#cell-{gen}-{i}")
                max_width = cell.size.width - 4
                if max_width > 0:
                    lines = [line[:max_width] for line in lines]
            except Exception:
                pass

            rich_text = Text.from_ansi("\n".join(lines))
            preview_widget.update(rich_text)

            try:
                scroll = preview_widget.parent
                if hasattr(scroll, "scroll_end"):
                    scroll.scroll_end(animate=False)
            except Exception:
                pass

        self._update_grid_selection()

    def _update_grid_selection(self) -> None:
        """Highlight the selected grid cell with a bright border."""
        gen = self._grid_generation
        for i in range(len(self._filtered_sessions)):
            try:
                cell = self.query_one(f"#cell-{gen}-{i}")
            except Exception:
                continue

            if i == self._grid_selected:
                cell.styles.border = ("solid", "#7aa2f7")  # tokyonight primary
            else:
                cell.styles.border = ("solid", "#313552")  # subtle muted

    # ── View toggle ──

    def _toggle_view(self) -> None:
        """Switch between list and grid view."""
        highlighted = self._get_highlighted_session()
        highlighted_name = highlighted.name if highlighted else None
        logger.info("toggle view: %s -> %s (%d sessions)",
                    self._view_mode, "grid" if self._view_mode == "list" else "list",
                    len(self._filtered_sessions))

        if self._view_mode == "list":
            self._view_mode = "grid"
            self.query_one("#list-view").display = False
            self.query_one("#grid-view").display = True
            # Stop list timer, start grid timer
            if self._list_timer:
                self._list_timer.stop()
            self._rebuild_grid()
            self._update_grid_previews()
            self._grid_timer = self.set_interval(
                self._grid_refresh_interval, self._poll_grid
            )
        else:
            self._view_mode = "list"
            self.query_one("#list-view").display = True
            self.query_one("#grid-view").display = False
            # Stop grid timer, start list timer
            if self._grid_timer:
                self._grid_timer.stop()
            self._list_timer = self.set_interval(1, self._poll_preview)

        # Restore selection by name, fall back to 0
        restored = False
        if highlighted_name:
            for i, s in enumerate(self._filtered_sessions):
                if s.name == highlighted_name:
                    if self._view_mode == "list":
                        self.query_one("#session-list", ListView).index = i
                    else:
                        self._grid_selected = i
                        self._update_grid_selection()
                    restored = True
                    break
        if not restored and self._filtered_sessions:
            if self._view_mode == "list":
                self.query_one("#session-list", ListView).index = 0
            else:
                self._grid_selected = 0
                self._update_grid_selection()

        self._update_hint_bar()

    # ── Events ──

    async def on_app_focus(self, event) -> None:
        """Refresh all data immediately when the picker regains focus."""
        try:
            new_sessions = await asyncio.to_thread(
                lambda: _sort_sessions(scan_sessions(), self._sort_mode)
            )
            self._sessions = new_sessions
            self._apply_filter()
            if self._view_mode == "grid":
                await self._update_grid_previews_async()
            else:
                session = self._get_highlighted_session()
                if session is not None:
                    await self._update_preview_async(session)
        except Exception:
            logger.exception("on_app_focus failed")

    def on_input_changed(self, event: Input.Changed) -> None:
        if not self._rename_mode:
            self._apply_filter()

    def _rebuild_list(self) -> None:
        lv = self.query_one("#session-list", ListView)
        lv.clear()
        if self._filtered_sessions:
            ages = _get_all_session_ages()
            # Count how many agents share each session name
            name_counts: dict[str, int] = {}
            for s in self._filtered_sessions:
                name_counts[s.name] = name_counts.get(s.name, 0) + 1
            for session in self._filtered_sessions:
                lv.append(_make_item(session, self._topics, ages, self._current_session, name_counts))
            # Defer index setting so the DOM has the new items first
            self.call_after_refresh(self._ensure_list_selection, 0)
        else:
            lv.append(ListItem(Static("[dim]No matching sessions[/dim]")))

    def _ensure_list_selection(self, index: int) -> None:
        """Force highlight on a list item after the DOM has refreshed."""
        lv = self.query_one("#session-list", ListView)
        if not self._filtered_sessions:
            return
        index = min(index, len(self._filtered_sessions) - 1)
        # Reset to None first to force the watcher to fire
        lv.index = None
        lv.index = index

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
        mode = "grid" if self._view_mode == "grid" else "list"
        parts = [f"[b]nagare[/b]  ·  {count} sessions  ·  {mode}"]
        if waiting:
            parts.append(f"  🟡 {waiting} need{'s' if waiting == 1 else ''} input")
        self.query_one("#title-bar", Static).update("".join(parts))

    def _jump_to_session(self, session) -> None:
        """Animate the selected widget then jump to the tmux session."""
        target = f"{session.name}:{session.window_index}.{session.pane_index}"

        widget = self._get_selected_widget()
        anim = self._anim_config

        if not widget or anim.jump_animation == "none":
            self._do_jump(target)
            return

        name = anim.jump_animation
        if name == "flash":
            self._anim_flash(widget, target, anim.flash_duration)
        elif name == "pulse":
            self._anim_pulse(widget, target, anim.pulse_duration)
        elif name == "fade":
            self._anim_fade(widget, target, anim.fade_duration)
        elif name == "sweep":
            self._anim_sweep(widget, target, anim.sweep_duration)
        elif name == "shrink":
            self._anim_shrink(widget, target, anim.shrink_duration)
        else:
            self._do_jump(target)

    def _get_selected_widget(self):
        """Get the currently selected widget (list item or grid cell)."""
        if self._view_mode == "list":
            lv = self.query_one("#session-list", ListView)
            if lv.index is not None and 0 <= lv.index < len(lv.children):
                return lv.children[lv.index]
        else:
            gen = self._grid_generation
            try:
                return self.query_one(f"#cell-{gen}-{self._grid_selected}")
            except Exception:
                pass
        return None

    def _anim_flash(self, widget, target: str, duration: float) -> None:
        """Dim → bright → jump."""
        half = duration / 2
        widget.styles.animate(
            "opacity", value=0.3, duration=half,
            on_complete=lambda: widget.styles.animate(
                "opacity", value=1.0, duration=half,
                on_complete=lambda: self._do_jump(target),
            ),
        )

    def _anim_pulse(self, widget, target: str, duration: float) -> None:
        """Dim → bright → dim → bright → jump (two beats)."""
        quarter = duration / 4
        widget.styles.animate(
            "opacity", value=0.3, duration=quarter,
            on_complete=lambda: widget.styles.animate(
                "opacity", value=1.0, duration=quarter,
                on_complete=lambda: widget.styles.animate(
                    "opacity", value=0.3, duration=quarter,
                    on_complete=lambda: widget.styles.animate(
                        "opacity", value=1.0, duration=quarter,
                        on_complete=lambda: self._do_jump(target),
                    ),
                ),
            ),
        )

    def _anim_fade(self, widget, target: str, duration: float) -> None:
        """Fade to transparent → jump."""
        widget.styles.animate(
            "opacity", value=0.0, duration=duration,
            on_complete=lambda: self._do_jump(target),
        )

    def _anim_sweep(self, widget, target: str, duration: float) -> None:
        """Background flash to primary color → jump."""
        from textual.color import Color
        widget.styles.animate(
            "background", value=Color.parse("#7aa2f7"), duration=duration * 0.6,
            on_complete=lambda: widget.styles.animate(
                "opacity", value=0.0, duration=duration * 0.4,
                on_complete=lambda: self._do_jump(target),
            ),
        )

    def _anim_shrink(self, widget, target: str, duration: float) -> None:
        """Collapse height → jump."""
        widget.styles.animate(
            "opacity", value=0.0, duration=duration,
            on_complete=lambda: self._do_jump(target),
        )
        widget.styles.animate("height", value=1, duration=duration)

    def _do_jump(self, target: str) -> None:
        """Actually switch to the tmux session and exit."""
        run_tmux("switch-client", "-t", target)
        self.exit()

    def _jump_to_highlighted(self) -> None:
        session = self._get_highlighted_session()
        if session:
            self._jump_to_session(session)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        lv = self.query_one("#session-list", ListView)
        idx = lv.index
        if idx is not None and 0 <= idx < len(self._filtered_sessions):
            self._jump_to_session(self._filtered_sessions[idx])

    def _is_command_palette_open(self) -> bool:
        """Check if the command palette is currently open."""
        from textual.command import CommandPalette
        try:
            return any(isinstance(s, CommandPalette) for s in self.screen_stack)
        except Exception:
            return False

    _KEY_DISPATCH = {
        "f1": "_toggle_help",
        "tab": "_toggle_view",
        "ctrl+y": "_quick_approve",
        "ctrl+a": "_quick_approve_always",
        "ctrl+w": "_kill_agent_pane",
        "ctrl+x": "_kill_tmux_session",
        "ctrl+o": "_cycle_sort",
        "ctrl+s": "_session_manager",
        "ctrl+n": "_new_session",
        "ctrl+r": "_quick_prototype",
        "ctrl+e": "_open_config",
        "f2": "_rename_session",
    }

    def on_key(self, event) -> None:
        # Don't handle keys when command palette is open
        if self._is_command_palette_open():
            return
        # Handle rename mode
        if self._rename_mode:
            if event.key == "enter":
                self._finish_rename()
                event.prevent_default()
                event.stop()
            elif event.key == "escape":
                self._rename_mode = False
                self._renaming_session = None
                self.query_one("#search", Input).value = ""
                self._update_title_bar()
                event.prevent_default()
                event.stop()
            return
        # Any key dismisses help
        if self._help_visible:
            self._toggle_help()
            event.prevent_default()
            event.stop()
            return

        method_name = self._KEY_DISPATCH.get(event.key)
        if method_name is not None:
            getattr(self, method_name)()
            event.prevent_default()
            event.stop()
        elif self._view_mode == "list":
            self._handle_list_key(event)
        else:
            self._handle_grid_key(event)

    def _handle_list_key(self, event) -> None:
        if event.key in ("down", "up"):
            lv = self.query_one("#session-list", ListView)
            if event.key == "down":
                lv.action_cursor_down()
            else:
                lv.action_cursor_up()
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

    def _handle_grid_key(self, event) -> None:
        n = len(self._filtered_sessions)
        if n == 0:
            return

        cols = _grid_columns(n)
        old = self._grid_selected

        if event.key == "right":
            self._grid_selected = min(self._grid_selected + 1, n - 1)
        elif event.key == "left":
            self._grid_selected = max(self._grid_selected - 1, 0)
        elif event.key == "down":
            new = self._grid_selected + cols
            if new < n:
                self._grid_selected = new
        elif event.key == "up":
            new = self._grid_selected - cols
            if new >= 0:
                self._grid_selected = new
        elif event.key == "enter":
            self._jump_to_highlighted()
            event.prevent_default()
            event.stop()
            return
        elif event.key == "ctrl+t":
            self._cycle_theme()
            event.prevent_default()
            event.stop()
            return
        else:
            return

        if old != self._grid_selected:
            self._update_grid_selection()
        event.prevent_default()
        event.stop()

    def _quick_approve(self) -> None:
        """Send Enter to the selected session if it needs input."""
        session = self._get_highlighted_session()
        if session is None:
            return
        if session.status != SessionStatus.WAITING_INPUT:
            return
        target = f"{session.name}:{session.window_index}.{session.pane_index}"
        try:
            run_tmux("send-keys", "-t", target, "Enter")
            logger.info("quick approve sent to %s", session.name)
            self.notify(f"Allowed {session.name}", severity="information")
        except Exception:
            logger.exception("quick approve failed for %s", session.name)

    def _quick_approve_always(self) -> None:
        """Send Down + Enter to select 'Allow always' if session needs input."""
        session = self._get_highlighted_session()
        if session is None:
            return
        if session.status != SessionStatus.WAITING_INPUT:
            return
        target = f"{session.name}:{session.window_index}.{session.pane_index}"
        try:
            run_tmux("send-keys", "-t", target, "Down", "Enter")
            logger.info("quick approve always sent to %s", session.name)
            self.notify(f"Always allowed {session.name}", severity="information")
        except Exception:
            logger.exception("quick approve always failed for %s", session.name)

    def _kill_agent_pane(self) -> None:
        """Kill just the agent pane, leave the tmux session alive."""
        session = self._get_highlighted_session()
        if session is None:
            return
        target = f"{session.name}:{session.window_index}.{session.pane_index}"
        try:
            mark_path_dead(session.path)
            run_tmux("kill-pane", "-t", target)
            logger.info("killed agent pane %s", target)
            self.notify(f"Killed agent in {session.name}", severity="warning")
        except Exception:
            logger.exception("kill pane failed for %s", target)
        self._refresh_sessions()

    def _kill_tmux_session(self) -> None:
        """Kill the entire tmux session."""
        session = self._get_highlighted_session()
        if session is None:
            return
        name = session.name
        try:
            mark_path_dead(session.path)
            run_tmux("kill-session", "-t", name)
            logger.info("killed tmux session %s", name)
            self.notify(f"Killed session {name}", severity="warning")
        except Exception:
            logger.exception("kill session failed for %s", name)
        self._refresh_sessions()

    def _cycle_sort(self) -> None:
        """Cycle through sort modes: status → name → agent."""
        idx = _SORT_MODES.index(self._sort_mode)
        self._sort_mode = _SORT_MODES[(idx + 1) % len(_SORT_MODES)]
        self._sessions = _sort_sessions(self._sessions, self._sort_mode)
        self._apply_filter()
        self._update_hint_bar()
        self._update_title_bar()

    def _toggle_help(self) -> None:
        """Show/hide the help overlay."""
        self._help_visible = not self._help_visible
        overlay = self.query_one("#help-overlay")
        overlay.display = self._help_visible
        if self._help_visible:
            # Hide the main views
            self.query_one("#list-view").display = False
            self.query_one("#grid-view").display = False
        else:
            # Restore the correct view
            if self._view_mode == "list":
                self.query_one("#list-view").display = True
            else:
                self.query_one("#grid-view").display = True

    def _new_session(self) -> None:
        """Exit picker with a signal to open the new-session form."""
        self.exit(result="new_session")

    def _quick_prototype(self) -> None:
        """Exit picker with a signal to open the quick prototype form."""
        self.exit(result="quick_prototype")

    def _rename_session(self) -> None:
        """Start renaming the selected session."""
        session = self._get_highlighted_session()
        if session is None:
            return
        self._renaming_session = session
        # Show rename input in the title bar area
        self.query_one("#title-bar", Static).update(
            f"  Rename [b]{session.name}[/b] to: "
        )
        search = self.query_one("#search", Input)
        search.value = session.name
        search.select_all()
        search.focus()
        self._rename_mode = True

    def _finish_rename(self) -> None:
        """Complete the rename operation."""
        search = self.query_one("#search", Input)
        new_name = search.value.strip()
        session = self._renaming_session
        self._rename_mode = False
        self._renaming_session = None
        search.value = ""

        if not new_name or not session or new_name == session.name:
            self._update_title_bar()
            return

        old_name = session.name
        try:
            # Check if target name already exists
            existing_sessions = set(run_tmux("list-sessions", "-F", "#{session_name}").splitlines())
            if new_name in existing_sessions:
                self.notify(f"Session '{new_name}' already exists", severity="error")
                return

            # Check if this session has multiple agents — if so, rename
            # the window instead of the whole tmux session
            sibling_count = sum(
                1 for s in self._sessions if s.name == old_name
            )
            if sibling_count > 1:
                target = f"{old_name}:{session.window_index}"
                run_tmux("rename-window", "-t", target, new_name)
                logger.info("renamed tmux window %s -> %s", target, new_name)
                self.notify(f"Renamed window → {new_name}", severity="information")
            else:
                run_tmux("rename-session", "-t", old_name, new_name)
                logger.info("renamed tmux session %s -> %s", old_name, new_name)
                self.notify(f"Renamed {old_name} → {new_name}", severity="information")

                from nagare.registry import SessionRegistry
                reg = SessionRegistry()
                existing = reg.find(old_name)
                if existing:
                    reg.remove(old_name)
                    reg.register(new_name, existing.path, existing.agent)

                if self._current_session == old_name:
                    self._current_session = new_name

            self._refresh_sessions()
        except Exception:
            logger.exception("rename failed: %s -> %s", old_name, new_name)
            self.notify(f"Rename failed: {old_name} → {new_name}", severity="error")
            return

        self._update_title_bar()

    def _session_manager(self) -> None:
        """Exit picker with a signal to open the session manager."""
        self.exit(result="session_manager")

    def _open_config(self) -> None:
        """Ensure config has all sections, then open in editor."""
        import subprocess as sp
        from pathlib import Path
        from nagare.config import CONFIG_PATH
        from nagare.setup import _DEFAULT_CONFIG

        path = Path(CONFIG_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(_DEFAULT_CONFIG)
        else:
            # Append any missing sections from the default config
            content = path.read_text()
            missing = []
            for section in ["[animation]", "[appearance]", "[picker]"]:
                if section not in content:
                    # Extract that section from the default config
                    lines = _DEFAULT_CONFIG.splitlines()
                    capturing = False
                    section_lines = []
                    for line in lines:
                        if line.strip() == section or (
                            capturing and line.startswith("# ── ")
                        ):
                            if capturing:
                                break
                            capturing = True
                        if capturing:
                            section_lines.append(line)
                    if section_lines:
                        missing.append("\n".join(section_lines))
            if missing:
                path.write_text(
                    content.rstrip() + "\n\n" + "\n\n".join(missing) + "\n"
                )

        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
        self.exit()
        sp.run([editor, str(path)])

    def _update_hint_bar(self) -> None:
        name = self._theme_names[self._theme_index]
        sort_label = {"status": "status", "name": "A→Z", "agent": "agent"}
        if self._view_mode == "list":
            nav = "[b]↑/↓[/b] Navigate"
        else:
            nav = "[b]↑/↓/←/→[/b] Navigate"

        hint = self.query_one("#hint-bar", Static)
        hint.update(
            f"[#7aa2f7][b]Ctrl+s[/b] Sessions  [b]Ctrl+n[/b] New  [b]Ctrl+r[/b] Prototype[/]  [b]F1[/b] Help  [b]Tab[/b] View  {nav}  [b]Enter[/b] Jump"
            f"  [#00D26A][b]Ctrl+y[/b] Allow[/]  [#00D26A][b]Ctrl+a[/b] Allow always[/]  [#db4b4b][b]Ctrl+w[/b] Kill  [b]Ctrl+x[/b] Kill session[/]"
            f"  [b]Ctrl+o[/b] Sort:[b]{sort_label[self._sort_mode]}[/b]"
            f"  [b]Ctrl+e[/b] Config  [b]Ctrl+t[/b] Theme  [b]Esc[/b] Cancel"
            f"  │  🎨 {name}"
        )

    def _cycle_theme(self) -> None:
        self._theme_index = (self._theme_index + 1) % len(self._theme_names)
        name = self._theme_names[self._theme_index]
        self.theme = name
        save_theme(name)
        self._update_hint_bar()

