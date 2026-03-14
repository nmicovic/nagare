import os
from dataclasses import replace
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import (
    Input, ListView, ListItem, Static, Switch, TabbedContent, TabPane,
)

from nagare.config import (
    NotificationConfig, NotificationEventConfig,
    load_config, save_notification_config,
)
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


def _setting_row(label: str, widget_id: str, value: bool) -> Vertical:
    """Create a label + switch row for a boolean setting."""
    return Vertical(
        Static(f"  {label}", classes="setting-label"),
        Switch(value=value, id=widget_id, classes="setting-switch"),
        classes="setting-row",
    )


def _number_row(label: str, widget_id: str, value: int) -> Vertical:
    """Create a label + input row for a numeric setting."""
    return Vertical(
        Static(f"  {label}", classes="setting-label"),
        Input(str(value), id=widget_id, classes="setting-input"),
        classes="setting-row",
    )


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
        self._config = load_config()
        self._notif_config = self._config.notifications

    def compose(self) -> ComposeResult:
        nc = self._notif_config
        ni = nc.needs_input
        tc = nc.task_complete

        with TabbedContent(id="tabs"):
            with TabPane("Notifications", id="tab-notifs"):
                yield ListView(id="notif-list")
            with TabPane("Settings", id="tab-settings"):
                with VerticalScroll(id="settings-scroll"):
                    # Master switch
                    yield Static("  [b]Master[/b]", classes="section-header")
                    yield _setting_row(
                        "Notifications enabled", "cfg-enabled", nc.enabled
                    )

                    # Needs Input section
                    yield Static(
                        "  [b]Needs Input[/b]  [dim]— when Claude needs your action[/dim]",
                        classes="section-header",
                    )
                    yield _setting_row("Toast", "cfg-ni-toast", ni.toast)
                    yield _setting_row("Bell", "cfg-ni-bell", ni.bell)
                    yield _setting_row("OS Notify", "cfg-ni-os-notify", ni.os_notify)
                    yield _setting_row("Popup", "cfg-ni-popup", ni.popup)
                    yield _number_row(
                        "Popup timeout (seconds)", "cfg-ni-popup-timeout", ni.popup_timeout
                    )

                    # Task Complete section
                    yield Static(
                        "  [b]Task Complete[/b]  [dim]— when Claude finishes a long task[/dim]",
                        classes="section-header",
                    )
                    yield _setting_row("Toast", "cfg-tc-toast", tc.toast)
                    yield _setting_row("Bell", "cfg-tc-bell", tc.bell)
                    yield _setting_row("OS Notify", "cfg-tc-os-notify", tc.os_notify)
                    yield _setting_row("Popup", "cfg-tc-popup", tc.popup)
                    yield _number_row(
                        "Popup timeout (seconds)", "cfg-tc-popup-timeout", tc.popup_timeout
                    )
                    yield _number_row(
                        "Min working seconds", "cfg-tc-min-working", tc.min_working_seconds
                    )

                    yield Static(
                        "  [dim]Changes saved automatically to ~/.config/nagare/config.toml[/dim]",
                        classes="settings-footer",
                    )

        yield Static(
            "[b]Enter[/b] Jump  [b]d[/b] Dismiss  [b]D[/b] Dismiss all  [b]Esc[/b] Close",
            id="hint-bar",
        )

    def on_mount(self) -> None:
        config = self._config
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

    # ── Settings handlers ──

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle any toggle switch change — update config and save."""
        self._apply_setting(event.switch.id, event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle numeric input changes — validate and save."""
        widget_id = event.input.id
        if widget_id and widget_id.startswith("cfg-"):
            try:
                value = int(event.value)
                if value >= 0:
                    self._apply_setting(widget_id, value)
            except ValueError:
                pass  # Ignore non-numeric input

    def _apply_setting(self, widget_id: str | None, value: bool | int) -> None:
        """Map a widget ID to the config field and save."""
        if not widget_id:
            return

        nc = self._notif_config

        # Master switch
        if widget_id == "cfg-enabled":
            self._notif_config = replace(nc, enabled=value)

        # Needs input fields
        elif widget_id == "cfg-ni-toast":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, toast=value))
        elif widget_id == "cfg-ni-bell":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, bell=value))
        elif widget_id == "cfg-ni-os-notify":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, os_notify=value))
        elif widget_id == "cfg-ni-popup":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, popup=value))
        elif widget_id == "cfg-ni-popup-timeout":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, popup_timeout=value))

        # Task complete fields
        elif widget_id == "cfg-tc-toast":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, toast=value))
        elif widget_id == "cfg-tc-bell":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, bell=value))
        elif widget_id == "cfg-tc-os-notify":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, os_notify=value))
        elif widget_id == "cfg-tc-popup":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, popup=value))
        elif widget_id == "cfg-tc-popup-timeout":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, popup_timeout=value))
        elif widget_id == "cfg-tc-min-working":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, min_working_seconds=value))
        else:
            return

        save_notification_config(self._notif_config)
