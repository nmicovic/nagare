import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from nagare.config import load_config
from nagare.notifications.store import NotificationStore
from nagare.themes import THEMES
from nagare.tmux import run_tmux

STORE_PATH = Path.home() / ".local" / "share" / "nagare" / "notifications.json"


def _format_notification(notif) -> str:
    dot = "●" if not notif.read else " "
    ts = notif.timestamp[:19].replace("T", " ")
    return f"{dot} [b]{notif.session_name}[/b]  {notif.message}\n   [dim]{ts}[/dim]"


class NotifsApp(App):
    CSS_PATH = "notifs.tcss"
    TITLE = "nagare notifications"

    BINDINGS = [
        Binding("escape", "quit", "Close", show=False),
        Binding("d", "dismiss", "Dismiss", show=False),
        Binding("D", "dismiss_all", "Dismiss All", show=False),
    ]

    def __init__(self, store: NotificationStore | None = None) -> None:
        super().__init__()
        self._store = store or NotificationStore(STORE_PATH)

    def compose(self) -> ComposeResult:
        yield OptionList(id="notif-list")
        yield Static(
            "[b]Enter[/b] Jump  [b]d[/b] Dismiss  [b]D[/b] Dismiss all  [b]Esc[/b] Close",
            id="hint-bar",
        )

    def on_mount(self) -> None:
        config = load_config()
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = config.theme if config.theme in THEMES else "tokyonight"

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        self._rebuild_list()

    def _rebuild_list(self) -> None:
        notifs = self._store.list_all()
        option_list = self.query_one("#notif-list", OptionList)
        option_list.clear_options()
        for notif in notifs:
            option_list.add_option(Option(_format_notification(notif), id=notif.id))
        if not notifs:
            option_list.add_option(Option("[dim]No notifications[/dim]"))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        notifs = self._store.list_all()
        idx = event.option_index
        if 0 <= idx < len(notifs):
            notif = notifs[idx]
            self._store.mark_read(notif.id)
            run_tmux("switch-client", "-t", notif.session_name)
            self.exit()

    def action_dismiss(self) -> None:
        option_list = self.query_one("#notif-list", OptionList)
        highlighted = option_list.highlighted
        notifs = self._store.list_all()
        if highlighted is not None and 0 <= highlighted < len(notifs):
            self._store.dismiss(notifs[highlighted].id)
            self._rebuild_list()

    def action_dismiss_all(self) -> None:
        self._store.dismiss_all()
        self._rebuild_list()
