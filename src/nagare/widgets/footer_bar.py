from textual.widgets import Static

BROWSE_FOOTER = (
    "[b]↑/k[/b] Up  [b]↓/j[/b] Down  [b]Ctrl+][/b] Interact  "
    "[b]r[/b] Refresh  [b]t[/b] Theme  [b]q[/b] Quit"
)

INTERACTIVE_FOOTER = (
    "[b]Ctrl+][/b] Back to sessions    "
    "All input forwarded to session"
)


class FooterBar(Static):

    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(BROWSE_FOOTER)

    def set_browse_mode(self) -> None:
        self.update(BROWSE_FOOTER)

    def set_interactive_mode(self) -> None:
        self.update(INTERACTIVE_FOOTER)
