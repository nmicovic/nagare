from rich.text import Text
from textual.widgets import RichLog


class TerminalView(RichLog):

    DEFAULT_CSS = """
    TerminalView {
        border: solid $surface;
    }

    TerminalView.active-pane {
        border: solid $primary;
    }
    """

    def __init__(self) -> None:
        super().__init__(wrap=False, highlight=False, markup=False)

    def update_content(self, raw_output: str) -> None:
        self.clear()
        if raw_output:
            rendered = Text.from_ansi(raw_output)
            self.write(rendered)

    def set_active(self, active: bool) -> None:
        if active:
            self.add_class("active-pane")
        else:
            self.remove_class("active-pane")
