from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import ListView, ListItem, Label


class ThemePicker(ModalScreen[str | None]):
    """Modal screen for picking a theme."""

    DEFAULT_CSS = """
    ThemePicker {
        align: center middle;
    }

    ThemePicker > #theme-dialog {
        width: 40;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }

    ThemePicker > #theme-dialog > #theme-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    ThemePicker > #theme-dialog > ListView {
        height: auto;
        max-height: 20;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def __init__(self, theme_names: list[str], current: str) -> None:
        super().__init__()
        self._theme_names = theme_names
        self._current = current

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        with Vertical(id="theme-dialog"):
            yield Label("Select Theme", id="theme-title")
            items = []
            initial = 0
            for i, name in enumerate(self._theme_names):
                marker = "  * " if name == self._current else "    "
                items.append(ListItem(Label(f"{marker}{name}")))
                if name == self._current:
                    initial = i
            yield ListView(*items, initial_index=initial, id="theme-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.index is not None:
            self.dismiss(self._theme_names[event.list_view.index])

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one(ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(ListView).action_cursor_up()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Live preview: apply theme as user navigates."""
        if event.list_view.index is not None:
            self.app.theme = self._theme_names[event.list_view.index]
