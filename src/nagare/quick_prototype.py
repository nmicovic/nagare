"""Quick prototype launcher — minimal form for fast session creation."""

import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, Static, RadioButton, RadioSet

from nagare.config import load_config
from nagare.log import logger
from nagare.session import create_session
from nagare.themes import THEMES
from nagare.tmux import run_tmux


class QuickPrototypeApp(App):
    CSS_PATH = "new_session.tcss"
    TITLE = "nagare quick prototype"

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        config = load_config()
        with Vertical(id="new-session-form"):
            yield Static("[b]Quick Prototype[/b]", id="form-title")
            yield Static(
                f"  Creates session at [b]{config.quick_project_path}/[/b]<name>",
                classes="form-label",
            )
            yield Input(placeholder="project name", id="name-input")
            yield Static("  Agent:", classes="form-label")
            with RadioSet(id="agent-select"):
                yield RadioButton("Claude", value=True, id="agent-claude")
                yield RadioButton("OpenCode", id="agent-opencode")
            yield Static(
                "\n  [b]Enter[/b] Create   [b]Esc[/b] Cancel",
                id="form-hint",
            )

    def on_mount(self) -> None:
        config = load_config()
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = config.theme if config.theme in THEMES else "tokyonight"

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        self.query_one("#name-input", Input).focus()

    def on_key(self, event) -> None:
        if event.key == "enter":
            self._create()
            event.prevent_default()
            event.stop()

    def action_cancel(self) -> None:
        self.exit(result="back_to_picker")

    def _create(self) -> None:
        from pathlib import Path
        from nagare.session import resolve_path

        name = self.query_one("#name-input", Input).value.strip()
        if not name:
            return

        # Check if directory already exists
        resolved = Path(resolve_path(name)).expanduser().resolve()
        if resolved.exists():
            self.query_one("#form-title", Static).update(
                f"[b]Quick Prototype[/b]  [bold red]Directory already exists: {resolved}[/bold red]"
            )
            self.query_one("#name-input", Input).focus()
            return

        radio = self.query_one("#agent-select", RadioSet)
        agent = "opencode" if radio.pressed_index == 1 else "claude"

        try:
            session_name = create_session(
                path=name,
                name=name,
                agent=agent,
                continue_session=False,
            )
            run_tmux("switch-client", "-t", session_name)
            self.exit()
        except (ValueError, RuntimeError) as e:
            logger.exception("Quick prototype failed")
            self.query_one("#form-title", Static).update(
                f"[b]Quick Prototype[/b]  [bold red]Error: {e}[/bold red]"
            )
