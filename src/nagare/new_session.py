"""New session creation form — standalone TUI and picker integration."""

import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, Static, ListView, ListItem, RadioButton, RadioSet, Switch

from nagare.config import load_config
from nagare.log import logger
from nagare.session import create_session, list_directories
from nagare.themes import THEMES
from nagare.tmux import run_tmux, switch_to_session


class NewSessionForm(Vertical):
    """Reusable new-session form widget."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._suggestions: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("[b]New Session[/b]", id="form-title")
        config = load_config()
        yield Static(
            f"  Path: [dim](or just a name → {config.quick_project_path}/)[/dim]",
            classes="form-label",
        )
        yield Input(placeholder="~/Projects/my-project  or  my_quick_prototype", id="path-input")
        yield ListView(id="path-suggestions")
        yield Static("  Name:", classes="form-label")
        yield Input(placeholder="auto-generated from path", id="name-input")
        yield Static("  Agent:", classes="form-label")
        with RadioSet(id="agent-select"):
            yield RadioButton("Claude", value=True, id="agent-claude")
            yield RadioButton("OpenCode", id="agent-opencode")
            yield RadioButton("Gemini", id="agent-gemini")
        yield Static("  Continue previous session:", classes="form-label")
        yield Switch(value=True, id="continue-switch")
        yield Static(
            "\n  [b]↑/↓[/b] Browse   [b]Tab[/b] Accept   [b]Enter[/b] Next / Create   [b]Esc[/b] Cancel",
            id="form-hint",
        )

    def on_mount(self) -> None:
        self.query_one("#path-suggestions", ListView).display = False
        self.query_one("#path-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "path-input":
            self._update_suggestions(event.value)
            self._auto_fill_name(event.value)
        elif event.input.id == "name-input":
            pass  # User is manually editing

    def _update_suggestions(self, partial: str) -> None:
        if not partial or len(partial) < 2:
            self.query_one("#path-suggestions", ListView).display = False
            self._suggestions = []
            return

        self._suggestions = list_directories(partial)
        lv = self.query_one("#path-suggestions", ListView)
        lv.clear()

        if self._suggestions:
            for s in self._suggestions:
                lv.append(ListItem(Static(f"  {s}")))
            lv.display = True
        else:
            lv.display = False

    def _auto_fill_name(self, path: str) -> None:
        name_input = self.query_one("#name-input", Input)
        # Only auto-fill if user hasn't manually edited
        if not name_input.value or name_input.value == self._last_auto_name:
            from pathlib import Path
            expanded = Path(path).expanduser()
            basename = expanded.name if expanded.name else ""
            name_input.value = basename
            self._last_auto_name = basename

    _last_auto_name: str = ""

    def accept_suggestion(self) -> None:
        """Accept the highlighted suggestion into the path input."""
        if self._suggestions:
            lv = self.query_one("#path-suggestions", ListView)
            idx = lv.index if lv.index is not None else 0
            idx = min(idx, len(self._suggestions) - 1)
            path_input = self.query_one("#path-input", Input)
            path_input.value = self._suggestions[idx]
            path_input.cursor_position = len(path_input.value)
            self._update_suggestions(path_input.value)

    def dismiss_suggestions(self) -> None:
        """Hide the suggestions dropdown."""
        self._suggestions = []
        self.query_one("#path-suggestions", ListView).display = False

    def get_values(self) -> dict:
        """Get form values as a dict."""
        path = self.query_one("#path-input", Input).value.strip()
        name = self.query_one("#name-input", Input).value.strip()
        radio = self.query_one("#agent-select", RadioSet)
        pressed = radio.pressed_button
        agent = pressed.id.removeprefix("agent-") if pressed else "claude"
        continue_session = self.query_one("#continue-switch", Switch).value
        return {
            "path": path,
            "name": name or None,
            "agent": agent,
            "continue_session": continue_session,
        }


class NewSessionApp(App):
    """Standalone new-session TUI for `nagare new` without arguments."""

    CSS_PATH = "new_session.tcss"
    TITLE = "nagare new session"

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield NewSessionForm(id="new-session-form")

    def on_mount(self) -> None:
        config = load_config()
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = config.theme if config.theme in THEMES else "tokyonight"

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

    def on_key(self, event) -> None:
        on_path = self.focused and self.focused.id == "path-input"
        form = self.query_one("#new-session-form", NewSessionForm)
        has_suggestions = bool(form._suggestions)

        if event.key == "tab" and on_path and has_suggestions:
            # Accept the highlighted suggestion
            form.accept_suggestion()
            event.prevent_default()
            event.stop()
        elif event.key in ("down", "up") and on_path and has_suggestions:
            # Browse suggestions
            lv = form.query_one("#path-suggestions", ListView)
            if event.key == "down":
                lv.action_cursor_down()
            else:
                lv.action_cursor_up()
            idx = lv.index
            if idx is not None and 0 <= idx < len(form._suggestions):
                path_input = form.query_one("#path-input", Input)
                path_input.value = form._suggestions[idx]
                path_input.cursor_position = len(path_input.value)
            event.prevent_default()
            event.stop()
        elif event.key == "enter" and on_path:
            # Confirm path, dismiss suggestions, move to name field
            form.dismiss_suggestions()
            name_input = form.query_one("#name-input", Input)
            name_input.focus()
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            # Create session from any other field
            self._create_session()
            event.prevent_default()
            event.stop()

    def action_cancel(self) -> None:
        self.exit(result="back_to_picker")

    def _create_session(self) -> None:
        form = self.query_one("#new-session-form", NewSessionForm)
        values = form.get_values()

        if not values["path"]:
            return

        try:
            name = create_session(**values)
            switch_to_session(name)
            self.exit()
        except (ValueError, RuntimeError) as e:
            logger.exception("Failed to create session")
            # Show error in the form
            self.query_one("#form-title", Static).update(
                f"[b]New Session[/b]  [bold red]Error: {e}[/bold red]"
            )
