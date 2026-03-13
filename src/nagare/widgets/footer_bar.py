from textual.widgets import Static


class FooterBar(Static):

    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 2;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        content = (
            "[b]↑/k[/b] Up  [b]↓/j[/b] Down  [b]Enter[/b] Attach  [b]r[/b] Refresh  [b]q[/b] Quit\n"
            "Detach from session: [b]Ctrl+b d[/b]"
        )
        super().__init__(content)
