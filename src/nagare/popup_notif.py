import argparse

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from nagare.config import load_config
from nagare.themes import THEMES
from nagare.tmux import run_tmux


def _human_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


class PopupNotifApp(App):
    CSS_PATH = "popup_notif.tcss"
    TITLE = "nagare notification"

    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss", show=False),
        Binding("enter", "jump", "Jump to session", show=False),
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
        with Vertical(id="popup-container"):
            yield Static(id="header")
            yield Static(id="subtitle")
            yield Static(id="message-body")
            yield Static("", id="divider")
            yield Static(id="hint-bar")
            yield Static(id="countdown")

    def on_mount(self) -> None:
        config = load_config()
        for t in THEMES.values():
            self.register_theme(t)
        saved = config.theme if config.theme in THEMES else "tokyonight"
        self.theme = saved

        # Header: icon + session name
        if self._event_type == "needs_input":
            icon = "[#db4b4b]\u25cf[/]"
            subtitle = "[bold #db4b4b]NEEDS PERMISSION[/bold #db4b4b]"
        else:
            icon = "[#00D26A]\u25cf[/]"
            duration_str = _human_duration(self._working_seconds) if self._working_seconds else ""
            suffix = f" (worked {duration_str})" if duration_str else ""
            subtitle = f"[bold #00D26A]TASK COMPLETE{suffix}[/bold #00D26A]"

        self.query_one("#header", Static).update(
            f"  {icon}  [b]{self._session_name}[/b]"
        )
        self.query_one("#subtitle", Static).update(f"  {subtitle}")

        # Message body
        msg = self._message or ""
        # Truncate long messages
        lines = msg.strip().split("\n")
        display = "\n     ".join(lines[:4])
        if len(lines) > 4:
            display += "..."
        if len(display) > 200:
            display = display[:197] + "..."
        self.query_one("#message-body", Static).update(f"  \U0001f4ac {display}")

        self.query_one("#divider", Static).update("  " + "\u2500" * 36)
        self.query_one("#hint-bar", Static).update(
            "  [b]Enter[/b]: Jump to session   [b]Esc[/b]: Dismiss"
        )
        self._update_countdown()
        self.set_interval(1, self._tick)

    def _tick(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self.exit()
            return
        self._update_countdown()

    def _update_countdown(self) -> None:
        self.query_one("#countdown", Static).update(
            f"  [dim]Auto-closing in {self._countdown}s...[/dim]"
        )

    def action_dismiss(self) -> None:
        self.exit()

    def action_jump(self) -> None:
        try:
            run_tmux("switch-client", "-t", self._session_name)
        except Exception:
            pass
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
