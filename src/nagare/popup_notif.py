import argparse
import os
import re

from rich.text import Text

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from nagare.config import load_config
from nagare.log import logger
from nagare.themes import THEMES
from nagare.tmux import run_tmux, switch_to_session

# Strip ANSI background color sequences that clash with Textual themes
_BG_COLOR_RE = re.compile(r"\x1b\[(?:48;[25](?:;[\d]+)*|49)m")


def _human_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def _capture_pane(session_name: str) -> str:
    """Capture the visible content of the session's active pane."""
    try:
        raw = run_tmux("capture-pane", "-t", session_name, "-p", "-e")
        return _BG_COLOR_RE.sub("", raw)
    except Exception:
        return ""


class PopupNotifApp(App):
    CSS_PATH = "popup_notif.tcss"
    TITLE = "nagare notification"

    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss", show=False),
        Binding("enter", "jump", "Jump to session", show=False),
        Binding("ctrl+y", "approve", "Allow", show=False),
        Binding("ctrl+a", "approve_always", "Allow always", show=False),
    ]

    def __init__(
        self,
        session_name: str,
        event_type: str,
        message: str = "",
        working_seconds: int = 0,
        popup_timeout: int = 10,
    ) -> None:
        super().__init__()
        self._session_name = session_name
        self._event_type = event_type
        self._message = message
        self._working_seconds = working_seconds
        self._countdown = popup_timeout

    def compose(self) -> ComposeResult:
        yield Static(id="notif-header")
        with VerticalScroll(id="preview-scroll"):
            yield Static(id="preview-content")
        yield Static(id="hint-bar")

    def on_mount(self) -> None:
        config = load_config()
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = config.theme if config.theme in THEMES else "tokyonight"

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        self._update_header()
        self._update_preview()
        self._update_hint_bar()
        self.set_interval(1, self._tick)

    def _update_header(self) -> None:
        if self._event_type == "needs_input":
            icon = "[#db4b4b]●[/]"
            label = "[bold #db4b4b]NEEDS INPUT[/bold #db4b4b]"
        else:
            icon = "[#00D26A]●[/]"
            dur = _human_duration(self._working_seconds) if self._working_seconds else ""
            suffix = f" (worked {dur})" if dur else ""
            label = f"[bold #00D26A]TASK COMPLETE{suffix}[/bold #00D26A]"

        parts = [f" {icon}  [b]{self._session_name}[/b]  {label}"]

        if self._message:
            msg = self._message.strip().split("\n")[0]
            if len(msg) > 100:
                msg = msg[:97] + "..."
            parts.append(f" 💬 {msg}")

        self.query_one("#notif-header", Static).update("\n".join(parts))

    def _update_preview(self) -> None:
        content = _capture_pane(self._session_name)
        if not content.strip():
            self.query_one("#preview-content", Static).update(
                "[dim]No pane content available[/dim]"
            )
            return

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

    def _update_hint_bar(self) -> None:
        if self._event_type == "needs_input":
            approve = "  [#00D26A][b]Ctrl+y[/b] Allow[/]  [#00D26A][b]Ctrl+a[/b] Allow always[/]"
        else:
            approve = ""
        self.query_one("#hint-bar", Static).update(
            f" [b]Enter[/b] Jump to session{approve}"
            f"  [b]Esc[/b] Dismiss"
            f"  │  Auto-closing in {self._countdown}s"
        )

    def _tick(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self.exit()
            return
        self._update_hint_bar()
        self._update_preview()

    def action_dismiss(self) -> None:
        self.exit()

    def action_jump(self) -> None:
        try:
            switch_to_session(self._session_name)
        except Exception:
            pass
        self.exit()

    def action_approve(self) -> None:
        """Send Enter to allow the current permission prompt."""
        if self._event_type != "needs_input":
            return
        try:
            run_tmux("send-keys", "-t", self._session_name, "Enter")
            logger.info("popup approve (allow) sent to %s", self._session_name)
        except Exception:
            logger.exception("popup approve failed for %s", self._session_name)
        self.exit()

    def action_approve_always(self) -> None:
        """Send Down + Enter to select 'Allow always' option."""
        if self._event_type != "needs_input":
            return
        try:
            run_tmux("send-keys", "-t", self._session_name, "Down", "Enter")
            logger.info("popup approve (allow always) sent to %s", self._session_name)
        except Exception:
            logger.exception("popup approve_always failed for %s", self._session_name)
        self.exit()


def run_popup(args: list[str]) -> None:
    """Parse CLI args and run the popup app."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--message", default="")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--duration", type=int, default=0)
    parsed = parser.parse_args(args)
    app = PopupNotifApp(
        session_name=parsed.session,
        event_type=parsed.event,
        message=parsed.message,
        working_seconds=parsed.duration,
        popup_timeout=parsed.timeout,
    )
    app.run()
