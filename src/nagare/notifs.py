import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import ListView, ListItem, Static

from nagare.config import load_config
from nagare.notifications.store import NotificationStore
from nagare.themes import THEMES
from nagare.tmux import run_tmux

STORE_PATH = Path.home() / ".local" / "share" / "nagare" / "notifications.json"


def _format_notification(notif) -> tuple[str, str]:
    dot = "●" if not notif.read else " "
    icon = "✅" if "finished" in notif.message.lower() else "⏳"
    line1 = f"{dot} {icon} [b]{notif.session_name}[/b]  {notif.message}"
    ts = notif.timestamp[:19].replace("T", " ")
    line2 = f"   [dim]{ts}[/dim]"
    return line1, line2


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
        yield ListView(id="notif-list")
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
        lv = self.query_one("#notif-list", ListView)
        lv.clear()
        for notif in notifs:
            line1, line2 = _format_notification(notif)
            item = ListItem(
                Vertical(Static(line1), Static(line2)),
                classes="notif-item",
            )
            lv.append(item)
        if not notifs:
            lv.append(
                ListItem(
                    Vertical(Static("[dim]No notifications[/dim]")),
                    classes="notif-item",
                )
            )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        notifs = self._store.list_all()
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(notifs):
            notif = notifs[idx]
            self._store.mark_read(notif.id)
            run_tmux("switch-client", "-t", notif.session_name)
            self.exit()

    def action_dismiss(self) -> None:
        lv = self.query_one("#notif-list", ListView)
        idx = lv.index
        notifs = self._store.list_all()
        if idx is not None and 0 <= idx < len(notifs):
            self._store.dismiss(notifs[idx].id)
            self._rebuild_list()

    def action_dismiss_all(self) -> None:
        self._store.dismiss_all()
        self._rebuild_list()
