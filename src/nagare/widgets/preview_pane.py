from rich.text import Text
from textual.widgets import RichLog


class PreviewPane(RichLog):

    def __init__(self) -> None:
        super().__init__(wrap=False, highlight=False, markup=False)

    def update_content(self, raw_output: str) -> None:
        self.clear()
        if raw_output:
            rendered = Text.from_ansi(raw_output)
            self.write(rendered)
